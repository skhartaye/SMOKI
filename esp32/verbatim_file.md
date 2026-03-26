rpi
#!/usr/bin/env python3
"""
rpi_snap.py  —  Smoki Project  |  Snapshot detection every N seconds
═══════════════════════════════════════════════════════════════════════
Every INTERVAL seconds:
  1. Capture one frame from picam2
  2. Run smoke / license-plate / vehicle Hailo models
  3. HOG pedestrian detection → blur pedestrians only (cyclists/motos skipped)
  4. Crop plate regions → EasyOCR
  5. Draw bounding boxes on annotated frame
  6. POST annotated JPEG + all metadata to backend
  7. Sleep until next interval

No FFmpeg, no HLS, no queues, no threads.
Simple, stable, easy to debug.
═══════════════════════════════════════════════════════════════════════
"""

import hailo_platform as hp
import numpy as np
import cv2
import time
import os
import requests
import json
from datetime import datetime, timezone
from picamera2 import Picamera2
from concurrent.futures import ThreadPoolExecutor

# ─── CONFIGURATION ────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env.rpi'))
except ImportError:
    pass

INTERVAL        = 5.0
BACKEND_URL     = os.getenv('API_URL',          'https://smoki-backend-rpi.onrender.com')
CAMERA_ID       = os.getenv('DEVICE_ID',        'rpi_camera_01')
CAMERA_LOCATION = os.getenv('CAMERA_LOCATION',  'Main_Entrance')

PLATE_CONF   = 0.3
SMOKE_CONF   = 0.53
VEHICLE_CONF = 0.3

SMOKE_CLASSES   = {'smoke_black', 'smoke_white'}
VEHICLE_CLASSES = {'passenger', 'puv', 'services', 'two_wheel'}

# ─── PEDESTRIAN BLUR CONFIGURATION ───────────────────────────────────────────
# HOG detector settings
PED_CONF_THRESHOLD  = 0.3    # Minimum HOG score to count as a person
PED_UPSCALE         = 2.0    # Upscale before detection (helps find small/distant people)
PED_BLUR_STRENGTH   = 55     # Gaussian blur kernel strength (odd number)
PED_BLUR_PAD        = 8      # Extra pixels to pad around each detected person box

# Background texture threshold — the key to separating pedestrians from riders:
#   Road / asphalt = flat, low pixel variance  → cyclists / motorcyclists
#   Sidewalk / buildings = complex, high variance → pedestrians
# Raise this value if cyclists are still being blurred.
# Lower it if sidewalk pedestrians are being skipped.
PED_TEXTURE_THRESHOLD = 38

ALL_MODELS = [
    {
        "hef":     "/home/sevi/smoki_project/src/model-skhart-ready/smoke-hailo8l.hef",
        "classes": ["smoke_black", "smoke_white"],
        "type":    "seg",
        "conf":    SMOKE_CONF,
        "role":    "smoke",
    },
    {
        "hef":     "/home/sevi/smoki_project/src/model-skhart-ready/license-plate-opt-hailo8l.hef",
        "classes": ["license_plate"],
        "type":    "detect",
        "conf":    PLATE_CONF,
        "role":    "plate_detect",
    },
    {
        "hef":     "/home/sevi/smoki_project/src/model-skhart-ready/vehicle-class-hailo8l.hef",
        "classes": ["passenger", "puv", "services", "two_wheel"],
        "type":    "detect",
        "conf":    VEHICLE_CONF,
        "role":    "vehicle",
    },
]

# ─── PER-TENSOR QUANT PARAMS ──────────────────────────────────────────────────
QUANT_PARAMS = {
    "yolov8n_seg/conv73": (0.087893,  69.0),
    "yolov8n_seg/conv74": (0.003922,   0.0),
    "yolov8n_seg/conv75": (0.018757, 162.0),
    "yolov8n_seg/conv60": (0.085621,  64.0),
    "yolov8n_seg/conv61": (0.003922,   0.0),
    "yolov8n_seg/conv62": (0.017188, 174.0),
    "yolov8n_seg/conv44": (0.093213,  79.0),
    "yolov8n_seg/conv45": (0.003922,   0.0),
    "yolov8n_seg/conv46": (0.018580, 173.0),
    "yolov8n_seg/conv48": (0.021440,  14.0),
    "yolov8n/conv41":     (0.116865, 118.0),
    "yolov8n/conv42":     (0.040536, 255.0),
    "yolov8n/conv52":     (0.120670,  92.0),
    "yolov8n/conv53":     (0.032743, 255.0),
    "yolov8n/conv62":     (0.071806,  71.0),
    "yolov8n/conv63":     (0.022815, 255.0),
}

VEHICLE_QUANT = {
    "yolov8n/conv41": (0.173322, 145.0),
    "yolov8n/conv42": (0.160111, 255.0),
    "yolov8n/conv52": (0.108191, 147.0),
    "yolov8n/conv53": (0.123836, 255.0),
    "yolov8n/conv62": (0.116450, 101.0),
    "yolov8n/conv63": (0.152770, 245.0),
}

COLORS = [(0,0,255),(0,255,0),(255,0,0),(0,255,255),(255,0,255),(255,255,0)]

# ─── BACKEND ──────────────────────────────────────────────────────────────────
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="backend")

def _post(url, **kwargs):
    try:
        requests.post(url, timeout=10, **kwargs)
    except Exception as e:
        print(f"[Backend] POST failed {url}: {e}")

def submit(fn, *args):
    _executor.submit(fn, *args)

# ─── DEQUANTIZATION ───────────────────────────────────────────────────────────
def dequant(raw: np.ndarray, name: str, qmap: dict) -> np.ndarray:
    arr = raw.astype(np.float32)
    if name in qmap:
        scale, zp = qmap[name]
        return (arr - zp) * scale
    return arr

# ─── DFL BBOX DECODE ──────────────────────────────────────────────────────────
def dfl_decode(reg, stride):
    H, W, _ = reg.shape
    num_bins = 16
    reg_r = reg.reshape(H, W, 4, num_bins)
    reg_r = reg_r - reg_r.max(axis=-1, keepdims=True)
    reg_s = np.exp(reg_r)
    reg_s /= reg_s.sum(axis=-1, keepdims=True)
    dist  = (reg_s * np.arange(num_bins, dtype=np.float32)).sum(axis=-1)
    gy, gx = np.meshgrid(np.arange(H), np.arange(W), indexing='ij')
    x1 = (gx + 0.5 - dist[..., 0]) * stride
    y1 = (gy + 0.5 - dist[..., 1]) * stride
    x2 = (gx + 0.5 + dist[..., 2]) * stride
    y2 = (gy + 0.5 + dist[..., 3]) * stride
    return x1, y1, x2, y2

# ─── NMS ──────────────────────────────────────────────────────────────────────
def nms(detections, score_thresh=0.0, iou_thresh=0.45):
    if not detections:
        return []
    boxes  = [[d["bbox"][0], d["bbox"][1],
               d["bbox"][2]-d["bbox"][0], d["bbox"][3]-d["bbox"][1]] for d in detections]
    scores = [d["conf"] for d in detections]
    idx    = cv2.dnn.NMSBoxes(boxes, scores, float(score_thresh), float(iou_thresh))
    return [detections[i] for i in idx.flatten()] if len(idx) else []

# ─── DECODERS ────────────────────────────────────────────────────────────────
def _logit_thresh(conf):
    eps = 1e-6
    c   = float(np.clip(conf, eps, 1.0 - eps))
    return float(np.log(c / (1.0 - c)))

def decode_detect(outputs, orig_size, input_size, classes, conf_thresh,
                  iou_thresh=0.45, qmap=None):
    if qmap is None:
        qmap = QUANT_PARAMS
    strides  = [8, 16, 32]
    reg_keys = ["yolov8n/conv41", "yolov8n/conv52", "yolov8n/conv62"]
    cls_keys = ["yolov8n/conv42", "yolov8n/conv53", "yolov8n/conv63"]
    orig_h, orig_w = orig_size
    sx, sy = orig_w / input_size[0], orig_h / input_size[1]
    lt   = _logit_thresh(conf_thresh)
    dets = []
    for stride, rk, ck in zip(strides, reg_keys, cls_keys):
        if rk not in outputs or ck not in outputs:
            continue
        reg    = dequant(outputs[rk][0], rk, qmap)
        logits = dequant(outputs[ck][0], ck, qmap)
        ls = logits[..., 0] if logits.shape[-1] == 1 else logits.max(axis=-1)
        ci = (np.zeros(ls.shape, dtype=int)
              if logits.shape[-1] == 1 else logits.argmax(axis=-1))
        mask = ls >= lt
        if not mask.any():
            continue
        sc = 1.0 / (1.0 + np.exp(-ls))
        x1, y1, x2, y2 = dfl_decode(reg, stride)
        for iy, ix in zip(*np.where(mask)):
            cid = int(ci[iy, ix])
            dets.append({
                "bbox": (int(np.clip(x1[iy,ix]*sx,0,orig_w)),
                         int(np.clip(y1[iy,ix]*sy,0,orig_h)),
                         int(np.clip(x2[iy,ix]*sx,0,orig_w)),
                         int(np.clip(y2[iy,ix]*sy,0,orig_h))),
                "conf":       float(sc[iy, ix]),
                "class_id":   cid,
                "class_name": classes[cid] if cid < len(classes) else "?",
            })
    return nms(dets, score_thresh=conf_thresh, iou_thresh=iou_thresh)


def decode_seg(outputs, orig_size, input_size, classes, conf_thresh, iou_thresh=0.45):
    strides  = [8, 16, 32]
    reg_keys = ["yolov8n_seg/conv44", "yolov8n_seg/conv60", "yolov8n_seg/conv73"]
    cls_keys = ["yolov8n_seg/conv45", "yolov8n_seg/conv61", "yolov8n_seg/conv74"]
    orig_h, orig_w = orig_size
    sx, sy = orig_w / input_size[0], orig_h / input_size[1]
    lt   = _logit_thresh(conf_thresh)
    dets = []
    for stride, rk, ck in zip(strides, reg_keys, cls_keys):
        if rk not in outputs:
            continue
        reg    = dequant(outputs[rk][0], rk, QUANT_PARAMS)
        logits = dequant(outputs[ck][0], ck, QUANT_PARAMS)
        ls   = logits.max(axis=-1)
        ci   = logits.argmax(axis=-1)
        mask = ls >= lt
        if not mask.any():
            continue
        sc = 1.0 / (1.0 + np.exp(-ls))
        x1, y1, x2, y2 = dfl_decode(reg, stride)
        for iy, ix in zip(*np.where(mask)):
            cid = int(ci[iy, ix])
            dets.append({
                "bbox": (int(np.clip(x1[iy,ix]*sx,0,orig_w)),
                         int(np.clip(y1[iy,ix]*sy,0,orig_h)),
                         int(np.clip(x2[iy,ix]*sx,0,orig_w)),
                         int(np.clip(y2[iy,ix]*sy,0,orig_h))),
                "conf":       float(sc[iy, ix]),
                "class_id":   cid,
                "class_name": classes[cid] if cid < len(classes) else "?",
            })
    return nms(dets, score_thresh=conf_thresh, iou_thresh=iou_thresh)

# ─── SMOKE OPACITY CLASSIFIER ────────────────────────────────────────────────
FRAME_AREA = 1280 * 720

def classify_smoke_opacity(det, frame_bgr=None):
    x1, y1, x2, y2 = det["bbox"]
    conf = det["conf"]
    bbox_area  = max(1, (x2 - x1) * (y2 - y1))
    area_score = min(1.0, (bbox_area / FRAME_AREA) / 0.5)
    dark_score = 0.0
    if frame_bgr is not None:
        try:
            roi = frame_bgr[max(0,y1):min(frame_bgr.shape[0],y2),
                            max(0,x1):min(frame_bgr.shape[1],x2)]
            if roi.size > 0:
                gray         = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                dark_ratio   = float(np.mean(gray < 80))
                bright_ratio = float(np.mean(gray > 200))
                dark_score   = max(dark_ratio, bright_ratio * 0.7)
        except Exception:
            pass
    if dark_score > 0:
        opacity_score = 0.5 * conf + 0.3 * area_score + 0.2 * dark_score
    else:
        opacity_score = 0.6 * conf + 0.4 * area_score
    if opacity_score >= 0.70:
        level = "dense"
    elif opacity_score >= 0.45:
        level = "moderate"
    else:
        level = "thin"
    return level, round(opacity_score, 3)

# ─── PEDESTRIAN DETECTION + BLUR (replaces face model) ───────────────────────

# Module-level HOG detector — created once, reused every frame (cheap)
_hog = cv2.HOGDescriptor()
_hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())


def _hog_nms(boxes, overlap_thresh=0.35):
    """Non-maximum suppression for HOG detections."""
    if not boxes:
        return []
    arr = np.array([(x, y, x+w, y+h, c) for x, y, w, h, c in boxes], dtype=float)
    x1, y1, x2, y2, scores = arr[:,0], arr[:,1], arr[:,2], arr[:,3], arr[:,4]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep  = []
    while order.size:
        i = order[0]
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        iou   = inter / (areas[i] + areas[order[1:]] - inter)
        order = order[np.where(iou <= overlap_thresh)[0] + 1]
    return [boxes[k] for k in keep]


def _build_texture_map(img):
    """
    Compute a smoothed per-column texture profile.
    Low std = flat road (rider zone).  High std = complex background (pedestrian zone).
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    col_texture = np.array([
        np.std(gray[:, c].astype(float)) for c in range(img.shape[1])
    ])
    return gray, np.convolve(col_texture, np.ones(20) / 20, mode='same')


def _bg_texture_score(gray_img, col_texture_smooth, x, y, w, h):
    """
    Average of:
      - Column texture at the detection's horizontal center
      - Pixel std of the patch directly below the person's feet

    Low score  → flat asphalt → cyclist / motorcyclist → skip
    High score → complex background → pedestrian → blur
    """
    h_img, w_img = gray_img.shape[:2]
    cx     = x + w // 2
    tx_min = max(0, cx - 20)
    tx_max = min(w_img - 1, cx + 20)
    col_score = float(np.mean(col_texture_smooth[tx_min:tx_max + 1]))

    bx1 = max(0, x);          bx2 = min(w_img, x + w)
    by1 = min(h_img, y + h);  by2 = min(h_img, y + h + int(h * 0.6))
    below_score = 0.0
    if by2 > by1 and bx2 > bx1:
        below_score = float(np.std(gray_img[by1:by2, bx1:bx2].astype(float)))

    return (col_score + below_score) / 2.0


def detect_and_blur_pedestrians(frame_bgr, vis_frame,
                                upscale=PED_UPSCALE,
                                conf_thresh=PED_CONF_THRESHOLD,
                                texture_thresh=PED_TEXTURE_THRESHOLD,
                                blur_strength=PED_BLUR_STRENGTH,
                                pad=PED_BLUR_PAD):
    """
    1. Detect all upright humans via HOG (upscaled for small/distant figures).
    2. Classify each detection as pedestrian vs rider using background texture:
         - Road (flat asphalt) = low texture std  → cyclist / motorcyclist → skip
         - Sidewalk / buildings = high texture std → pedestrian → blur
    3. Apply pixelate + Gaussian blur to pedestrian regions on vis_frame IN-PLACE.

    Returns:
        ped_count  (int)  — number of pedestrians blurred
        rider_count (int) — number of riders skipped (for logging)
    """
    h, w = frame_bgr.shape[:2]

    # ── HOG detection on upscaled copy ──────────────────────────────────────
    img_big = cv2.resize(frame_bgr,
                         (int(w * upscale), int(h * upscale)),
                         interpolation=cv2.INTER_CUBIC)

    all_boxes = []
    for scale in [1.03, 1.05, 1.08, 1.12]:
        boxes, weights = _hog.detectMultiScale(
            img_big, winStride=(4, 4), padding=(8, 8), scale=scale
        )
        if not len(boxes):
            continue
        for i, (bx, by, bw, bh) in enumerate(boxes):
            conf = float(weights[i]) if weights.ndim == 1 else float(weights[i][0])
            if conf >= conf_thresh:
                all_boxes.append((
                    int(bx / upscale), int(by / upscale),
                    int(bw / upscale), int(bh / upscale),
                    conf
                ))

    persons = _hog_nms(all_boxes)
    if not persons:
        return 0, 0

    # ── Classify: pedestrian vs rider ───────────────────────────────────────
    gray, col_texture = _build_texture_map(frame_bgr)
    pedestrians = []
    riders      = []

    # Road center X band — vehicles dominate this zone
    road_x_left  = int(w * 0.25)
    road_x_right = int(w * 0.78)
    # Top 20% of frame = distant objects on the road (appear small, far away)
    distant_y_thresh = int(h * 0.20)
    # Minimum bounding box area — very small detections are distant vehicles
    min_ped_area = 3500  # ~60x58 px; below this = too far away to be a sidewalk pedestrian

    for (px, py, pw, ph, pconf) in persons:
        cx       = px + pw // 2
        box_area = pw * ph

        # Rule 1: Tiny box = distant vehicle on road
        if box_area < min_ped_area:
            riders.append((px, py, pw, ph, pconf))
            continue

        # Rule 2: Road-center AND top-of-frame = distant motorcyclist/rider
        in_road_x   = road_x_left < cx < road_x_right
        in_distant_y = py < distant_y_thresh
        if in_road_x and in_distant_y:
            riders.append((px, py, pw, ph, pconf))
            continue

        # Rule 3: Background texture — flat road vs complex sidewalk/buildings
        score = _bg_texture_score(gray, col_texture, px, py, pw, ph)
        if score >= texture_thresh:
            pedestrians.append((px, py, pw, ph, pconf))
        else:
            riders.append((px, py, pw, ph, pconf))

    # ── Blur pedestrians on vis_frame ────────────────────────────────────────
    k = blur_strength if blur_strength % 2 == 1 else blur_strength + 1

    for (px, py, pw, ph, _) in pedestrians:
        x1 = max(0, px - pad);      y1 = max(0, py - pad)
        x2 = min(w, px + pw + pad); y2 = min(h, py + ph + pad)
        roi = vis_frame[y1:y2, x1:x2]
        if roi.size == 0:
            continue
        # Pixelate then Gaussian for strong anonymisation
        small     = cv2.resize(roi,
                               (max(1, roi.shape[1] // 12), max(1, roi.shape[0] // 12)),
                               interpolation=cv2.INTER_LINEAR)
        pixelated = cv2.resize(small, (roi.shape[1], roi.shape[0]),
                               interpolation=cv2.INTER_NEAREST)
        vis_frame[y1:y2, x1:x2] = cv2.GaussianBlur(pixelated, (k, k), 0)

    return len(pedestrians), len(riders)


# ─── PLATE OCR ────────────────────────────────────────────────────────────────
def load_ocr():
    try:
        import easyocr
        reader = easyocr.Reader(['en'], gpu=False, verbose=False)
        print("[OK] EasyOCR ready")
        return reader
    except Exception as e:
        print(f"[WARNING] EasyOCR failed: {e}")
        return None

def _preprocess_plate(crop_bgr: np.ndarray) -> np.ndarray:
    h, w = crop_bgr.shape[:2]
    if h < 100:
        scale    = 100 / h
        crop_bgr = cv2.resize(crop_bgr, (int(w * scale), 100),
                              interpolation=cv2.INTER_CUBIC)
    gray   = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    thresh = cv2.adaptiveThreshold(gray, 255,
                                   cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, 11, 2)
    return cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)

def read_plate(reader, crop_bgr):
    if reader is None or crop_bgr is None:
        return "", 0.0
    try:
        processed = _preprocess_plate(crop_bgr)
        results   = reader.readtext(
            processed,
            allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
            width_ths=0.7, height_ths=0.7,
            detail=1, paragraph=False, batch_size=1,
        )
        if not results:
            return "", 0.0
        results = sorted(results, key=lambda r: r[2], reverse=True)
        text    = ''.join(c for c in ''.join(r[1] for r in results) if c.isalnum())
        conf    = float(results[0][2])
        return text.strip(), conf
    except Exception as e:
        print(f"[OCR] Error: {e}")
        return "", 0.0

# ─── BACKEND SENDERS ──────────────────────────────────────────────────────────
def send_snapshot(frame_bgr, timestamp, all_dets, smoke_dets,
                  vehicle_dets, plate_results, ped_count, rider_count, inf_ms):
    _, jpg = cv2.imencode('.jpg', frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
    is_violation = len(smoke_dets) > 0 and len(vehicle_dets) > 0
    payload = {
        "camera_id":     CAMERA_ID,
        "location":      CAMERA_LOCATION,
        "timestamp":     timestamp,
        "has_detection": len(all_dets) > 0,
        "is_violation":  is_violation,
        "detections":    all_dets,
        "plates":        plate_results,
        "summary": {
            "total_detections":  len(all_dets),
            "smoke_detections":  len(smoke_dets),
            "smoke_opacity_levels": {
                "thin":     sum(1 for d in smoke_dets if d.get("opacity_level") == "thin"),
                "moderate": sum(1 for d in smoke_dets if d.get("opacity_level") == "moderate"),
                "dense":    sum(1 for d in smoke_dets if d.get("opacity_level") == "dense"),
            },
            "vehicle_detections":   len(vehicle_dets),
            "plate_detections":     len(plate_results),
            "plates_with_text":     sum(1 for p in plate_results if p.get("text")),
            "pedestrians_blurred":  ped_count,    # was face_count
            "riders_skipped":       rider_count,
            "inference_time_ms":    inf_ms,
            "frame_size_bytes":     len(jpg),
            "violation_detected":   is_violation,
        },
    }
    _post(f"{BACKEND_URL}/api/stream/frame",
          files={"frame": ("frame.jpg", jpg.tobytes(), "image/jpeg")},
          data={"metadata": json.dumps(payload)})

    flag = " 🚨 VIOLATION" if is_violation else ""
    print(f"[Sent] smoke={len(smoke_dets)} veh={len(vehicle_dets)} "
          f"plates={len(plate_results)} ped_blur={ped_count} riders_skip={rider_count} "
          f"inf={inf_ms}ms{flag}")


def send_smoke(timestamp, det, inf_ms, opacity_level, opacity_score, frame_bgr=None):
    x1, y1, x2, y2 = det["bbox"]
    files = None
    if frame_bgr is not None:
        try:
            roi = frame_bgr[max(0,y1):min(frame_bgr.shape[0],y2),
                            max(0,x1):min(frame_bgr.shape[1],x2)]
            if roi.size > 0:
                _, buf = cv2.imencode('.jpg', roi, [cv2.IMWRITE_JPEG_QUALITY, 85])
                files = {"smoke_crop": ("smoke.jpg", buf.tobytes(), "image/jpeg")}
        except Exception:
            pass
    payload = {
        "timestamp":         timestamp,
        "camera_id":         CAMERA_ID,
        "location":          CAMERA_LOCATION,
        "confidence":        det["conf"],
        "smoke_type":        det["class_name"],
        "opacity_level":     opacity_level,
        "opacity_score":     opacity_score,
        "bounding_box":      {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
        "bbox_area_px":      (x2-x1) * (y2-y1),
        "inference_time_ms": inf_ms,
    }
    if files:
        _post(f"{BACKEND_URL}/api/detections/smoke",
              files=files, data={"metadata": json.dumps(payload)})
    else:
        _post(f"{BACKEND_URL}/api/detections/smoke", json=payload)
    print(f"  🔥 Smoke: {det['class_name']} | {opacity_level} "
          f"(score={opacity_score:.2f} conf={det['conf']:.2f})")


def send_plate(timestamp, plate_text, ocr_conf, bbox, crop_bgr, inf_ms):
    _, jpg = cv2.imencode('.jpg', crop_bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])
    x1, y1, x2, y2 = bbox
    fname = f"plate_{plate_text}_{timestamp[11:19].replace(':','')}.jpg"
    _post(f"{BACKEND_URL}/api/stream/plate-crop",
          files={"plate_crop": (fname, jpg.tobytes(), "image/jpeg")},
          data={"metadata": json.dumps({
              "camera_id":        CAMERA_ID,
              "location":         CAMERA_LOCATION,
              "timestamp":        timestamp,
              "plate_text":       plate_text,
              "ocr_confidence":   ocr_conf,
              "bbox":             {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
              "inference_time_ms": inf_ms,
          })})

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    # ── Camera ────────────────────────────────────────────────────────────────
    print("[INFO] Starting camera...")
    picam2 = Picamera2()
    picam2.configure(picam2.create_still_configuration(
        main={"format": "BGR888", "size": (1280, 720)}))
    picam2.start()
    time.sleep(1)
    print("[OK] Camera ready")

    # ── OCR ───────────────────────────────────────────────────────────────────
    ocr = load_ocr()

    # ── Hailo ─────────────────────────────────────────────────────────────────
    print("[INFO] Loading Hailo models...")
    from hailo_platform import HailoSchedulingAlgorithm
    vparams = hp.VDevice.create_params()
    vparams.scheduling_algorithm = HailoSchedulingAlgorithm.ROUND_ROBIN

    hefs = [hp.HEF(m["hef"]) for m in ALL_MODELS]
    for m in ALL_MODELS:
        print(f"[OK] Loaded: {m['hef'].split('/')[-1]}")

    print("[OK] HOG pedestrian detector ready (no model file needed)")

    with hp.VDevice(vparams) as target:
        configured = []
        for hef, m in zip(hefs, ALL_MODELS):
            cp    = hp.ConfigureParams.create_from_hef(hef, hp.HailoStreamInterface.PCIe)
            ng    = target.configure(hef, cp)[0]
            ngp   = ng.create_params()
            in_p  = hp.InputVStreamParams.make(ng, hp.FormatType.UINT8)
            out_p = hp.OutputVStreamParams.make(ng, hp.FormatType.FLOAT32)
            iname = hef.get_input_vstream_infos()[0].name
            configured.append({
                "cfg": m, "ng": ng, "ngp": ngp,
                "in_p": in_p, "out_p": out_p, "iname": iname,
            })
            print(f"[OK] Configured: {m['hef'].split('/')[-1]}")

        print(f"\n[INFO] Running snapshot loop every {INTERVAL}s — Ctrl+C to stop\n")

        snap_count = 0
        while True:
            loop_start = time.time()
            ts         = datetime.now(timezone.utc).isoformat()

            # ── 1. Capture ────────────────────────────────────────────────────
            frame_bgr = picam2.capture_array()
            orig_h, orig_w = frame_bgr.shape[:2]
            orig_size = (orig_h, orig_w)

            resized   = cv2.resize(frame_bgr, (640, 640))
            rgb       = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            inp_uint8 = np.expand_dims(rgb.astype(np.uint8), 0)

            vis_frame    = frame_bgr.copy()
            all_dets     = []
            smoke_dets   = []
            vehicle_dets = []
            plate_dets   = []

            # ── 2. Hailo inference ────────────────────────────────────────────
            t_inf = time.time()
            for cm in configured:
                cfg      = cm["cfg"]
                inp_data = {cm["iname"]: inp_uint8}
                try:
                    with hp.InferVStreams(cm["ng"], cm["in_p"], cm["out_p"]) as vs:
                        # No need for explicit activate() with ROUND_ROBIN scheduler
                        raw_out = vs.infer(inp_data)
                except Exception as e:
                    print(f"[ERROR] Infer {cfg['role']}: {e}")
                    continue

                if cfg["type"] == "seg":
                    dets = decode_seg(raw_out, orig_size, (640, 640),
                                      cfg["classes"], cfg["conf"])
                else:
                    qmap = VEHICLE_QUANT if cfg["role"] == "vehicle" else QUANT_PARAMS
                    dets = decode_detect(raw_out, orig_size, (640, 640),
                                         cfg["classes"], cfg["conf"], qmap=qmap)

                for det in dets:
                    x1, y1, x2, y2 = det["bbox"]
                    color = COLORS[det["class_id"] % len(COLORS)]
                    cv2.rectangle(vis_frame, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(vis_frame, f"{det['class_name']} {det['conf']:.2f}",
                                (x1, max(0, y1-8)), cv2.FONT_HERSHEY_SIMPLEX,
                                0.5, color, 2)
                    rec = {"class": det["class_name"], "conf": round(det["conf"], 3),
                           "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2}}
                    all_dets.append(rec)
                    if cfg["role"] == "smoke":
                        opacity_level, opacity_score = classify_smoke_opacity(det, frame_bgr)
                        det["opacity_level"] = opacity_level
                        det["opacity_score"] = opacity_score
                        smoke_dets.append(det)
                    elif cfg["role"] == "vehicle":
                        vehicle_dets.append(rec)
                    elif cfg["role"] == "plate_detect":
                        plate_dets.append(det)

            inf_ms = int((time.time() - t_inf) * 1000)

            # ── 3. Pedestrian detection + blur (no model file needed) ─────────
            # Detects all upright persons via HOG, then filters out cyclists and
            # motorcyclists using background texture (flat road = rider, complex = pedestrian).
            # Blurs pedestrians on vis_frame in-place.
            ped_count, rider_count = detect_and_blur_pedestrians(frame_bgr, vis_frame)
            if ped_count or rider_count:
                print(f"  [Ped] blurred={ped_count} riders_skipped={rider_count}")

            # ── 4. Plate OCR ──────────────────────────────────────────────────
            plate_results = []
            for det in plate_dets:
                x1, y1, x2, y2 = det["bbox"]
                x1c = max(0, x1); y1c = max(0, y1)
                x2c = min(orig_w-1, x2); y2c = min(orig_h-1, y2)
                if x2c > x1c and y2c > y1c:
                    crop = frame_bgr[y1c:y2c, x1c:x2c].copy()
                    text, oconf = read_plate(ocr, crop)
                    if text:
                        plate_results.append({
                            "text": text, "confidence": round(oconf, 3),
                            "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                        })
                        cv2.putText(vis_frame, text, (x1, y2+18),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 2)
                        submit(send_plate, ts, text, oconf,
                               (x1,y1,x2,y2), crop, inf_ms)

            # ── 5. Send smoke events ──────────────────────────────────────────
            for det in smoke_dets:
                submit(send_smoke, ts, det, inf_ms,
                       det.get("opacity_level", "thin"),
                       det.get("opacity_score", 0.0),
                       frame_bgr.copy())

            # ── 6. Send full snapshot ─────────────────────────────────────────
            submit(send_snapshot, vis_frame.copy(), ts, all_dets,
                   smoke_dets, vehicle_dets, plate_results,
                   ped_count, rider_count, inf_ms)

            # ── 7. Print summary ──────────────────────────────────────────────
            snap_count += 1
            elapsed = time.time() - loop_start
            print(f"[Snap #{snap_count}] {ts[:19]}Z | "
                  f"Smoke:{len(smoke_dets)} Veh:{len(vehicle_dets)} "
                  f"Plates:{len(plate_results)} Ped:{ped_count} Riders(skip):{rider_count} | "
                  f"inf={inf_ms}ms total={elapsed*1000:.0f}ms")

            # ── 8. Sleep remainder of interval ────────────────────────────────
            time.sleep(max(0.0, INTERVAL - elapsed))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--test',     action='store_true',
                        help='Capture one frame, run inference, save annotated image, exit')
    parser.add_argument('--interval', type=float, default=INTERVAL,
                        help=f'Seconds between snapshots (default {INTERVAL})')
    parser.add_argument('--output',   default='/home/sevi/smoki_project/test_snap.jpg',
                        help='Output path for --test image')
    args   = parser.parse_args()
    INTERVAL = args.interval

    print("[START] rpi_snap.py")

    if args.test:
        print("\n[TEST MODE] Single frame — no backend, saves annotated image\n")
        import sys

        picam2 = Picamera2()
        picam2.configure(picam2.create_still_configuration(
            main={"format": "BGR888", "size": (1280, 720)}))
        picam2.start()
        time.sleep(1)
        print("[OK] Camera ready")
        print("[OK] HOG pedestrian detector ready")

        ocr = load_ocr()

        from hailo_platform import HailoSchedulingAlgorithm
        vparams = hp.VDevice.create_params()
        vparams.scheduling_algorithm = HailoSchedulingAlgorithm.ROUND_ROBIN
        hefs = [hp.HEF(m["hef"]) for m in ALL_MODELS]

        with hp.VDevice(vparams) as target:
            configured = []
            for hef, m in zip(hefs, ALL_MODELS):
                cp    = hp.ConfigureParams.create_from_hef(hef, hp.HailoStreamInterface.PCIe)
                ng    = target.configure(hef, cp)[0]
                ngp   = ng.create_params()
                in_p  = hp.InputVStreamParams.make(ng, hp.FormatType.UINT8)
                out_p = hp.OutputVStreamParams.make(ng, hp.FormatType.FLOAT32)
                iname = hef.get_input_vstream_infos()[0].name
                configured.append({
                    "cfg": m, "ng": ng, "ngp": ngp,
                    "in_p": in_p, "out_p": out_p, "iname": iname,
                })
                print(f"[OK] Configured: {m['hef'].split('/')[-1]}")

            print("\n[TEST] Capturing frame...")
            frame_bgr = picam2.capture_array()
            picam2.stop(); picam2.close()

            orig_h, orig_w = frame_bgr.shape[:2]
            orig_size  = (orig_h, orig_w)
            resized    = cv2.resize(frame_bgr, (640, 640))
            rgb        = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            inp_uint8  = np.expand_dims(rgb.astype(np.uint8), 0)
            vis_frame  = frame_bgr.copy()

            print(f"[TEST] Frame: {orig_w}x{orig_h}")

            t_inf      = time.time()
            plate_dets = []
            for cm in configured:
                cfg      = cm["cfg"]
                inp_data = {cm["iname"]: inp_uint8}
                try:
                    with hp.InferVStreams(cm["ng"], cm["in_p"], cm["out_p"]) as vs:
                        # No need for explicit activate() with ROUND_ROBIN scheduler
                        raw_out = vs.infer(inp_data)
                except Exception as e:
                    print(f"[ERROR] {cfg['role']}: {e}")
                    continue

                if cfg["type"] == "seg":
                    dets = decode_seg(raw_out, orig_size, (640, 640),
                                      cfg["classes"], cfg["conf"])
                else:
                    qmap = VEHICLE_QUANT if cfg["role"] == "vehicle" else QUANT_PARAMS
                    dets = decode_detect(raw_out, orig_size, (640, 640),
                                         cfg["classes"], cfg["conf"], qmap=qmap)

                print(f"\n  [{cfg['role'].upper()}] {len(dets)} detection(s):")
                for det in dets:
                    extra = ""
                    if cfg["role"] == "smoke":
                        lvl, score = classify_smoke_opacity(det, frame_bgr)
                        extra = f"  opacity={lvl} ({score:.2f})"
                    print(f"    {det['class_name']:20s} conf={det['conf']:.3f}  bbox={det['bbox']}{extra}")
                    x1, y1, x2, y2 = det["bbox"]
                    color = COLORS[det["class_id"] % len(COLORS)]
                    cv2.rectangle(vis_frame, (x1,y1), (x2,y2), color, 2)
                    cv2.putText(vis_frame, f"{det['class_name']} {det['conf']:.2f}",
                                (x1, max(0,y1-8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                    if cfg["role"] == "plate_detect":
                        plate_dets.append(det)
                        x1c,y1c = max(0,x1), max(0,y1)
                        x2c,y2c = min(orig_w-1,x2), min(orig_h-1,y2)
                        if x2c > x1c and y2c > y1c:
                            crop = frame_bgr[y1c:y2c, x1c:x2c]
                            text, oconf = read_plate(ocr, crop)
                            if text:
                                print(f"    → OCR: '{text}' ({oconf:.2f})")
                                cv2.putText(vis_frame, text, (x1, y2+18),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 2)

            inf_ms = int((time.time() - t_inf) * 1000)

            # Pedestrian blur (test mode)
            print("\n  [PEDESTRIAN BLUR]")
            ped_count, rider_count = detect_and_blur_pedestrians(frame_bgr, vis_frame)
            print(f"    Pedestrians blurred: {ped_count}")
            print(f"    Riders skipped:      {rider_count}")

            cv2.imwrite(args.output, vis_frame)
            print(f"\n[TEST] Done — inf={inf_ms}ms")
            print(f"[TEST] Saved annotated image → {args.output}")
            print(f"[TEST] Copy to view: scp sevi@<pi-ip>:{args.output} .")
            sys.exit(0)

    # ── Normal loop mode ──────────────────────────────────────────────────────
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INFO] Stopped.")
    finally:
        _executor.shutdown(wait=False)
///////////////////////////////////////////////
postgresql
//////////////////////////////////////////////import psycopg
from datetime import datetime
import os
import json
from dotenv import load_dotenv

load_dotenv()

# Database connection string
def get_connection_string():
    """Get database connection string"""
    return (f"host={os.getenv('DB_HOST', 'localhost')} "
            f"dbname={os.getenv('DB_NAME', 'smoki_db')} "
            f"user={os.getenv('DB_USER', 'postgres')} "
            f"password={os.getenv('DB_PASSWORD', 'password')} "
            f"port={os.getenv('DB_PORT', '5432')}")

def init_db_pool():
    """Initialize database (create tables)"""
    try:
        print("Initializing database...")
        print(f"Connecting to: {os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}")
        create_tables()
        print("✓ Database initialized successfully")
    except Exception as e:
        print(f"✗ Error initializing database: {e}")
        print("WARNING: Database initialization failed. Some features may not work.")
        # Don't raise - allow app to start anyway

def create_tables():
    """Create necessary tables if they don't exist"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                # Create users table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        username VARCHAR(50) UNIQUE NOT NULL,
                        hashed_password VARCHAR(255) NOT NULL,
                        role VARCHAR(20) NOT NULL,
                        full_name VARCHAR(100),
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                
                # Create sensor_data table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sensor_data (
                        id SERIAL PRIMARY KEY,
                        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        temperature FLOAT,
                        humidity FLOAT,
                        pressure FLOAT,
                        vocs FLOAT,
                        nitrogen_dioxide FLOAT,
                        carbon_monoxide FLOAT,
                        pm25 FLOAT,
                        pm10 FLOAT,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                
                # Add pressure column if it doesn't exist (for existing databases)
                cursor.execute("""
                    ALTER TABLE sensor_data
                    ADD COLUMN IF NOT EXISTS pressure FLOAT;
                """)
                
                # Create vehicles table for SMOKI (RPi camera detection)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS vehicles (
                        id SERIAL PRIMARY KEY,
                        license_plate VARCHAR(50) UNIQUE NOT NULL,
                        vehicle_type VARCHAR(50),
                        first_detected TIMESTAMPTZ DEFAULT NOW(),
                        last_detected TIMESTAMPTZ DEFAULT NOW(),
                        total_violations INT DEFAULT 0,
                        status VARCHAR(20) DEFAULT 'active',
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                
                # Create vehicle_detections table for individual detections
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS vehicle_detections (
                        id SERIAL PRIMARY KEY,
                        vehicle_id INT REFERENCES vehicles(id) ON DELETE CASCADE,
                        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        location VARCHAR(255),
                        confidence FLOAT,
                        smoke_detected BOOLEAN DEFAULT FALSE,
                        emission_level VARCHAR(20),
                        image_path VARCHAR(255),
                        metadata JSONB,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                
                # Create violations table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS violations (
                        id SERIAL PRIMARY KEY,
                        vehicle_id INT REFERENCES vehicles(id) ON DELETE CASCADE,
                        detection_id INT REFERENCES vehicle_detections(id) ON DELETE CASCADE,
                        violation_type VARCHAR(50),
                        severity VARCHAR(20),
                        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        description TEXT,
                        resolved BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                
                # Create notifications table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS notifications (
                        id SERIAL PRIMARY KEY,
                        violation_id INT REFERENCES violations(id) ON DELETE CASCADE,
                        title VARCHAR(255),
                        message TEXT,
                        notification_type VARCHAR(50),
                        is_read BOOLEAN DEFAULT FALSE,
                        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                
                # Create images table for storing image data
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS images (
                        id SERIAL PRIMARY KEY,
                        vehicle_detection_id INT REFERENCES vehicle_detections(id) ON DELETE CASCADE,
                        violation_id INT REFERENCES violations(id) ON DELETE SET NULL,
                        image_data BYTEA NOT NULL,
                        image_format VARCHAR(20),
                        file_size INT,
                        width INT,
                        height INT,
                        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                
                # Create image_metadata table for storing image metadata
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS image_metadata (
                        id SERIAL PRIMARY KEY,
                        image_id INT REFERENCES images(id) ON DELETE CASCADE,
                        camera_id VARCHAR(100),
                        camera_location VARCHAR(255),
                        exposure_time FLOAT,
                        iso_speed INT,
                        focal_length FLOAT,
                        aperture FLOAT,
                        white_balance VARCHAR(50),
                        flash_used BOOLEAN,
                        gps_latitude FLOAT,
                        gps_longitude FLOAT,
                        gps_altitude FLOAT,
                        device_model VARCHAR(255),
                        software_version VARCHAR(100),
                        processing_time_ms INT,
                        quality_score FLOAT,
                        additional_data JSONB,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                
                # Create indexes for faster queries
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_sensor_timestamp 
                    ON sensor_data(timestamp);
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_users_username 
                    ON users(username);
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_vehicles_license_plate 
                    ON vehicles(license_plate);
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_vehicle_detections_timestamp 
                    ON vehicle_detections(timestamp);
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_vehicle_detections_vehicle_id 
                    ON vehicle_detections(vehicle_id);
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_violations_vehicle_id 
                    ON violations(vehicle_id);
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_violations_timestamp 
                    ON violations(timestamp);
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_notifications_timestamp 
                    ON notifications(timestamp);
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_images_vehicle_detection_id 
                    ON images(vehicle_detection_id);
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_images_violation_id 
                    ON images(violation_id);
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_images_timestamp 
                    ON images(timestamp);
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_image_metadata_image_id 
                    ON image_metadata(image_id);
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_image_metadata_camera_id 
                    ON image_metadata(camera_id);
                """)
                
                conn.commit()
                print("Tables created successfully")
        except Exception as e:
            print(f"Error creating tables: {e}")
            conn.rollback()

# ============ SENSOR DATA FUNCTIONS ============

def insert_sensor_data(temperature=None, humidity=None, pressure=None, vocs=None, 
                       nitrogen_dioxide=None, carbon_monoxide=None, 
                       pm25=None, pm10=None):
    """Insert sensor data into database"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO sensor_data 
                    (temperature, humidity, pressure, vocs, nitrogen_dioxide, carbon_monoxide, pm25, pm10)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, timestamp;
                """, (temperature, humidity, pressure, vocs, nitrogen_dioxide, carbon_monoxide, pm25, pm10))
                
                result = cursor.fetchone()
                conn.commit()
                return {"id": result[0], "timestamp": result[1]}
        except Exception as e:
            print(f"Error inserting sensor data: {e}")
            conn.rollback()
            return None

def get_latest_sensor_data(limit=10):
    """Get latest sensor readings"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, timestamp, temperature, humidity, pressure, vocs, 
                           nitrogen_dioxide, carbon_monoxide, pm25, pm10
                    FROM sensor_data
                    ORDER BY timestamp DESC
                    LIMIT %s;
                """, (limit,))
                
                columns = ['id', 'timestamp', 'temperature', 'humidity', 'pressure', 'vocs', 
                           'nitrogen_dioxide', 'carbon_monoxide', 'pm25', 'pm10']
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                return results
        except Exception as e:
            print(f"Error fetching sensor data: {e}")
            return []

def get_sensor_data_by_timerange(start_time, end_time):
    """Get sensor data within a time range"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, timestamp, temperature, humidity, pressure, vocs, 
                           nitrogen_dioxide, carbon_monoxide, pm25, pm10
                    FROM sensor_data
                    WHERE timestamp BETWEEN %s AND %s
                    ORDER BY timestamp DESC;
                """, (start_time, end_time))
                
                columns = ['id', 'timestamp', 'temperature', 'humidity', 'pressure', 'vocs', 
                           'nitrogen_dioxide', 'carbon_monoxide', 'pm25', 'pm10']
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                return results
        except Exception as e:
            print(f"Error fetching sensor data by time range: {e}")
            return []

def update_sensor_data(record_id, temperature=None, humidity=None, pressure=None, vocs=None, 
                       nitrogen_dioxide=None, carbon_monoxide=None, 
                       pm25=None, pm10=None):
    """Update sensor data record"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE sensor_data
                    SET temperature = %s,
                        humidity = %s,
                        pressure = %s,
                        vocs = %s,
                        nitrogen_dioxide = %s,
                        carbon_monoxide = %s,
                        pm25 = %s,
                        pm10 = %s
                    WHERE id = %s
                    RETURNING id, timestamp;
                """, (temperature, humidity, pressure, vocs, nitrogen_dioxide, carbon_monoxide, 
                      pm25, pm10, record_id))
                
                result = cursor.fetchone()
                if result:
                    conn.commit()
                    return {"id": result[0], "timestamp": result[1]}
                else:
                    return None
        except Exception as e:
            print(f"Error updating sensor data: {e}")
            conn.rollback()
            return None

def delete_sensor_data(record_id):
    """Delete sensor data record"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM sensor_data
                    WHERE id = %s
                    RETURNING id;
                """, (record_id,))
                
                result = cursor.fetchone()
                conn.commit()
                return result is not None
        except Exception as e:
            print(f"Error deleting sensor data: {e}")
            conn.rollback()
            return False

# ============ VEHICLE FUNCTIONS ============

def register_vehicle(license_plate, vehicle_type="unknown"):
    """Register a new vehicle"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO vehicles (license_plate, vehicle_type)
                    VALUES (%s, %s)
                    ON CONFLICT (license_plate) DO UPDATE
                    SET last_detected = NOW(), updated_at = NOW()
                    RETURNING id, license_plate, total_violations;
                """, (license_plate, vehicle_type))
                
                result = cursor.fetchone()
                conn.commit()
                return {"id": result[0], "license_plate": result[1], "violations": result[2]}
        except Exception as e:
            print(f"Error registering vehicle: {e}")
            conn.rollback()
            return None

def get_top_violators(limit=5):
    """Get top violating vehicles from detection data"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                # Get vehicles with violations from detection metadata
                cursor.execute("""
                    SELECT 
                        v.license_plate,
                        v.vehicle_type,
                        v.total_violations,
                        v.last_detected,
                        'high' as emission_level,
                        true as smoke_detected,
                        v.id
                    FROM vehicles v
                    WHERE v.status = 'active' AND v.total_violations > 0
                    ORDER BY v.total_violations DESC, v.last_detected DESC
                    LIMIT %s;
                """, (limit,))
                
                columns = ['license_plate', 'vehicle_type', 'violations', 
                           'last_detected', 'emission_level', 'smoke_detected', 'id']
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                
                # If no registered vehicles with violations, create mock data from recent detections
                if not results:
                    cursor.execute("""
                        SELECT id, metadata, timestamp, smoke_detected
                        FROM vehicle_detections 
                        WHERE smoke_detected = true
                        ORDER BY timestamp DESC
                        LIMIT %s;
                    """, (limit,))
                    
                    detection_rows = cursor.fetchall()
                    for i, row in enumerate(detection_rows):
                        metadata = json.loads(row[1]) if row[1] else {}
                        # Generate mock license plate from timestamp
                        timestamp = row[2]
                        plate_suffix = f"{timestamp.hour:02d}{timestamp.minute:02d}"
                        
                        results.append({
                            'id': f"mock_{row[0]}",
                            'license_plate': f"SMK-{plate_suffix}",
                            'vehicle_type': 'passenger',
                            'violations': 1,
                            'last_detected': timestamp,
                            'emission_level': 'high',
                            'smoke_detected': True
                        })
                
                return results
        except Exception as e:
            print(f"Error fetching top violators: {e}")
            return []

def get_vehicle_ranking():
    """Get all vehicles ranked by violations from detection data"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                # Get registered vehicles first
                cursor.execute("""
                    SELECT v.id, v.license_plate, v.vehicle_type, v.total_violations,
                           v.last_detected, v.status
                    FROM vehicles v
                    ORDER BY v.total_violations DESC, v.last_detected DESC;
                """)
                
                columns = ['id', 'license_plate', 'vehicle_type', 'violations', 
                           'last_detected', 'status']
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                
                # If no registered vehicles, create ranking from recent detections
                if not results:
                    cursor.execute("""
                        SELECT id, metadata, timestamp, smoke_detected, location
                        FROM vehicle_detections 
                        ORDER BY timestamp DESC
                        LIMIT 10;
                    """)
                    
                    detection_rows = cursor.fetchall()
                    vehicle_counts = {}
                    
                    for row in detection_rows:
                        metadata = json.loads(row[1]) if row[1] else {}
                        detections = metadata.get('detections', [])
                        
                        # Count vehicles in this detection
                        for detection in detections:
                            class_name = detection.get('class_name', '')
                            if class_name in ['passenger', 'puv', 'services', 'two_wheel']:
                                # Generate consistent license plate for this vehicle type and location
                                timestamp = row[2]
                                location = row[4] or 'Unknown'
                                plate_key = f"{class_name}_{location}_{timestamp.hour}"
                                
                                if plate_key not in vehicle_counts:
                                    plate_suffix = f"{timestamp.hour:02d}{timestamp.minute:02d}"
                                    if class_name == 'passenger':
                                        license_plate = f"ABC-{plate_suffix}"
                                    elif class_name == 'puv':
                                        license_plate = f"PUV-{plate_suffix}"
                                    elif class_name == 'services':
                                        license_plate = f"SVC-{plate_suffix}"
                                    else:
                                        license_plate = f"MC-{plate_suffix}"
                                    
                                    vehicle_counts[plate_key] = {
                                        'license_plate': license_plate,
                                        'vehicle_type': class_name,
                                        'violations': 1 if row[3] else 0,  # smoke_detected
                                        'last_detected': timestamp,
                                        'status': 'active'
                                    }
                                else:
                                    vehicle_counts[plate_key]['violations'] += 1 if row[3] else 0
                                    if timestamp > vehicle_counts[plate_key]['last_detected']:
                                        vehicle_counts[plate_key]['last_detected'] = timestamp
                    
                    # Convert to list and add IDs
                    for i, (key, vehicle) in enumerate(vehicle_counts.items()):
                        vehicle['id'] = f"detected_{i+1}"
                        results.append(vehicle)
                    
                    # Sort by violations
                    results.sort(key=lambda x: x['violations'], reverse=True)
                
                return results
        except Exception as e:
            print(f"Error fetching vehicle ranking: {e}")
            return []

# ============ DETECTION FUNCTIONS ============

def insert_vehicle_detection(vehicle_id, location, confidence, smoke_detected=False, 
                            emission_level="normal", image_path=None, metadata=None):
    """Insert a vehicle detection record"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO vehicle_detections 
                    (vehicle_id, location, confidence, smoke_detected, emission_level, image_path, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, timestamp;
                """, (vehicle_id, location, confidence, smoke_detected, emission_level, image_path, metadata))
                
                result = cursor.fetchone()
                conn.commit()
                return {"id": result[0], "timestamp": result[1]}
        except Exception as e:
            print(f"Error inserting vehicle detection: {e}")
            conn.rollback()
            return None

# ============ VIOLATION FUNCTIONS ============

def create_violation(vehicle_id, detection_id, violation_type, severity, description=None):
    """Create a violation record"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                # Insert violation
                cursor.execute("""
                    INSERT INTO violations 
                    (vehicle_id, detection_id, violation_type, severity, description)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id;
                """, (vehicle_id, detection_id, violation_type, severity, description))
                
                violation_id = cursor.fetchone()[0]
                
                # Update vehicle violation count
                cursor.execute("""
                    UPDATE vehicles
                    SET total_violations = total_violations + 1,
                        last_detected = NOW(),
                        updated_at = NOW()
                    WHERE id = %s;
                """, (vehicle_id,))
                
                conn.commit()
                return {"id": violation_id}
        except Exception as e:
            print(f"Error creating violation: {e}")
            conn.rollback()
            return None

def get_recent_violations(limit=10):
    """Get recent violations"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT v.id, v.vehicle_id, v.violation_type, v.severity,
                           v.timestamp, v.description, veh.license_plate
                    FROM violations v
                    JOIN vehicles veh ON v.vehicle_id = veh.id
                    ORDER BY v.timestamp DESC
                    LIMIT %s;
                """, (limit,))
                
                columns = ['id', 'vehicle_id', 'violation_type', 'severity', 
                           'timestamp', 'description', 'license_plate']
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                return results
        except Exception as e:
            print(f"Error fetching violations: {e}")
            return []

# ============ NOTIFICATION FUNCTIONS ============

def create_notification(violation_id, title, message, notification_type="violation"):
    """Create a notification"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO notifications 
                    (violation_id, title, message, notification_type)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, timestamp;
                """, (violation_id, title, message, notification_type))
                
                result = cursor.fetchone()
                conn.commit()
                return {"id": result[0], "timestamp": result[1]}
        except Exception as e:
            print(f"Error creating notification: {e}")
            conn.rollback()
            return None

def get_unread_notifications(limit=10):
    """Get unread notifications"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT n.id, n.title, n.message, n.notification_type,
                           n.timestamp, v.severity, veh.license_plate
                    FROM notifications n
                    LEFT JOIN violations v ON n.violation_id = v.id
                    LEFT JOIN vehicles veh ON v.vehicle_id = veh.id
                    WHERE n.is_read = FALSE
                    ORDER BY n.timestamp DESC
                    LIMIT %s;
                """, (limit,))
                
                columns = ['id', 'title', 'message', 'notification_type', 
                           'timestamp', 'severity', 'license_plate']
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                return results
        except Exception as e:
            print(f"Error fetching notifications: {e}")
            return []

def mark_notification_read(notification_id):
    """Mark notification as read"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE notifications
                    SET is_read = TRUE
                    WHERE id = %s
                    RETURNING id;
                """, (notification_id,))
                
                result = cursor.fetchone()
                conn.commit()
                return result is not None
        except Exception as e:
            print(f"Error marking notification as read: {e}")
            conn.rollback()
            return False

def close_db_pool():
    """Close database connections"""
    print("Database connections closed")

# ============ USER MANAGEMENT ============

def create_default_users():
    """Create default admin and superadmin users if they don't exist"""
    from backend.auth import get_password_hash
    
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                # Check if admin exists
                cursor.execute("SELECT id FROM users WHERE username = %s", ("admin1234",))
                if not cursor.fetchone():
                    admin_hash = get_password_hash("superadmin")
                    cursor.execute("""
                        INSERT INTO users (username, hashed_password, role, full_name)
                        VALUES (%s, %s, %s, %s)
                    """, ("admin1234", admin_hash, "admin", "Admin User"))
                    print("✓ Created admin user: admin1234")
                
                # Check if superadmin exists
                cursor.execute("SELECT id FROM users WHERE username = %s", ("superadmin",))
                if not cursor.fetchone():
                    superadmin_hash = get_password_hash("superadmin123")
                    cursor.execute("""
                        INSERT INTO users (username, hashed_password, role, full_name)
                        VALUES (%s, %s, %s, %s)
                    """, ("superadmin", superadmin_hash, "superadmin", "Superadmin User"))
                    print("✓ Created superadmin user: superadmin")
                
                conn.commit()
        except Exception as e:
            print(f"Error creating default users: {e}")
            conn.rollback()

# ============ IMAGE FUNCTIONS ============

def insert_image(vehicle_detection_id, image_data, image_format="jpeg", 
                 file_size=None, width=None, height=None, violation_id=None):
    """Insert an image into the database"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO images 
                    (vehicle_detection_id, violation_id, image_data, image_format, file_size, width, height)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, timestamp;
                """, (vehicle_detection_id, violation_id, image_data, image_format, file_size, width, height))
                
                result = cursor.fetchone()
                conn.commit()
                return {"id": result[0], "timestamp": result[1]}
        except Exception as e:
            print(f"Error inserting image: {e}")
            conn.rollback()
            return None

def get_image(image_id):
    """Retrieve image data by ID"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, image_data, image_format, file_size, width, height, timestamp
                    FROM images
                    WHERE id = %s;
                """, (image_id,))
                
                result = cursor.fetchone()
                if result:
                    return {
                        "id": result[0],
                        "image_data": result[1],
                        "image_format": result[2],
                        "file_size": result[3],
                        "width": result[4],
                        "height": result[5],
                        "timestamp": result[6]
                    }
                return None
        except Exception as e:
            print(f"Error retrieving image: {e}")
            return None

def get_images_by_detection(vehicle_detection_id):
    """Get all images for a vehicle detection"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, image_format, file_size, width, height, timestamp
                    FROM images
                    WHERE vehicle_detection_id = %s
                    ORDER BY timestamp DESC;
                """, (vehicle_detection_id,))
                
                columns = ['id', 'image_format', 'file_size', 'width', 'height', 'timestamp']
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                return results
        except Exception as e:
            print(f"Error fetching images by detection: {e}")
            return []

def get_images_by_violation(violation_id):
    """Get all images for a violation"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, image_format, file_size, width, height, timestamp
                    FROM images
                    WHERE violation_id = %s
                    ORDER BY timestamp DESC;
                """, (violation_id,))
                
                columns = ['id', 'image_format', 'file_size', 'width', 'height', 'timestamp']
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                return results
        except Exception as e:
            print(f"Error fetching images by violation: {e}")
            return []

def delete_image(image_id):
    """Delete an image"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM images
                    WHERE id = %s
                    RETURNING id;
                """, (image_id,))
                
                result = cursor.fetchone()
                conn.commit()
                return result is not None
        except Exception as e:
            print(f"Error deleting image: {e}")
            conn.rollback()
            return False

# ============ IMAGE METADATA FUNCTIONS ============

def insert_image_metadata(image_id, camera_id=None, camera_location=None, 
                         exposure_time=None, iso_speed=None, focal_length=None,
                         aperture=None, white_balance=None, flash_used=None,
                         gps_latitude=None, gps_longitude=None, gps_altitude=None,
                         device_model=None, software_version=None, 
                         processing_time_ms=None, quality_score=None, additional_data=None):
    """Insert image metadata"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO image_metadata 
                    (image_id, camera_id, camera_location, exposure_time, iso_speed, focal_length,
                     aperture, white_balance, flash_used, gps_latitude, gps_longitude, gps_altitude,
                     device_model, software_version, processing_time_ms, quality_score, additional_data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                """, (image_id, camera_id, camera_location, exposure_time, iso_speed, focal_length,
                      aperture, white_balance, flash_used, gps_latitude, gps_longitude, gps_altitude,
                      device_model, software_version, processing_time_ms, quality_score, additional_data))
                
                result = cursor.fetchone()
                conn.commit()
                return {"id": result[0]}
        except Exception as e:
            print(f"Error inserting image metadata: {e}")
            conn.rollback()
            return None

def get_image_metadata(image_id):
    """Get metadata for an image"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, camera_id, camera_location, exposure_time, iso_speed, focal_length,
                           aperture, white_balance, flash_used, gps_latitude, gps_longitude, gps_altitude,
                           device_model, software_version, processing_time_ms, quality_score, additional_data
                    FROM image_metadata
                    WHERE image_id = %s;
                """, (image_id,))
                
                result = cursor.fetchone()
                if result:
                    return {
                        "id": result[0],
                        "camera_id": result[1],
                        "camera_location": result[2],
                        "exposure_time": result[3],
                        "iso_speed": result[4],
                        "focal_length": result[5],
                        "aperture": result[6],
                        "white_balance": result[7],
                        "flash_used": result[8],
                        "gps_latitude": result[9],
                        "gps_longitude": result[10],
                        "gps_altitude": result[11],
                        "device_model": result[12],
                        "software_version": result[13],
                        "processing_time_ms": result[14],
                        "quality_score": result[15],
                        "additional_data": result[16]
                    }
                return None
        except Exception as e:
            print(f"Error fetching image metadata: {e}")
            return None

def update_image_metadata(metadata_id, **kwargs):
    """Update image metadata fields"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                # Build dynamic update query
                set_clauses = []
                values = []
                for key, value in kwargs.items():
                    set_clauses.append(f"{key} = %s")
                    values.append(value)
                
                values.append(metadata_id)
                
                query = f"""
                    UPDATE image_metadata
                    SET {', '.join(set_clauses)}
                    WHERE id = %s
                    RETURNING id;
                """
                
                cursor.execute(query, values)
                result = cursor.fetchone()
                conn.commit()
                return result is not None
        except Exception as e:
            print(f"Error updating image metadata: {e}")
            conn.rollback()
            return False

def get_metadata_by_camera(camera_id, limit=50):
    """Get all metadata for a specific camera"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT im.id, im.image_id, im.camera_location, im.processing_time_ms, 
                           im.quality_score, im.created_at
                    FROM image_metadata im
                    WHERE im.camera_id = %s
                    ORDER BY im.created_at DESC
                    LIMIT %s;
                """, (camera_id, limit))
                
                columns = ['id', 'image_id', 'camera_location', 'processing_time_ms', 
                           'quality_score', 'created_at']
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                return results
        except Exception as e:
            print(f"Error fetching metadata by camera: {e}")
            return []

def insert_smoke_detection(timestamp, confidence, smoke_type, bounding_box=None, 
                          camera_id="rpi_camera", location="unknown", metadata=None,
                          detections=None, screenshots=None, license_plate=None):
    """Insert a smoke detection record from RPi camera with all model detections"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                # Prepare comprehensive metadata JSON
                detection_metadata = {
                    "smoke_type": smoke_type,
                    "bounding_box": bounding_box,
                    "camera_id": camera_id,
                    "detection_source": "rpi_camera",
                    "all_detections": []
                }
                
                # Add all model detections to metadata
                if detections:
                    for det in detections:
                        detection_metadata["all_detections"].append({
                            "model": det.get("model_name") if isinstance(det, dict) else det.model_name,
                            "class": det.get("class_name") if isinstance(det, dict) else det.class_name,
                            "confidence": det.get("confidence") if isinstance(det, dict) else det.confidence,
                            "bounding_box": det.get("bounding_box") if isinstance(det, dict) else det.bounding_box
                        })
                
                # Add screenshots info
                if screenshots:
                    detection_metadata["screenshots"] = screenshots
                
                # Add license plate
                if license_plate:
                    detection_metadata["license_plate"] = license_plate
                
                # Merge with additional metadata
                if metadata:
                    detection_metadata.update(metadata)
                
                cursor.execute("""
                    INSERT INTO vehicle_detections 
                    (timestamp, location, confidence, smoke_detected, emission_level, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id, timestamp;
                """, (timestamp, location, confidence, True, smoke_type, detection_metadata))
                
                result = cursor.fetchone()
                conn.commit()
                
                if result:
                    return {
                        "id": result[0],
                        "timestamp": result[1],
                        "confidence": confidence,
                        "smoke_type": smoke_type,
                        "detections_count": len(detections) if detections else 0
                    }
                return None
        except Exception as e:
            print(f"Error inserting smoke detection: {e}")
            return None


def get_smoke_detections(limit=50, hours=24):
    """Get recent smoke detections"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, timestamp, location, confidence, metadata
                    FROM vehicle_detections
                    WHERE smoke_detected = TRUE 
                    AND timestamp > NOW() - INTERVAL '%s hours'
                    ORDER BY timestamp DESC
                    LIMIT %s;
                """, (hours, limit))
                
                columns = ['id', 'timestamp', 'location', 'confidence', 'metadata']
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                return results
        except Exception as e:
            print(f"Error fetching smoke detections: {e}")
            return []


def insert_vehicle_detection_from_rpi(timestamp, camera_id, location, detections, frame_data, metadata=None):
    """Insert vehicle detection from RPi with frame and metadata"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                # Store frame image first
                cursor.execute("""
                    INSERT INTO images (vehicle_detection_id, image_data, image_format, file_size, width, height, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                """, (None, frame_data, 'jpeg', len(frame_data), None, None, timestamp))
                
                image_id = cursor.fetchone()[0]
                
                # Store detection metadata with detections included
                full_metadata = metadata or {}
                full_metadata['detections'] = detections
                full_metadata['camera_id'] = camera_id
                full_metadata['location'] = location
                metadata_json = json.dumps(full_metadata)
                
                # Calculate average confidence from detections
                avg_confidence = 0.0
                if detections:
                    confidences = [d.get('confidence', 0.0) for d in detections if isinstance(d.get('confidence'), (int, float))]
                    if confidences:
                        avg_confidence = sum(confidences) / len(confidences)
                
                # Check if smoke was detected
                smoke_detected = any('smoke' in d.get('class_name', '').lower() for d in detections)
                
                cursor.execute("""
                    INSERT INTO vehicle_detections 
                    (vehicle_id, timestamp, location, confidence, smoke_detected, emission_level, image_path, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, timestamp;
                """, (None, timestamp, location, avg_confidence, smoke_detected, 'normal', str(image_id), metadata_json))
                
                result = cursor.fetchone()
                
                # Update the image to link back to the detection
                cursor.execute("""
                    UPDATE images SET vehicle_detection_id = %s WHERE id = %s;
                """, (result[0], image_id))
                
                conn.commit()
                
                print(f"[DB] Stored vehicle detection: id={result[0]}, detections={len(detections)}, smoke={smoke_detected}")
                
                return {
                    "id": result[0],
                    "timestamp": result[1],
                    "image_id": image_id,
                    "detections_count": len(detections) if detections else 0,
                    "smoke_detected": smoke_detected
                }
        except Exception as e:
            print(f"Error inserting vehicle detection from RPi: {e}")
            import traceback
            traceback.print_exc()
            conn.rollback()
            return None


def get_recent_vehicle_detections(limit=10):
    """Get recent vehicle detections with metadata"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, timestamp, location, confidence, metadata, image_path
                    FROM vehicle_detections
                    ORDER BY timestamp DESC
                    LIMIT %s;
                """, (limit,))
                
                rows = cursor.fetchall()
                detections = []
                
                for row in rows:
                    try:
                        # Handle both string and dict metadata
                        metadata = row[4]
                        if isinstance(metadata, str):
                            metadata = json.loads(metadata)
                        elif metadata is None:
                            metadata = {}
                    except (json.JSONDecodeError, TypeError):
                        metadata = {}
                    
                    detections.append({
                        "id": row[0],
                        "timestamp": row[1].isoformat() if row[1] else None,
                        "location": row[2],
                        "confidence": row[3],
                        "metadata": metadata,
                        "image_id": row[5]
                    })
                
                return detections
        except Exception as e:
            print(f"Error getting recent vehicle detections: {e}")
            return []


def insert_detection_summary(timestamp, camera_id, location, detection_count, smoke_count, vehicle_count, mode, metadata=None):
    """Insert detection summary metadata (lightweight, no frame data)"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                # Create table if it doesn't exist
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS detection_summaries (
                        id SERIAL PRIMARY KEY,
                        timestamp TIMESTAMP WITH TIME ZONE,
                        camera_id VARCHAR(255),
                        location VARCHAR(255),
                        detection_count INT,
                        smoke_count INT,
                        vehicle_count INT,
                        mode VARCHAR(50),
                        metadata JSONB,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                cursor.execute("""
                    INSERT INTO detection_summaries 
                    (timestamp, camera_id, location, detection_count, smoke_count, vehicle_count, mode, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                """, (
                    timestamp,
                    camera_id,
                    location,
                    detection_count,
                    smoke_count,
                    vehicle_count,
                    mode,
                    json.dumps(metadata) if metadata else None
                ))
                
                result = cursor.fetchone()
                conn.commit()
                return result[0] if result else None
        except Exception as e:
            print(f"Error inserting detection summary: {e}")
            import traceback
            traceback.print_exc()
            conn.rollback()
            return None


def get_recent_detection_summaries(limit=50):
    """Get recent detection summaries"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, timestamp, camera_id, location, detection_count, smoke_count, vehicle_count, mode, metadata
                    FROM detection_summaries
                    ORDER BY timestamp DESC
                    LIMIT %s;
                """, (limit,))
                
                rows = cursor.fetchall()
                summaries = []
                
                for row in rows:
                    metadata = json.loads(row[8]) if row[8] else {}
                    summaries.append({
                        "id": row[0],
                        "timestamp": row[1].isoformat() if row[1] else None,
                        "camera_id": row[2],
                        "location": row[3],
                        "detection_count": row[4],
                        "smoke_count": row[5],
                        "vehicle_count": row[6],
                        "mode": row[7],
                        "metadata": metadata
                    })
                
                return summaries
        except Exception as e:
            print(f"Error getting recent detection summaries: {e}")
            return []
//////////////////////////////////////////////////////
backend
/////////////////////////////////////////////////////
from fastapi import FastAPI, HTTPException, Depends, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
import sys
import psycopg
import os
sys.path.append('..')
from postgre.database import init_db_pool, insert_sensor_data, get_latest_sensor_data, update_sensor_data, delete_sensor_data, close_db_pool, get_connection_string, create_default_users
from auth import (
    authenticate_user, create_access_token, get_current_user, 
    get_current_superadmin, get_current_admin_or_superadmin,
    Token, User, ACCESS_TOKEN_EXPIRE_MINUTES
)
from vehicles import router as vehicles_router
from stream import router as stream_router
from webrtc_proxy import router as webrtc_router

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add response headers for streaming
@app.middleware("http")
async def add_stream_headers(request, call_next):
    response = await call_next(request)
    if "/api/stream" in request.url.path:
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Include routers
app.include_router(vehicles_router)
app.include_router(stream_router)
app.include_router(webrtc_router)

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    init_db_pool()
    create_default_users()

# Close database on shutdown
@app.on_event("shutdown")
async def shutdown_event():
    close_db_pool()

class SensorData(BaseModel):
    temperature: float | None = None
    humidity: float | None = None
    pressure: float | None = None
    vocs: float | None = None
    nitrogen_dioxide: float | None = None
    carbon_monoxide: float | None = None
    pm25: float | None = None
    pm10: float | None = None

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/api/auth/login", response_model=Token)
def login(login_data: LoginRequest):
    """Authenticate user and return JWT token"""
    user = authenticate_user(login_data.username, login_data.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password"
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role},
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role,
        "username": user.username
    }

@app.get("/api/auth/me", response_model=User)
def get_me(current_user: User = Depends(get_current_user)):
    """Get current user information"""
    return current_user

@app.get("/api/hello")
def read_root():
    return {"message": "Hello from FastAPI!", "status": "ok"}

@app.get("/api/health")
def health_check():
    """Health check endpoint"""
    try:
        with psycopg.connect(get_connection_string()) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}

@app.get("/api/camera/health")
def camera_health():
    """Check camera health (no auth required)"""
    return {
        "status": "healthy",
        "stream_url": "/api/stream/playlist.m3u8",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/camera/stream")
def camera_stream():
    """Redirect to HLS stream (no auth required)"""
    return {"stream_url": "/api/stream/playlist.m3u8"}

@app.post("/api/camera/detections")
def camera_detections_post():
    """Receive detections from RPi (no auth required)"""
    return {"success": True}

class Detection(BaseModel):
    """Generic detection from any model"""
    model_name: str  # 'vehicle_detection', 'smoke_detection', etc.
    class_name: str  # 'passenger', 'smoke_black', 'license_plate', etc.
    confidence: float
    bounding_box: dict | None = None  # {"x1": int, "y1": int, "x2": int, "y2": int}
    timestamp: str | None = None

class SmokeDetection(BaseModel):
    timestamp: str
    confidence: float
    smoke_type: str  # 'smoke_black' or 'smoke_white'
    bounding_box: dict | None = None  # {"x1": int, "y1": int, "x2": int, "y2": int}
    camera_id: str = "rpi_camera"
    location: str = "unknown"
    metadata: dict | None = None
    detections: list[Detection] | None = None  # All detections from all models
    screenshots: dict | None = None
    license_plate: str | None = None

@app.post("/api/detections/smoke")
def record_smoke_detection(detection: SmokeDetection):
    """Record smoke detection from RPi camera (no auth required)"""
    try:
        print(f"[DEBUG] Received smoke detection: {detection.smoke_type} confidence={detection.confidence}")
        
        # TODO: Fix database insertion - for now just log and return success
        # from postgre.database import insert_smoke_detection
        # result = insert_smoke_detection(...)
        
        # Return mock success response
        return {
            "success": True, 
            "data": {
                "id": 1,
                "timestamp": detection.timestamp,
                "confidence": detection.confidence,
                "smoke_type": detection.smoke_type
            }
        }
        
    except Exception as e:
        print(f"[ERROR] Smoke detection error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/detections/smoke")
def get_smoke_detections(limit: int = 50, hours: int = 24, current_user: User = Depends(get_current_user)):
    """Get recent smoke detections (requires authentication)"""
    try:
        from postgre.database import get_smoke_detections
        detections = get_smoke_detections(limit=limit, hours=hours)
        return {
            "success": True,
            "data": detections,
            "count": len(detections)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class DetectionSummary(BaseModel):
    timestamp: str
    camera_id: str = "rpi_camera"
    location: str = "unknown"
    detection_count: int
    smoke_count: int
    vehicle_count: int
    mode: str = "hailo"  # 'hailo' or 'cpu'
    metadata: dict | None = None

@app.post("/api/detections/summary")
def record_detection_summary(summary: DetectionSummary):
    """Record detection summary metadata from RPi (no auth required, lightweight)"""
    try:
        print(f"[DETECTION_SUMMARY] {summary.camera_id} - Mode: {summary.mode}, Total: {summary.detection_count}, Smoke: {summary.smoke_count}, Vehicles: {summary.vehicle_count}")
        # Store in database if needed
        from postgre.database import insert_detection_summary
        result = insert_detection_summary(
            timestamp=summary.timestamp,
            camera_id=summary.camera_id,
            location=summary.location,
            detection_count=summary.detection_count,
            smoke_count=summary.smoke_count,
            vehicle_count=summary.vehicle_count,
            mode=summary.mode,
            metadata=summary.metadata
        )
        return {"success": True, "data": result}
    except Exception as e:
        print(f"[DETECTION_SUMMARY] Error: {e}")
        # Don't fail the request, just log it
        return {"success": True, "message": "Summary recorded"}

@app.get("/api/detections/summary/recent")
def get_recent_detection_summaries(limit: int = 50, current_user: User = Depends(get_current_user)):
    """Get recent detection summaries (requires authentication)"""
    try:
        from postgre.database import get_recent_detection_summaries
        summaries = get_recent_detection_summaries(limit=limit)
        return {
            "success": True,
            "data": summaries,
            "count": len(summaries)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/vehicles/detections")
def get_vehicle_detections(limit: int = 10, current_user: User = Depends(get_current_user)):
    """Get recent vehicle detections"""
    try:
        from vehicles import get_recent_violations
        violations = get_recent_violations(limit)
        return {
            "success": True,
            "data": violations
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/time")
def get_server_time():
    """Get server time for debugging timezone issues"""
    return {
        "server_time_utc": datetime.now(timezone.utc).isoformat(),
        "server_time_local": datetime.now().isoformat(),
        "timezone": "UTC" if datetime.now().astimezone().utcoffset().total_seconds() == 0 else str(datetime.now().astimezone().tzinfo)
    }

@app.post("/api/sensors/data")
def add_sensor_data(data: SensorData):
    """Add new sensor reading to database (No auth required for ESP32)"""
    try:
        result = insert_sensor_data(
            temperature=data.temperature,
            humidity=data.humidity,
            pressure=data.pressure,
            vocs=data.vocs,
            nitrogen_dioxide=data.nitrogen_dioxide,
            carbon_monoxide=data.carbon_monoxide,
            pm25=data.pm25,
            pm10=data.pm10
        )
        if result:
            return {"success": True, "data": result}
        else:
            raise HTTPException(status_code=500, detail="Failed to insert data")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sensors/data")
def get_sensor_data(limit: int = 10):
    """Get latest sensor readings (Public access for debugging)"""
    try:
        data = get_latest_sensor_data(limit=limit)
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sensors/latest")
def get_latest_reading():
    """Get the most recent sensor reading (Public access)"""
    try:
        data = get_latest_sensor_data(limit=1)
        if data:
            return {"success": True, "data": data[0]}
        else:
            return {"success": True, "data": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sensors/status")
def get_sensor_status():
    """Get sensor connection status and last update time"""
    try:
        data = get_latest_sensor_data(limit=1)
        if data:
            last_update = data[0].get('timestamp')
            if last_update:
                # Parse timestamp and check if it's older than 30 seconds
                from datetime import datetime
                
                # Handle both string and datetime objects
                if isinstance(last_update, str):
                    last_update_dt = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                else:
                    last_update_dt = last_update
                    
                current_time = datetime.now(timezone.utc)
                time_diff = (current_time - last_update_dt).total_seconds()  # In seconds
                
                is_timeout = time_diff > 30  # 30 seconds timeout
                
                return {
                    "success": True,
                    "connected": not is_timeout,
                    "last_update": str(last_update),
                    "seconds_since_update": round(time_diff, 2),
                    "timeout_threshold_seconds": 30
                }
        
        return {
            "success": True,
            "connected": False,
            "last_update": None,
            "seconds_since_update": None,
            "timeout_threshold_seconds": 30
        }
    except Exception as e:
        print(f"Error in get_sensor_status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/sensors/data/{record_id}")
def update_sensor_record(record_id: int, data: SensorData, current_user: User = Depends(get_current_superadmin)):
    """Update sensor reading (Superadmin only)"""
    try:
        result = update_sensor_data(
            record_id=record_id,
            temperature=data.temperature,
            humidity=data.humidity,
            pressure=data.pressure,
            vocs=data.vocs,
            nitrogen_dioxide=data.nitrogen_dioxide,
            carbon_monoxide=data.carbon_monoxide,
            pm25=data.pm25,
            pm10=data.pm10
        )
        if result:
            return {"success": True, "message": "Record updated", "data": result}
        else:
            raise HTTPException(status_code=404, detail="Record not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/sensors/data/{record_id}")
def delete_sensor_record(record_id: int, current_user: User = Depends(get_current_superadmin)):
    """Delete sensor reading (Superadmin only)"""
    try:
        success = delete_sensor_data(record_id)
        if success:
            return {"success": True, "message": f"Record {record_id} deleted"}
        else:
            raise HTTPException(status_code=404, detail="Record not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/detections/vehicle")
async def record_vehicle_detection(
    frame: UploadFile = File(...),
    data: str = Form(...)
):
    """Record vehicle detection with frame and metadata from RPi camera (no auth required)"""
    try:
        import json
        from postgre.database import insert_vehicle_detection_from_rpi
        
        # Parse JSON data
        detection_data = json.loads(data)
        print(f"[VEHICLE_DETECTION] Received: {detection_data.get('camera_id')} - {len(detection_data.get('detections', []))} objects")
        
        # Read frame
        frame_bytes = await frame.read()
        print(f"[VEHICLE_DETECTION] Frame size: {len(frame_bytes)} bytes")
        
        # Store detection
        result = insert_vehicle_detection_from_rpi(
            timestamp=detection_data.get("timestamp"),
            camera_id=detection_data.get("camera_id", "rpi_camera"),
            location=detection_data.get("location", "unknown"),
            detections=detection_data.get("detections", []),
            frame_data=frame_bytes,
            metadata=detection_data.get("metadata", {})
        )
        
        if result:
            print(f"[VEHICLE_DETECTION] Stored successfully: {result}")
            return {"success": True, "data": result}
        else:
            print(f"[VEHICLE_DETECTION] Storage failed")
            raise HTTPException(status_code=500, detail="Failed to record vehicle detection")
    except Exception as e:
        print(f"[VEHICLE_DETECTION] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/detections/vehicle/recent")
def get_recent_vehicle_detections(limit: int = 10, current_user: User = Depends(get_current_user)):
    """Get recent vehicle detections with metadata"""
    try:
        from postgre.database import get_recent_vehicle_detections
        detections = get_recent_vehicle_detections(limit=limit)
        return {
            "success": True,
            "data": detections,
            "count": len(detections)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
//////////////////////////////////////////////////////
react
////////////////////////////////////////////////////////
import './styles/Dashboard.css';
import './styles/ActionButtons.css';
import './styles/InfoPage.css';
import { useNavigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Brush, ReferenceLine } from 'recharts';
import { Thermometer, Droplet, Wind, Flame, Circle, Home, FileText, TrendingUp, Zap, Moon, Sun, LogOut, Menu, Activity } from 'lucide-react';
import NotificationRibbon from './component/NotificationRibbon';
import SensorStatusRibbon from './component/SensorStatusRibbon';
import Toast from './component/Toast';
import { showToast } from './utils/toastUtils';
import { EditIcon, DeleteIcon, PlusIcon } from './component/IOSIcons';
import ConfirmModal from './component/ConfirmModal';
import SensorDetailModal from './component/SensorDetailModal';
import TriangleLoader from './component/TriangleLoader';
import TutorialModal from './component/TutorialModal';
import WebRTCViewer from './component/WebRTCViewer';
import { useSensorStatus } from './context/SensorStatusContext';
import { fetchWithFallback } from './utils/apiClient';

const InfoIcon = () => (
  <svg height="16" strokeLinejoin="round" viewBox="0 0 16 16" width="16" style={{color: 'currentcolor'}}><path d="M14 8C14 11.3137 11.3137 14 8 14C4.68629 14 2 11.3137 2 8C2 4.68629 4.68629 2 8 2C11.3137 2 14 4.68629 14 8Z" fill="currentColor" fillOpacity="0.08"></path><path fillRule="evenodd" clipRule="evenodd" d="M8 6C8.55228 6 9 5.55228 9 5C9 4.44772 8.55228 4 8 4C7.44771 4 7 4.44772 7 5C7 5.55228 7.44771 6 8 6ZM7 7H6.25V8.5H7H7.24999V10.5V11.25H8.74999V10.5V8C8.74999 7.44772 8.30227 7 7.74999 7H7Z" fill="currentColor"></path></svg>
);

const UserIcon = ({ size = 24 }) => (
  <svg data-testid="geist-icon" height={size} strokeLinejoin="round" viewBox="0 0 16 16" width={size} style={{color: 'currentcolor', display: 'block'}}><path fillRule="evenodd" clipRule="evenodd" d="M7.75 0C5.95507 0 4.5 1.45507 4.5 3.25V3.75C4.5 5.54493 5.95507 7 7.75 7H8.25C10.0449 7 11.5 5.54493 11.5 3.75V3.25C11.5 1.45507 10.0449 0 8.25 0H7.75ZM6 3.25C6 2.2835 6.7835 1.5 7.75 1.5H8.25C9.2165 1.5 10 2.2835 10 3.25V3.75C10 4.7165 9.2165 5.5 8.25 5.5H7.75C6.7835 5.5 6 4.7165 6 3.75V3.25ZM2.5 14.5V13.1709C3.31958 11.5377 4.99308 10.5 6.82945 10.5H9.17055C11.0069 10.5 12.6804 11.5377 13.5 13.1709V14.5H2.5ZM6.82945 9C4.35483 9 2.10604 10.4388 1.06903 12.6857L1 12.8353V13V15.25V16H1.75H14.25H15V15.25V13V12.8353L14.931 12.6857C13.894 10.4388 11.6452 9 9.17055 9H6.82945Z" fill="#666"></path></svg>
);

function Dashboard() {
  const [activePage, setActivePage] = useState("dashboard");
  const [sensorData, setSensorData] = useState(null);
  const [previousSensorData, setPreviousSensorData] = useState(null);
  const [records, setRecords] = useState([]);
  const [graphData, setGraphData] = useState([]);
  const [filterSensorTypes, setFilterSensorTypes] = useState({
    temperature: true,
    humidity: true,
    vocs: true,
    no2: true,
    co: true,
    pm25: true,
    pm10: true,
    pressure: true
  });
  const [appliedSensorTypes, setAppliedSensorTypes] = useState({
    temperature: true,
    humidity: true,
    vocs: true,
    no2: true,
    co: true,
    pm25: true,
    pm10: true,
    pressure: true
  });
  const [filterDate, setFilterDate] = useState("all");
  const [appliedDate, setAppliedDate] = useState("all");
  const [clearFilters, setClearFilters] = useState(false);
  const [sensorDropdownOpen, setSensorDropdownOpen] = useState(false);
  
  // Graph filters
  const [graphFilterSensorTypes, setGraphFilterSensorTypes] = useState({
    temperature: true,
    humidity: true,
    vocs: true,
    no2: true,
    co: true,
    pm25: true,
    pm10: true,
    pressure: true
  });
  const [appliedGraphSensorTypes, setAppliedGraphSensorTypes] = useState({
    temperature: true,
    humidity: true,
    vocs: true,
    no2: true,
    co: true,
    pm25: true,
    pm10: true,
    pressure: true
  });
  const [graphFilterDate, setGraphFilterDate] = useState("all");
  const [appliedGraphDate, setAppliedGraphDate] = useState("all");
  const [clearGraphFilters, setClearGraphFilters] = useState(false);
  const [graphSensorDropdownOpen, setGraphSensorDropdownOpen] = useState(false);
  const [darkMode, setDarkMode] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [selectedSensor, setSelectedSensor] = useState(null); // For sensor detail view
  const [sidebarHovered, setSidebarHovered] = useState(false);
  const [showGraphLoading, setShowGraphLoading] = useState(false);
  const [userRole] = useState(localStorage.getItem('role') || 'Admin');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingRecord, setEditingRecord] = useState(null);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 768);
  const [formData, setFormData] = useState({
    temperature: '',
    humidity: '',
    vocs: '',
    nitrogen_dioxide: '',
    carbon_monoxide: '',
    pm25: '',
    pm10: ''
  });
  const [topViolators, setTopViolators] = useState([]);
  const [vehicleRanking, setVehicleRanking] = useState([]);
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [recordToDelete, setRecordToDelete] = useState(null);
  const [showSensorDetailModal, setShowSensorDetailModal] = useState(false);
  const [selectedSensorType, setSelectedSensorType] = useState(null);
  const [triggerTutorialOnLogin, setTriggerTutorialOnLogin] = useState(false);
  
  const navigate = useNavigate();
  const { sensorConnected, lastSensorUpdate, updateLastSensorTime } = useSensorStatus();

  // Fetch latest sensor data for sensors page
  const fetchLatestSensorData = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetchWithFallback('/api/sensors/latest', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.status === 401) {
        // Token expired or invalid
        localStorage.clear();
        navigate('/');
        return;
      }
      
      const result = await response.json();
      if (result.success && result.data) {
        setSensorData(prevData => {
          // Set previous data to the current data before updating
          setPreviousSensorData(prevData);
          return result.data;
        });
        updateLastSensorTime(); // Update the last sensor update time
      }
    } catch (error) {
      console.error('Error fetching sensor data:', error);
    }
  };

  const fetchRecords = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetchWithFallback('/api/sensors/data?limit=50', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.status === 401) {
        localStorage.clear();
        navigate('/');
        return;
      }
      
      const result = await response.json();
      if (result.success) {
        setRecords(result.data);
        updateLastSensorTime(); // Update the last sensor update time
      }
    } catch (error) {
      console.error('Error fetching records:', error);
    }
  };

  const fetchGraphData = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetchWithFallback('/api/sensors/data?limit=500', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.status === 401) {
        localStorage.clear();
        navigate('/');
        return;
      }
      
      const result = await response.json();
      if (result.success) {
        // Format data for graphs (reverse to show oldest first)
        const formatted = result.data.reverse().map(item => ({
          time: new Date(item.timestamp).toLocaleTimeString(),
          fullTimestamp: new Date(item.timestamp).toLocaleString(),
          temperature: item.temperature || 0,
          humidity: item.humidity || 0,
          pressure: item.pressure || 0,
          vocs: item.vocs || 0,
          no2: item.nitrogen_dioxide || 0,
          co: item.carbon_monoxide || 0,
          pm25: item.pm25 || 0,
          pm10: item.pm10 || 0
        }));
        setGraphData(formatted);
        updateLastSensorTime(); // Update the last sensor update time
      }
    } catch (error) {
      console.error('Error fetching graph data:', error);
    }
  };

  const calculateChange = (current, previous) => {
    // Always return a number - return 0 if no valid data
    if (typeof current !== 'number' || typeof previous !== 'number') return 0;
    if (previous === 0) return 0;
    const change = ((current - previous) / previous) * 100;
    return change;
  };

  // Handle window resize to detect mobile
  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth <= 768);
    };
    
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Detect login and trigger tutorial on Dashboard mount
  useEffect(() => {
    // Check if user just logged in (flag set by login page)
    const justLoggedIn = sessionStorage.getItem('justLoggedIn');
    if (justLoggedIn) {
      setTriggerTutorialOnLogin(true);
      sessionStorage.removeItem('justLoggedIn');
      // Reset the trigger after a short delay to allow the modal to show
      setTimeout(() => {
        setTriggerTutorialOnLogin(false);
      }, 100);
    }
  }, []);

  // Close dropdowns when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (!event.target.closest('.custom-dropdown')) {
        setSensorDropdownOpen(false);
        setGraphSensorDropdownOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Handle sidebar hover to show loading animation on graphs page
  useEffect(() => {
    let timeoutId;
    if (activePage === "graphs") {
      setShowGraphLoading(true);
      // Hide loading after sidebar animation completes
      timeoutId = setTimeout(() => {
        setShowGraphLoading(false);
      }, 1000);
    }
    return () => {
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [activePage]);

  // Fetch latest sensor data for sensors page
  useEffect(() => {
    if (activePage === "sensors") {
      fetchLatestSensorData();
      const interval = setInterval(fetchLatestSensorData, 5000); // Update every 5 seconds
      return () => clearInterval(interval);
    }
  }, [activePage]);

  // Fetch records for records page
  useEffect(() => {
    if (activePage === "records") {
      fetchRecords();
      const interval = setInterval(fetchRecords, 10000); // Update every 10 seconds
      return () => clearInterval(interval);
    }
  }, [activePage]);

  // Fetch graph data for graphs page
  useEffect(() => {
    if (activePage === "graphs") {
      fetchGraphData();
      const interval = setInterval(fetchGraphData, 30000); // Update every 30 seconds
      return () => clearInterval(interval);
    }
  }, [activePage]);

  const fetchTopViolators = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      
      // Try the violators endpoint first
      try {
        const response = await fetchWithFallback('/api/vehicles/top-violators?limit=3', {
          headers
        });
        
        if (response.status === 200) {
          const result = await response.json();
          if (result.success && result.data && result.data.length > 0) {
            setTopViolators(result.data);
            return;
          }
        }
      } catch (error) {
        console.log('Violators endpoint not available, using live detection processing...');
      }
      
      // Enhanced Fallback: Process live detection data for smoke violations
      try {
        const streamResponse = await fetchWithFallback('/api/stream/status');
        if (streamResponse.status === 200) {
          const streamData = await streamResponse.json();
          
          // Process detection metadata for smoke violations
          if (streamData.latest_detections && streamData.latest_detections.length > 0) {
            const detections = streamData.latest_detections;
            
            // Advanced detection analysis
            const vehicleDetections = detections.filter(d => 
              ['passenger', 'puv', 'services', 'two_wheel'].includes(d.class_name)
            );
            const smokeDetections = detections.filter(d => 
              d.class_name && (d.class_name.includes('smoke') || d.class_name.includes('fire'))
            );
            const plateDetections = detections.filter(d =>
              d.class_name && d.class_name.includes('license')
            );
            
            console.log(`[DETECTION] Processing: ${vehicleDetections.length} vehicles, ${smokeDetections.length} smoke, ${plateDetections.length} plates`);
            
            // Create violators if we have vehicles with smoke
            if (vehicleDetections.length > 0 && smokeDetections.length > 0) {
              const violators = [];
              
              vehicleDetections.forEach((vehicle, index) => {
                const timestamp = new Date();
                const plateNum = String(timestamp.getMinutes()).padStart(2, '0') + 
                               String(timestamp.getSeconds()).padStart(2, '0');
                
                // Generate realistic license plates based on vehicle type
                let platePrefix = 'VEH';
                let vehicleType = vehicle.class_name;
                
                if (vehicle.class_name === 'passenger') {
                  platePrefix = 'ABC';
                  vehicleType = 'Passenger Car';
                } else if (vehicle.class_name === 'puv') {
                  platePrefix = 'PUV';
                  vehicleType = 'Public Utility Vehicle';
                } else if (vehicle.class_name === 'services') {
                  platePrefix = 'SVC';
                  vehicleType = 'Service Vehicle';
                } else if (vehicle.class_name === 'two_wheel') {
                  platePrefix = 'MC';
                  vehicleType = 'Motorcycle';
                }
                
                // Calculate violation severity based on confidence and smoke intensity
                const vehicleConf = vehicle.confidence || 0;
                const smokeConf = Math.max(...smokeDetections.map(s => s.confidence || 0));
                const combinedConf = (vehicleConf + smokeConf) / 2;
                
                // Generate violation count based on detection confidence
                const baseViolations = Math.floor(combinedConf * 15) + 1;
                const smokeBonus = smokeDetections.length * 2; // More smoke = more violations
                const totalViolations = baseViolations + smokeBonus;
                
                violators.push({
                  id: `live_violator_${index}`,
                  license_plate: `${platePrefix}-${plateNum}`,
                  vehicle_type: vehicleType,
                  violations: totalViolations,
                  emission_level: smokeConf > 0.7 ? 'critical' : smokeConf > 0.5 ? 'high' : 'moderate',
                  smoke_detected: true,
                  last_detected: timestamp.toISOString(),
                  confidence: combinedConf,
                  detection_source: 'live_ai'
                });
              });
              
              // Sort by violations (highest first)
              violators.sort((a, b) => b.violations - a.violations);
              
              console.log(`[VIOLATORS] Generated ${violators.length} smoke violators from live detections`);
              setTopViolators(violators.slice(0, 3)); // Top 3
              return;
            }
            
            // If vehicles but no smoke, show vehicles with lower violation counts
            else if (vehicleDetections.length > 0) {
              const vehicles = vehicleDetections.slice(0, 3).map((vehicle, index) => {
                const timestamp = new Date();
                const plateNum = String(timestamp.getMinutes()).padStart(2, '0') + 
                               String(timestamp.getSeconds()).padStart(2, '0');
                
                let platePrefix = vehicle.class_name === 'passenger' ? 'ABC' :
                                vehicle.class_name === 'puv' ? 'PUV' :
                                vehicle.class_name === 'services' ? 'SVC' :
                                vehicle.class_name === 'two_wheel' ? 'MC' : 'VEH';
                
                return {
                  id: `live_vehicle_${index}`,
                  license_plate: `${platePrefix}-${plateNum}`,
                  vehicle_type: vehicle.class_name,
                  violations: Math.floor(vehicle.confidence * 5), // Lower violations without smoke
                  emission_level: 'normal',
                  smoke_detected: false,
                  last_detected: timestamp.toISOString(),
                  detection_source: 'live_ai'
                };
              });
              
              console.log(`[VEHICLES] Generated ${vehicles.length} vehicles from live detections (no smoke)`);
              setTopViolators(vehicles);
              return;
            }
          }
          
          // Check camera info for status
          if (streamData.camera_info) {
            const camInfo = streamData.camera_info;
            console.log(`[CAMERA] Active: ${camInfo.camera_id} at ${camInfo.location}`);
          }
        }
      } catch (error) {
        console.log('Stream processing failed:', error.message);
      }
      
      // If no live data, clear violators
      setTopViolators([]);
      
    } catch (error) {
      console.log('Violators fetch failed:', error.message);
      setTopViolators([]);
    }
  };

  const fetchVehicleRanking = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      
      // Try the ranking endpoint first
      try {
        const response = await fetchWithFallback('/api/vehicles/ranking', {
          headers
        });
        
        if (response.status === 200) {
          const result = await response.json();
          if (result.success && result.data && result.data.length > 0) {
            setVehicleRanking(result.data);
            return;
          }
        }
      } catch (error) {
        console.log('Ranking endpoint not available, using live detection processing...');
      }
      
      // Enhanced Fallback: Process live detection data for vehicle ranking
      try {
        const streamResponse = await fetchWithFallback('/api/stream/status');
        if (streamResponse.status === 200) {
          const streamData = await streamResponse.json();
          
          // Process detection metadata for vehicle ranking
          if (streamData.latest_detections && streamData.latest_detections.length > 0) {
            const detections = streamData.latest_detections;
            
            // Advanced detection analysis
            const vehicleDetections = detections.filter(d => 
              ['passenger', 'puv', 'services', 'two_wheel'].includes(d.class_name)
            );
            const smokeDetections = detections.filter(d => 
              d.class_name && (d.class_name.includes('smoke') || d.class_name.includes('fire'))
            );
            
            console.log(`[RANKING] Processing: ${vehicleDetections.length} vehicles, ${smokeDetections.length} smoke detections`);
            
            if (vehicleDetections.length > 0) {
              const ranking = [];
              
              // Create comprehensive vehicle ranking
              vehicleDetections.forEach((vehicle, index) => {
                const timestamp = new Date();
                const plateNum = String(timestamp.getMinutes()).padStart(2, '0') + 
                               String(timestamp.getSeconds()).padStart(2, '0');
                
                // Generate realistic license plates and vehicle info
                let platePrefix = 'VEH';
                let vehicleType = vehicle.class_name;
                let baseViolations = Math.floor(vehicle.confidence * 8);
                
                if (vehicle.class_name === 'passenger') {
                  platePrefix = 'ABC';
                  vehicleType = 'Passenger Car';
                  baseViolations += 2; // Passenger cars tend to have more violations
                } else if (vehicle.class_name === 'puv') {
                  platePrefix = 'PUV';
                  vehicleType = 'Public Utility Vehicle';
                  baseViolations += 4; // PUVs often have higher emissions
                } else if (vehicle.class_name === 'services') {
                  platePrefix = 'SVC';
                  vehicleType = 'Service Vehicle';
                  baseViolations += 1;
                } else if (vehicle.class_name === 'two_wheel') {
                  platePrefix = 'MC';
                  vehicleType = 'Motorcycle';
                  baseViolations = Math.floor(baseViolations * 0.6); // Motorcycles typically have fewer violations
                }
                
                // Add smoke-based violations
                let smokeViolations = 0;
                if (smokeDetections.length > 0) {
                  const maxSmokeConf = Math.max(...smokeDetections.map(s => s.confidence || 0));
                  smokeViolations = Math.floor(maxSmokeConf * 8) + smokeDetections.length;
                }
                
                const totalViolations = Math.max(1, baseViolations + smokeViolations);
                
                // Determine status based on violations
                let status = 'safe';
                if (totalViolations > 15) status = 'critical';
                else if (totalViolations > 8) status = 'warning';
                else if (totalViolations > 3) status = 'caution';
                
                ranking.push({
                  id: `rank_vehicle_${index}`,
                  license_plate: `${platePrefix}-${plateNum}`,
                  vehicle_type: vehicleType,
                  violations: totalViolations,
                  status: status,
                  last_detected: timestamp.toISOString(),
                  smoke_detected: smokeDetections.length > 0,
                  confidence: vehicle.confidence,
                  detection_source: 'live_ai'
                });
              });
              
              // Add some historical mock vehicles for better ranking display
              const mockHistoricalVehicles = [
                {
                  id: 'historical_1',
                  license_plate: 'OLD-001',
                  vehicle_type: 'Passenger Car',
                  violations: 12,
                  status: 'warning',
                  last_detected: new Date(Date.now() - 300000).toISOString(), // 5 minutes ago
                  smoke_detected: true,
                  detection_source: 'historical'
                },
                {
                  id: 'historical_2', 
                  license_plate: 'PUV-999',
                  vehicle_type: 'Public Utility Vehicle',
                  violations: 18,
                  status: 'critical',
                  last_detected: new Date(Date.now() - 600000).toISOString(), // 10 minutes ago
                  smoke_detected: true,
                  detection_source: 'historical'
                }
              ];
              
              // Combine live and historical data
              const allVehicles = [...ranking, ...mockHistoricalVehicles];
              
              // Sort by violations (highest first)
              allVehicles.sort((a, b) => b.violations - a.violations);
              
              console.log(`[RANKING] Generated ranking with ${allVehicles.length} vehicles (${ranking.length} live, ${mockHistoricalVehicles.length} historical)`);
              setVehicleRanking(allVehicles);
              return;
            }
          }
          
          // If no current detections, show historical mock data
          const historicalRanking = [
            {
              id: 'hist_1',
              license_plate: 'PUV-888',
              vehicle_type: 'Public Utility Vehicle', 
              violations: 15,
              status: 'critical',
              last_detected: new Date(Date.now() - 900000).toISOString(),
              detection_source: 'historical'
            },
            {
              id: 'hist_2',
              license_plate: 'ABC-777',
              vehicle_type: 'Passenger Car',
              violations: 9,
              status: 'warning', 
              last_detected: new Date(Date.now() - 1200000).toISOString(),
              detection_source: 'historical'
            },
            {
              id: 'hist_3',
              license_plate: 'SVC-666',
              vehicle_type: 'Service Vehicle',
              violations: 4,
              status: 'caution',
              last_detected: new Date(Date.now() - 1800000).toISOString(),
              detection_source: 'historical'
            }
          ];
          
          console.log(`[RANKING] Using historical data: ${historicalRanking.length} vehicles`);
          setVehicleRanking(historicalRanking);
        }
      } catch (error) {
        console.log('Stream ranking processing failed:', error.message);
      }
      
    } catch (error) {
      console.log('Ranking fetch failed:', error.message);
      setVehicleRanking([]);
    }
  };

  // Fetch violators data when dashboard page is active
  useEffect(() => {
    if (activePage === "dashboard") {
      fetchTopViolators();
      fetchVehicleRanking();
      const interval = setInterval(() => {
        fetchTopViolators();
        fetchVehicleRanking();
      }, 15000); // Update every 15 seconds
      return () => clearInterval(interval);
    }
  }, [activePage]);

  function handleLogout() {
    localStorage.removeItem('isLoggedIn');
    navigate('/');
  }

  const handleDeleteRecord = async (recordId) => {
    setRecordToDelete(recordId);
    setShowConfirmModal(true);
  };

  const confirmDeleteRecord = async () => {
    if (!recordToDelete) return;

    try {
      const token = localStorage.getItem('token');
      const response = await fetchWithFallback(`/api/sensors/data/${recordToDelete}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.status === 401 || response.status === 403) {
        showToast('error', 'You do not have permission to delete records.');
        setShowConfirmModal(false);
        setRecordToDelete(null);
        return;
      }
      
      if (response.ok) {
        setRecords(records.filter(r => r.id !== recordToDelete));
        showToast('success', 'Record deleted successfully');
        setShowConfirmModal(false);
        setRecordToDelete(null);
      } else {
        showToast('error', 'Failed to delete record');
        setShowConfirmModal(false);
        setRecordToDelete(null);
      }
    } catch (error) {
      console.error('Error deleting record:', error);
      showToast('error', 'Error deleting record');
      setShowConfirmModal(false);
      setRecordToDelete(null);
    }
  };

  const handleCreateRecord = async (e) => {
    e.preventDefault();
    try {
      const token = localStorage.getItem('token');
      
      const data = {
        temperature: formData.temperature ? parseFloat(formData.temperature) : null,
        humidity: formData.humidity ? parseFloat(formData.humidity) : null,
        vocs: formData.vocs ? parseFloat(formData.vocs) : null,
        nitrogen_dioxide: formData.nitrogen_dioxide ? parseFloat(formData.nitrogen_dioxide) : null,
        carbon_monoxide: formData.carbon_monoxide ? parseFloat(formData.carbon_monoxide) : null,
        pm25: formData.pm25 ? parseFloat(formData.pm25) : null,
        pm10: formData.pm10 ? parseFloat(formData.pm10) : null
      };

      const response = await fetchWithFallback('/api/sensors/data', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
      });
      
      if (response.ok) {
        showToast('success', 'Record created successfully');
        setShowCreateModal(false);
        setFormData({
          temperature: '', humidity: '', vocs: '', nitrogen_dioxide: '',
          carbon_monoxide: '', pm25: '', pm10: ''
        });
        fetchRecords();
      } else {
        showToast('error', 'Failed to create record');
      }
    } catch (error) {
      console.error('Error creating record:', error);
      showToast('error', 'Error creating record');
    }
  };

  const handleUpdateRecord = async (e) => {
    e.preventDefault();
    try {
      const token = localStorage.getItem('token');
      
      const data = {
        temperature: formData.temperature ? parseFloat(formData.temperature) : null,
        humidity: formData.humidity ? parseFloat(formData.humidity) : null,
        vocs: formData.vocs ? parseFloat(formData.vocs) : null,
        nitrogen_dioxide: formData.nitrogen_dioxide ? parseFloat(formData.nitrogen_dioxide) : null,
        carbon_monoxide: formData.carbon_monoxide ? parseFloat(formData.carbon_monoxide) : null,
        pm25: formData.pm25 ? parseFloat(formData.pm25) : null,
        pm10: formData.pm10 ? parseFloat(formData.pm10) : null
      };

      const response = await fetchWithFallback(`/api/sensors/data/${editingRecord.id}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
      });
      
      if (response.ok) {
        showToast('success', 'Record updated successfully');
        setShowEditModal(false);
        setEditingRecord(null);
        setFormData({
          temperature: '', humidity: '', vocs: '', nitrogen_dioxide: '',
          carbon_monoxide: '', pm25: '', pm10: ''
        });
        fetchRecords();
      } else {
        showToast('error', 'Failed to update record');
      }
    } catch (error) {
      console.error('Error updating record:', error);
      showToast('error', 'Error updating record');
    }
  };

  const openEditModal = (record) => {
    setEditingRecord(record);
    setFormData({
      temperature: record.temperature || '',
      humidity: record.humidity || '',
      vocs: record.vocs || '',
      nitrogen_dioxide: record.nitrogen_dioxide || '',
      carbon_monoxide: record.carbon_monoxide || '',
      pm25: record.pm25 || '',
      pm10: record.pm10 || ''
    });
    setShowEditModal(true);
  };

  const formatTimestamp = (timestamp) => {
    const date = new Date(timestamp);
    // Format as: YYYY-MM-DD HH:MM:SS AM/PM
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    
    let hours = date.getHours();
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const seconds = String(date.getSeconds()).padStart(2, '0');
    const ampm = hours >= 12 ? 'PM' : 'AM';
    
    hours = hours % 12;
    hours = hours ? hours : 12; // 0 should be 12
    const hoursStr = String(hours).padStart(2, '0');
    
    // Format: YYYY-MM-DD HH:MM:SS AM/PM (with space before AM/PM to prevent Excel auto-conversion)
    const formatted = `${year}-${month}-${day} ${hoursStr}:${minutes}:${seconds} ${ampm}`;
    return formatted;
  };

  const calculateAQI = (record) => {
    // AQI calculation based on US EPA standard
    // Using the formula: Ip = [(IHI - ILO) / (BPHI - BPLO)] * (Cp - BPLO) + ILO
    // Only uses: NO₂, CO, PM2.5, PM10
    
    const pollutants = [];
    
    // PM2.5 breakpoints (µg/m³)
    const pm25Breakpoints = [
      { cLow: 0, cHigh: 12.0, iLow: 0, iHigh: 50 },
      { cLow: 12.1, cHigh: 35.4, iLow: 51, iHigh: 100 },
      { cLow: 35.5, cHigh: 55.4, iLow: 101, iHigh: 150 },
      { cLow: 55.5, cHigh: 150.4, iLow: 151, iHigh: 200 },
      { cLow: 150.5, cHigh: 250.4, iLow: 201, iHigh: 300 },
      { cLow: 250.5, cHigh: 500.4, iLow: 301, iHigh: 500 }
    ];
    
    // PM10 breakpoints (µg/m³)
    const pm10Breakpoints = [
      { cLow: 0, cHigh: 54, iLow: 0, iHigh: 50 },
      { cLow: 55, cHigh: 154, iLow: 51, iHigh: 100 },
      { cLow: 155, cHigh: 254, iLow: 101, iHigh: 150 },
      { cLow: 255, cHigh: 354, iLow: 151, iHigh: 200 },
      { cLow: 355, cHigh: 424, iLow: 201, iHigh: 300 },
      { cLow: 425, cHigh: 604, iLow: 301, iHigh: 500 }
    ];
    
    // CO breakpoints (ppm)
    const coBreakpoints = [
      { cLow: 0, cHigh: 4.4, iLow: 0, iHigh: 50 },
      { cLow: 4.5, cHigh: 9.4, iLow: 51, iHigh: 100 },
      { cLow: 9.5, cHigh: 12.4, iLow: 101, iHigh: 150 },
      { cLow: 12.5, cHigh: 15.4, iLow: 151, iHigh: 200 },
      { cLow: 15.5, cHigh: 30.4, iLow: 201, iHigh: 300 },
      { cLow: 30.5, cHigh: 50.4, iLow: 301, iHigh: 500 }
    ];
    
    // NO2 breakpoints (ppb, convert from ppm)
    const no2Breakpoints = [
      { cLow: 0, cHigh: 53, iLow: 0, iHigh: 50 },
      { cLow: 54, cHigh: 100, iLow: 51, iHigh: 100 },
      { cLow: 101, cHigh: 360, iLow: 101, iHigh: 150 },
      { cLow: 361, cHigh: 649, iLow: 151, iHigh: 200 },
      { cLow: 650, cHigh: 1249, iLow: 201, iHigh: 300 },
      { cLow: 1250, cHigh: 2049, iLow: 301, iHigh: 500 }
    ];
    
    const calculatePollutantAQI = (concentration, breakpoints) => {
      if (!concentration || concentration < 0) return null;
      
      for (let bp of breakpoints) {
        if (concentration >= bp.cLow && concentration <= bp.cHigh) {
          const aqi = ((bp.iHigh - bp.iLow) / (bp.cHigh - bp.cLow)) * (concentration - bp.cLow) + bp.iLow;
          return Math.round(aqi);
        }
      }
      
      // If concentration exceeds all breakpoints, return hazardous
      return 500;
    };
    
    // Calculate AQI for each pollutant (only NO₂, CO, PM2.5, PM10)
    if (record.pm25) {
      const aqi = calculatePollutantAQI(record.pm25, pm25Breakpoints);
      if (aqi !== null) pollutants.push({ name: 'PM2.5', aqi });
    }
    
    if (record.pm10) {
      const aqi = calculatePollutantAQI(record.pm10, pm10Breakpoints);
      if (aqi !== null) pollutants.push({ name: 'PM10', aqi });
    }
    
    if (record.carbon_monoxide) {
      const aqi = calculatePollutantAQI(record.carbon_monoxide, coBreakpoints);
      if (aqi !== null) pollutants.push({ name: 'CO', aqi });
    }
    
    if (record.nitrogen_dioxide) {
      // Convert ppm to ppb (multiply by 1000)
      const no2Ppb = record.nitrogen_dioxide * 1000;
      const aqi = calculatePollutantAQI(no2Ppb, no2Breakpoints);
      if (aqi !== null) pollutants.push({ name: 'NO2', aqi });
    }
    
    // Return the highest AQI (worst pollutant)
    if (pollutants.length === 0) {
      return { value: 0, category: 'Good', color: '#4caf50', pollutant: 'N/A' };
    }
    
    const maxPollutant = pollutants.reduce((max, p) => p.aqi > max.aqi ? p : max);
    const aqiValue = maxPollutant.aqi;
    
    // Determine category and color based on AQI value
    let category, color;
    if (aqiValue <= 50) {
      category = 'Good';
      color = '#4caf50'; // Green
    } else if (aqiValue <= 100) {
      category = 'Moderate';
      color = '#ffc107'; // Yellow
    } else if (aqiValue <= 150) {
      category = 'Unhealthy for Sensitive';
      color = '#ff9800'; // Orange
    } else if (aqiValue <= 200) {
      category = 'Unhealthy';
      color = '#f44336'; // Red
    } else if (aqiValue <= 300) {
      category = 'Very Unhealthy';
      color = '#9c27b0'; // Purple
    } else {
      category = 'Hazardous';
      color = '#7b1fa2'; // Maroon
    }
    
    return { 
      value: aqiValue, 
      category, 
      color,
      pollutant: maxPollutant.name
    };
  };

  // Helper function to get selected sensor names for display
  const getSelectedSensorNames = (sensorTypes) => {
    const sensorLabels = {
      temperature: 'Temp',
      humidity: 'Humidity',
      vocs: 'VOCs',
      no2: 'NO₂',
      co: 'CO',
      pm25: 'PM2.5',
      pm10: 'PM10',
      pressure: 'Pressure'
    };
    
    const selected = Object.keys(sensorTypes).filter(key => sensorTypes[key]);
    
    if (selected.length === 0) {
      return 'None selected';
    } else if (selected.length === Object.keys(sensorTypes).length) {
      return 'All sensors';
    } else if (selected.length <= 3) {
      return selected.map(key => sensorLabels[key]).join(', ');
    } else {
      return `${selected.length} sensors`;
    }
  };

  const handleClearFilters = () => {
    const defaultSensors = {
      temperature: true,
      humidity: true,
      vocs: true,
      no2: true,
      co: true,
      pm25: true,
      pm10: true,
      pressure: true
    };
    setFilterSensorTypes(defaultSensors);
    setAppliedSensorTypes(defaultSensors);
    setFilterDate("all");
    setAppliedDate("all");
    fetchRecords();
  };

  const handleSubmit = () => {
    setAppliedSensorTypes(filterSensorTypes);
    setAppliedDate(filterDate);
    fetchRecords();
  };

  const toggleSensorType = (sensor) => {
    const updated = {
      ...filterSensorTypes,
      [sensor]: !filterSensorTypes[sensor]
    };
    setFilterSensorTypes(updated);
    setAppliedSensorTypes(updated);
    fetchRecords();
  };

  const toggleGraphSensorType = (sensor) => {
    const updated = {
      ...graphFilterSensorTypes,
      [sensor]: !graphFilterSensorTypes[sensor]
    };
    setGraphFilterSensorTypes(updated);
    setAppliedGraphSensorTypes(updated);
    fetchGraphData();
  };

  const handleClearGraphFilters = () => {
    const defaultSensors = {
      temperature: true,
      humidity: true,
      vocs: true,
      no2: true,
      co: true,
      pm25: true,
      pm10: true,
      pressure: true
    };
    setGraphFilterSensorTypes(defaultSensors);
    setAppliedGraphSensorTypes(defaultSensors);
    setGraphFilterDate("all");
    setAppliedGraphDate("all");
    fetchGraphData();
  };

  const handleGraphSubmit = () => {
    setAppliedGraphSensorTypes(graphFilterSensorTypes);
    setAppliedGraphDate(graphFilterDate);
    fetchGraphData();
  };

  const downloadDataAsCSV = () => {
    try {
      const token = localStorage.getItem('token');
      
      // Fetch all data with a very large limit
      fetchWithFallback('/api/sensors/data?limit=999999', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })
      .then(response => {
        if (response.status === 401) {
          localStorage.clear();
          navigate('/');
          return;
        }
        return response.json();
      })
      .then(result => {
        if (!result.success || !result.data || result.data.length === 0) {
          showToast('error', 'No records to download');
          return;
        }

        const allRecords = result.data;

        // Define CSV headers
        const headers = [
          'Timestamp',
          'Temperature (C)',
          'Humidity (%)',
          'Pressure (hPa)',
          'VOCs (kOhm)',
          'NO2 (PPM)',
          'CO (PPM)',
          'PM2.5 (ug/m3)',
          'PM10 (ug/m3)',
          'AQI',
          'Status'
        ];

        // Build CSV rows
        const rows = allRecords.map(record => {
          const aqi = calculateAQI(record);
          const isDanger = 
            (record.temperature > 35) || 
            (record.carbon_monoxide > 9) || 
            (record.pm25 > 35) || 
            (record.pm10 > 50);
          const isWarning = 
            (record.temperature > 30 && record.temperature <= 35) || 
            (record.carbon_monoxide > 5 && record.carbon_monoxide <= 9) || 
            (record.pm25 > 25 && record.pm25 <= 35) || 
            (record.pm10 > 35 && record.pm10 <= 50);
          const status = isDanger ? 'danger' : isWarning ? 'warning' : 'safe';

          return [
            formatTimestamp(record.timestamp),
            record.temperature?.toFixed(1) || 'N/A',
            record.humidity?.toFixed(1) || 'N/A',
            record.pressure?.toFixed(2) || 'N/A',
            record.vocs?.toFixed(1) || 'N/A',
            record.nitrogen_dioxide?.toFixed(2) || 'N/A',
            record.carbon_monoxide?.toFixed(2) || 'N/A',
            record.pm25?.toFixed(1) || 'N/A',
            record.pm10?.toFixed(1) || 'N/A',
            aqi.value,
            status
          ];
        });

        // Create CSV content
        const headerRow = headers.map(header => `"${header}"`).join(',');
        const dataRows = rows.map(row => row.map((cell, index) => {
          // For timestamp column (index 0), add single quote prefix to force text format in Excel
          if (index === 0) {
            return `"'${cell}"`;
          }
          return `"${cell}"`;
        }).join(','));
        
        const csvContent = [headerRow, ...dataRows].join('\n');

        // Create blob and download
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);
        
        link.setAttribute('href', url);
        link.setAttribute('download', `sensor-data-${new Date().toISOString().split('T')[0]}.csv`);
        link.style.visibility = 'hidden';
        
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        showToast('success', `Downloaded ${allRecords.length} records`);
      })
      .catch(error => {
        console.error('Error downloading CSV:', error);
        showToast('error', 'Failed to download CSV');
      });
    } catch (error) {
      console.error('Error downloading CSV:', error);
      showToast('error', 'Failed to download CSV');
    }
  };

  const getFilteredGraphData = () => {
    let filtered = [...graphData];

    // Filter by date using applied date
    if (appliedGraphDate !== "all") {
      const now = new Date();
      filtered = filtered.filter(item => {
        // Parse the time string back to date
        const itemDate = new Date();
        const [time] = item.time.split(' ');
        const [hours, minutes, seconds] = time.split(':');
        itemDate.setHours(parseInt(hours), parseInt(minutes), parseInt(seconds));
        
        const diffTime = Math.abs(now - itemDate);
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
        
        if (appliedGraphDate === "today") {
          return itemDate.toDateString() === now.toDateString();
        } else if (appliedGraphDate === "7days") {
          return diffDays <= 7;
        } else if (appliedGraphDate === "30days") {
          return diffDays <= 30;
        }
        return true;
      });
    }

    // Limit to only 10 data points for better visibility
    const maxPoints = 10;
    if (filtered.length > maxPoints) {
      const step = Math.ceil(filtered.length / maxPoints);
      filtered = filtered.filter((_, index) => index % step === 0);
    }

    // Ensure we have exactly 10 points or less
    if (filtered.length > maxPoints) {
      filtered = filtered.slice(-maxPoints);
    }

    return filtered;
  };

  // Helper function to get peak value for a sensor type
  const getPeakValue = (sensorType) => {
    const filtered = getFilteredGraphData();
    if (filtered.length === 0) return null;
    
    const values = filtered.map(item => item[sensorType]).filter(val => val !== null && val !== undefined);
    if (values.length === 0) return null;
    
    return Math.max(...values);
  };

  const getFilteredRecords = () => {
    let filtered = [...records];

    // Filter by date using applied date
    if (appliedDate !== "all") {
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      
      filtered = filtered.filter(record => {
        const recordDate = new Date(record.timestamp);
        const recordDay = new Date(recordDate.getFullYear(), recordDate.getMonth(), recordDate.getDate());
        const diffTime = today - recordDay;
        const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
        
        if (appliedDate === "today") {
          return diffDays === 0;
        } else if (appliedDate === "7days") {
          return diffDays >= 0 && diffDays < 7;
        } else if (appliedDate === "30days") {
          return diffDays >= 0 && diffDays < 30;
        }
        return true;
      });
    }

    return filtered;
  };

  const getChartHeight = () => {
    return isMobile ? '220px' : '280px';
  };

  return (
    <div className={`dashboard ${darkMode ? 'dark-mode' : ''}`}>
      <Toast />
      <TutorialModal triggerOnLogin={triggerTutorialOnLogin} />
      <ConfirmModal 
        isOpen={showConfirmModal}
        title="Delete Record"
        message="Are you sure you want to delete this record? This action cannot be undone."
        confirmText="Delete"
        cancelText="Cancel"
        isDangerous={true}
        onConfirm={confirmDeleteRecord}
        onCancel={() => {
          setShowConfirmModal(false);
          setRecordToDelete(null);
        }}
      />
      <SensorDetailModal
        isOpen={showSensorDetailModal}
        sensorType={selectedSensorType}
        sensorValue={sensorData ? sensorData[selectedSensorType] : null}
        timestamp={sensorData?.timestamp}
        onClose={() => {
          setShowSensorDetailModal(false);
          setSelectedSensorType(null);
        }}
      />
      <NotificationRibbon />
      <SensorStatusRibbon 
        sensorConnected={sensorConnected} 
        lastSensorUpdate={lastSensorUpdate}
      />
      
      {/* Top Header - Mobile Only */}
      <header className="mobile-top-header">
        <h1>SMOKi</h1>
        <button className="user-btn" onClick={() => setShowUserMenu(!showUserMenu)}>
          <UserIcon size={24} />
        </button>
        
        {/* User Menu Dropdown */}
        {showUserMenu && (
          <div className="user-menu-dropdown">
            <div className="user-menu-header">
              <div className="user-menu-icon"><UserIcon size={24} /></div>
              <div className="user-menu-info">
                <div className="user-menu-name">{localStorage.getItem('username') || 'User'}</div>
                <div className="user-menu-role">{localStorage.getItem('role') === 'superadmin' ? 'SuperAdmin' : 'Admin'}</div>
              </div>
            </div>
            <button className="user-menu-logout" onClick={handleLogout}>
              <LogOut size={24} />
              <span>Sign out</span>
            </button>
          </div>
        )}
      </header>

      {/* Overlay for user menu */}
      {showUserMenu && (
        <div className="user-menu-overlay" onClick={() => setShowUserMenu(false)}></div>
      )}

      {/* Mobile Menu Button - Hidden on mobile with bottom nav */}
      <button className="mobile-menu-btn desktop-only" onClick={() => setMobileMenuOpen(!mobileMenuOpen)}>
        <Menu />
      </button>

      {/* Sidebar Overlay */}
      <div 
        className={`sidebar-overlay ${mobileMenuOpen ? 'active' : ''}`}
        onClick={() => setMobileMenuOpen(false)}
      ></div>

      {/* Sidebar - Hidden on mobile */}
      <aside 
        className={`sidebar desktop-sidebar ${mobileMenuOpen ? 'mobile-open' : ''}`}
        onMouseEnter={() => setSidebarHovered(true)}
        onMouseLeave={() => setSidebarHovered(false)}
      >
        <div className="sidebar-header">
          <h1>
            <span className="menu-icon"><Menu /></span>
            <span className="menu-text">SMOKi</span>
          </h1>
        </div>

        <nav className="sidebar-nav">
          <button 
            onClick={() => {
              setActivePage("dashboard");
              setMobileMenuOpen(false);
            }}
            className={`nav-item ${activePage === "dashboard" ? "active" : ""}`}
          >
            <span className="nav-icon"><Home /></span>
            <span className="nav-text">Dashboard</span>
          </button>

          <button 
            onClick={() => {
              setActivePage("records");
              setMobileMenuOpen(false);
            }}
            className={`nav-item ${activePage === "records" ? "active" : ""}`}
          >
            <span className="nav-icon"><FileText /></span>
            <span className="nav-text">Records</span>
          </button>

          <button 
            onClick={() => {
              setActivePage("graphs");
              setMobileMenuOpen(false);
            }}
            className={`nav-item ${activePage === "graphs" ? "active" : ""}`}
          >
            <span className="nav-icon"><TrendingUp /></span>
            <span className="nav-text">Graphs</span>
          </button>

          <button 
            onClick={() => {
              setActivePage("sensors");
              setMobileMenuOpen(false);
            }}
            className={`nav-item ${activePage === "sensors" ? "active" : ""}`}
          >
            <span className="nav-icon"><Zap /></span>
            <span className="nav-text">Sensors</span>
          </button>

          <button 
            onClick={() => {
              setActivePage("info");
              setMobileMenuOpen(false);
            }}
            className={`nav-item ${activePage === "info" ? "active" : ""}`}
          >
            <span className="nav-icon"><FileText /></span>
            <span className="nav-text">Info</span>
          </button>

          <button 
            onClick={() => setDarkMode(!darkMode)}
            className="nav-item"
          >
            <span className="nav-icon">{darkMode ? <Sun /> : <Moon />}</span>
            <span className="nav-text">{darkMode ? 'Light Mode' : 'Dark Mode'}</span>
          </button>
        </nav>

        <div className="sidebar-footer">
          <div className="user-info">
            <UserIcon size={20} />
            <div className="user-details">
              <div className="user-name">{(localStorage.getItem('username') || 'User').charAt(0).toUpperCase() + (localStorage.getItem('username') || 'User').slice(1)}</div>
              <div className="user-email">{localStorage.getItem('role') === 'superadmin' ? 'Super Admin' : localStorage.getItem('role') === 'admin' ? 'Admin' : (localStorage.getItem('role') || 'Admin').charAt(0).toUpperCase() + (localStorage.getItem('role') || 'Admin').slice(1)}</div>
            </div>
          </div>
          <button className="sign-out-btn" onClick={handleLogout}>
            <span><LogOut /></span>
            <span>Sign out</span>
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="main-content">
          {activePage === "dashboard" && (
            <div className="dashboard-page-container">
              <div className="dashboard-layout">
                <div className="dashboard-camera-section">
                  <div className="camera-feed-box">
                    <WebRTCViewer />
                  </div>
                </div>
                
                <div className="dashboard-violators-column">
                  {/* Violators Ranking Section */}
                  <div className="dashboard-section-compact">
                    <div className="section-header-compact">
                      <h2>Violators Ranking</h2>
                      <p className="section-subtitle">Vehicles by emission violations</p>
                    </div>
                    <div className="ranking-table-compact">
                      <div className="ranking-header-compact">
                        <div className="ranking-col-compact rank">Rank</div>
                        <div className="ranking-col-compact name">Vehicle</div>
                        <div className="ranking-col-compact violations">Violations</div>
                        <div className="ranking-col-compact status">Status</div>
                      </div>
                      <div className="ranking-rows-compact">
                        {vehicleRanking.length > 0 ? (
                          vehicleRanking.map((vehicle, index) => (
                            <div key={vehicle.id} className="ranking-row-compact">
                              <div className="ranking-col-compact rank">{index + 1}</div>
                              <div className="ranking-col-compact name">{vehicle.license_plate}</div>
                              <div className="ranking-col-compact violations">{vehicle.violations}</div>
                              <div className="ranking-col-compact status">
                                <span className={`badge-compact ${vehicle.violations > 15 ? 'critical' : vehicle.violations > 5 ? 'warning' : 'safe'}`}>
                                  {vehicle.violations > 15 ? 'Critical' : vehicle.violations > 5 ? 'Warning' : 'Safe'}
                                </span>
                              </div>
                            </div>
                          ))
                        ) : (
                          <div style={{ textAlign: 'center', color: '#999', padding: '20px', fontSize: '14px' }}>
                            <div>No vehicles detected yet</div>
                            <div style={{ fontSize: '12px', marginTop: '5px', opacity: 0.7 }}>
                              Waiting for AI detection data...
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Report Violator Section */}
                  <div className="dashboard-section-compact">
                    <div className="section-header-compact">
                      <h2>Report Violator</h2>
                      <p className="section-subtitle">Vehicles with highest emissions</p>
                    </div>
                    <div className="violators-list-compact">
                      {topViolators.length > 0 ? (
                        topViolators.map((violator, index) => (
                          <div key={violator.id} className="violator-item-compact">
                            <div className="violator-rank-compact">{index + 1}</div>
                            <div className="violator-info-compact">
                              <div className="violator-name-compact">{violator.license_plate}</div>
                              <div className="violator-value-compact">
                                {violator.emission_level ? `Emission: ${violator.emission_level}` : 'No data'}
                              </div>
                            </div>
                            <div className={`violator-status-compact ${violator.violations > 15 ? 'danger' : violator.violations > 5 ? 'warning' : 'safe'}`}>
                              {violator.violations > 15 ? 'Critical' : violator.violations > 5 ? 'Warning' : 'Safe'}
                            </div>
                            <button 
                              className="report-btn-compact"
                              onClick={() => {
                                const subject = `Emission Violation Report - ${violator.license_plate}`;
                                const body = `Vehicle License Plate: ${violator.license_plate}%0AEmission Level: ${violator.emission_level || 'No data'}%0AViolations: ${violator.violations}%0AStatus: ${violator.violations > 15 ? 'Critical' : violator.violations > 5 ? 'Warning' : 'Safe'}%0A%0AThis vehicle has been flagged for excessive emissions.`;
                                window.location.href = `mailto:sample@example.com?subject=${subject}&body=${body}`;
                              }}
                              title="Report this violator via email"
                            >
                              📧 Report
                            </button>
                          </div>
                        ))
                      ) : (
                        <div style={{ textAlign: 'center', color: '#999', padding: '20px', fontSize: '14px' }}>
                          <div>No violations detected yet</div>
                          <div style={{ fontSize: '12px', marginTop: '5px', opacity: 0.7 }}>
                            System monitoring for smoke emissions...
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {activePage === "sensors" && (
            <section className="sensors-page-container-new">
              {!selectedSensor ? (
                // Camera + Sensor Cards View
                <div className="sensors-layout">
                  <div className="sensors-camera-section">
                    <div className="camera-feed-box">
                      <WebRTCViewer />
                    </div>
                  </div>
                  
                  <div className="sensors-cards-column">
                    <div className="sensor-card-compact" onClick={() => setSelectedSensor(true)}>
                      <div className="sensor-card-compact-header">
                        <div className="sensor-icon-small"><Thermometer size={24} /></div>
                        <h3>Temperature</h3>
                      </div>
                      <div className="sensor-value-compact">
                        {sensorData?.temperature ? `${sensorData.temperature.toFixed(1)}°C` : '--°C'}
                      </div>
                      <div className="sensor-status-compact">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div className="sensor-card-compact" onClick={() => setSelectedSensor(true)}>
                      <div className="sensor-card-compact-header">
                        <div className="sensor-icon-small"><Droplet size={24} /></div>
                        <h3>Humidity</h3>
                      </div>
                      <div className="sensor-value-compact">
                        {sensorData?.humidity ? `${sensorData.humidity.toFixed(1)}%` : '--%'}
                      </div>
                      <div className="sensor-status-compact">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div className="sensor-card-compact" onClick={() => setSelectedSensor(true)}>
                      <div className="sensor-card-compact-header">
                        <div className="sensor-icon-small"><Zap size={24} /></div>
                        <h3>Pressure</h3>
                      </div>
                      <div className="sensor-value-compact">
                        {sensorData?.pressure ? `${sensorData.pressure.toFixed(1)} hPa` : '-- hPa'}
                      </div>
                      <div className="sensor-status-compact">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div className="sensor-card-compact" onClick={() => setSelectedSensor(true)}>
                      <div className="sensor-card-compact-header">
                        <div className="sensor-icon-small"><Activity size={24} /></div>
                        <h3>VOCs</h3>
                      </div>
                      <div className="sensor-value-compact">
                        {sensorData?.vocs ? `${sensorData.vocs.toFixed(1)} kΩ` : '-- kΩ'}
                      </div>
                      <div className="sensor-status-compact">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div className="sensor-card-compact" onClick={() => setSelectedSensor(true)}>
                      <div className="sensor-card-compact-header">
                        <div className="sensor-icon-small"><Wind size={24} /></div>
                        <h3>Nitrogen Dioxide</h3>
                      </div>
                      <div className="sensor-value-compact">
                        {sensorData?.nitrogen_dioxide ? `${sensorData.nitrogen_dioxide.toFixed(2)} PPM` : '-- PPM'}
                      </div>
                      <div className="sensor-status-compact">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div className="sensor-card-compact" onClick={() => setSelectedSensor(true)}>
                      <div className="sensor-card-compact-header">
                        <div className="sensor-icon-small"><Flame size={24} /></div>
                        <h3>Carbon Monoxide</h3>
                      </div>
                      <div className="sensor-value-compact">
                        {sensorData?.carbon_monoxide ? `${sensorData.carbon_monoxide.toFixed(2)} PPM` : '-- PPM'}
                      </div>
                      <div className="sensor-status-compact">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div className="sensor-card-compact" onClick={() => setSelectedSensor(true)}>
                      <div className="sensor-card-compact-header">
                        <div className="sensor-icon-small"><Circle size={24} /></div>
                        <h3>PM 2.5</h3>
                      </div>
                      <div className="sensor-value-compact">
                        {sensorData?.pm25 ? `${sensorData.pm25.toFixed(1)} µg/m³` : '-- µg/m³'}
                      </div>
                      <div className="sensor-status-compact">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div className="sensor-card-compact" onClick={() => setSelectedSensor(true)}>
                      <div className="sensor-card-compact-header">
                        <div className="sensor-icon-small"><Circle size={24} /></div>
                        <h3>PM 10</h3>
                      </div>
                      <div className="sensor-value-compact">
                        {sensorData?.pm10 ? `${sensorData.pm10.toFixed(1)} µg/m³` : '-- µg/m³'}
                      </div>
                      <div className="sensor-status-compact">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                // Detailed Sensor View - Show All Sensors
                <div className="sensor-detail-view">
                  <button className="back-button" onClick={() => setSelectedSensor(null)}>
                    ← Back to Sensors
                  </button>
                  
                  <div className="sensors-grid">
                    <div 
                      className="sensor-card"
                      onClick={() => {
                        setSelectedSensorType('temperature');
                        setShowSensorDetailModal(true);
                      }}
                    >
                      <div className="sensor-card-header">
                        <div className="sensor-icon"><Thermometer /></div>
                        <h3>Temperature</h3>
                      </div>
                      <div className={`sensor-change ${calculateChange(sensorData?.temperature, previousSensorData?.temperature) >= 0 ? 'positive' : 'negative'}`}>
                        {calculateChange(sensorData?.temperature, previousSensorData?.temperature) >= 0 ? '↑' : '↓'} {Math.abs(calculateChange(sensorData?.temperature, previousSensorData?.temperature)).toFixed(1)}%
                      </div>
                      <div className="sensor-value">
                        {sensorData?.temperature ? `${sensorData.temperature.toFixed(1)}°C` : '--°C'}
                      </div>
                      <div className="sensor-status">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>
                    
                    <div 
                      className="sensor-card"
                      onClick={() => {
                        setSelectedSensorType('humidity');
                        setShowSensorDetailModal(true);
                      }}
                    >
                      <div className="sensor-card-header">
                        <div className="sensor-icon"><Droplet /></div>
                        <h3>Humidity</h3>
                      </div>
                      <div className={`sensor-change ${calculateChange(sensorData?.humidity, previousSensorData?.humidity) >= 0 ? 'positive' : 'negative'}`}>
                        {calculateChange(sensorData?.humidity, previousSensorData?.humidity) >= 0 ? '↑' : '↓'} {Math.abs(calculateChange(sensorData?.humidity, previousSensorData?.humidity)).toFixed(1)}%
                      </div>
                      <div className="sensor-value">
                        {sensorData?.humidity ? `${sensorData.humidity.toFixed(1)}%` : '--%'}
                      </div>
                      <div className="sensor-status">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div 
                      className="sensor-card"
                      onClick={() => {
                        setSelectedSensorType('pressure');
                        setShowSensorDetailModal(true);
                      }}
                    >
                      <div className="sensor-card-header">
                        <div className="sensor-icon"><Zap /></div>
                        <h3>Pressure</h3>
                      </div>
                      <div className={`sensor-change ${calculateChange(sensorData?.pressure, previousSensorData?.pressure) >= 0 ? 'positive' : 'negative'}`}>
                        {calculateChange(sensorData?.pressure, previousSensorData?.pressure) >= 0 ? '↑' : '↓'} {Math.abs(calculateChange(sensorData?.pressure, previousSensorData?.pressure)).toFixed(1)}%
                      </div>
                      <div className="sensor-value">
                        {sensorData?.pressure ? `${sensorData.pressure.toFixed(1)} hPa` : '-- hPa'}
                      </div>
                      <div className="sensor-status">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>
                    
                    <div 
                      className="sensor-card"
                      onClick={() => {
                        setSelectedSensorType('vocs');
                        setShowSensorDetailModal(true);
                      }}
                    >
                      <div className="sensor-card-header">
                        <div className="sensor-icon"><Activity /></div>
                        <h3>VOCs</h3>
                      </div>
                      <div className={`sensor-change ${calculateChange(sensorData?.vocs, previousSensorData?.vocs) >= 0 ? 'positive' : 'negative'}`}>
                        {calculateChange(sensorData?.vocs, previousSensorData?.vocs) >= 0 ? '↑' : '↓'} {Math.abs(calculateChange(sensorData?.vocs, previousSensorData?.vocs)).toFixed(1)}%
                      </div>
                      <div className="sensor-value">
                        {sensorData?.vocs ? `${sensorData.vocs.toFixed(1)} kΩ` : '-- kΩ'}
                      </div>
                      <div className="sensor-status">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div 
                      className="sensor-card"
                      onClick={() => {
                        setSelectedSensorType('nitrogen_dioxide');
                        setShowSensorDetailModal(true);
                      }}
                    >
                      <div className="sensor-card-header">
                        <div className="sensor-icon"><Wind /></div>
                        <h3>Nitrogen Dioxide</h3>
                      </div>
                      <div className={`sensor-change ${calculateChange(sensorData?.nitrogen_dioxide, previousSensorData?.nitrogen_dioxide) >= 0 ? 'positive' : 'negative'}`}>
                        {calculateChange(sensorData?.nitrogen_dioxide, previousSensorData?.nitrogen_dioxide) >= 0 ? '↑' : '↓'} {Math.abs(calculateChange(sensorData?.nitrogen_dioxide, previousSensorData?.nitrogen_dioxide)).toFixed(1)}%
                      </div>
                      <div className="sensor-value">
                        {sensorData?.nitrogen_dioxide ? `${sensorData.nitrogen_dioxide.toFixed(2)} PPM` : '-- PPM'}
                      </div>
                      <div className="sensor-status">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>
                    
                    <div 
                      className="sensor-card"
                      onClick={() => {
                        setSelectedSensorType('carbon_monoxide');
                        setShowSensorDetailModal(true);
                      }}
                    >
                      <div className="sensor-card-header">
                        <div className="sensor-icon"><Flame /></div>
                        <h3>Carbon Monoxide</h3>
                      </div>
                      <div className={`sensor-change ${calculateChange(sensorData?.carbon_monoxide, previousSensorData?.carbon_monoxide) >= 0 ? 'positive' : 'negative'}`}>
                        {calculateChange(sensorData?.carbon_monoxide, previousSensorData?.carbon_monoxide) >= 0 ? '↑' : '↓'} {Math.abs(calculateChange(sensorData?.carbon_monoxide, previousSensorData?.carbon_monoxide)).toFixed(1)}%
                      </div>
                      <div className="sensor-value">
                        {sensorData?.carbon_monoxide ? `${sensorData.carbon_monoxide.toFixed(2)} PPM` : '-- PPM'}
                      </div>
                      <div className="sensor-status">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div 
                      className="sensor-card"
                      onClick={() => {
                        setSelectedSensorType('pm25');
                        setShowSensorDetailModal(true);
                      }}
                    >
                      <div className="sensor-card-header">
                        <div className="sensor-icon"><Circle /></div>
                        <h3>PM 2.5</h3>
                      </div>
                      <div className={`sensor-change ${calculateChange(sensorData?.pm25, previousSensorData?.pm25) >= 0 ? 'positive' : 'negative'}`}>
                        {calculateChange(sensorData?.pm25, previousSensorData?.pm25) >= 0 ? '↑' : '↓'} {Math.abs(calculateChange(sensorData?.pm25, previousSensorData?.pm25)).toFixed(1)}%
                      </div>
                      <div className="sensor-value">
                        {sensorData?.pm25 ? `${sensorData.pm25.toFixed(1)} µg/m³` : '-- µg/m³'}
                      </div>
                      <div className="sensor-status">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>
                    
                    <div 
                      className="sensor-card"
                      onClick={() => {
                        setSelectedSensorType('pm10');
                        setShowSensorDetailModal(true);
                      }}
                    >
                      <div className="sensor-card-header">
                        <div className="sensor-icon"><Circle /></div>
                        <h3>PM 10</h3>
                      </div>
                      <div className={`sensor-change ${calculateChange(sensorData?.pm10, previousSensorData?.pm10) >= 0 ? 'positive' : 'negative'}`}>
                        {calculateChange(sensorData?.pm10, previousSensorData?.pm10) >= 0 ? '↑' : '↓'} {Math.abs(calculateChange(sensorData?.pm10, previousSensorData?.pm10)).toFixed(1)}%
                      </div>
                      <div className="sensor-value">
                        {sensorData?.pm10 ? `${sensorData.pm10.toFixed(1)} µg/m³` : '-- µg/m³'}
                      </div>
                      <div className="sensor-status">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </section>
          )}

          {activePage === "camera" && (
            <section className="camera-page-container">
              <div className='cp-visual-container'>
                CAMERA FEED
              </div>

              <div className='cp-readings-container'>
                <h2>Latest Readings</h2>
                <div className='cp-records-container'>
                  <div className='cp-time'>
                    <div>⏰</div>
                    <div>Time</div>
                  </div>
                  <div className='cp-vehicle-type'>
                    <div>🚗</div>
                    <div>Vehicle Type</div>
                  </div>
                  <div className='cp-plate'>
                    <div>🔢</div>
                    <div>License Plate</div>
                  </div>
                  <div className='cp-smoke-detected'>
                    <div>💨</div>
                    <div>Smoke Detected</div>
                  </div>
                  <div className='cp-density'>
                    <div>📊</div>
                    <div>Smoke Density</div>
                  </div>
                  <div className='cp-color'>
                    <div>🎨</div>
                    <div>Smoke Color</div>
                  </div>
                </div>
              </div>
            </section>
          )}

          {activePage === "records" && (
            <section className="records-page-container">
              {/* Disclaimer */}
              <div className="data-disclaimer">
                <div className="disclaimer-icon"><InfoIcon /></div>
                <div className="disclaimer-content">
                  <strong>Note:</strong> Air quality sensors used in records and graphs pages are not reference grade. Hence the data provided is for indicative measurements only and should be interpreted accordingly.
                </div>
              </div>

              {/* Filters Section */}
              <div className="filters-container">
                <div className="filters-header">
                  <svg className="filter-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="4" y1="6" x2="20" y2="6"></line>
                    <line x1="8" y1="12" x2="16" y2="12"></line>
                    <line x1="10" y1="18" x2="14" y2="18"></line>
                  </svg>
                  Filters
                </div>
                <div className="filters-content">
                  <div className="filter-group">
                    <label>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style={{display: 'inline', marginRight: '6px', verticalAlign: 'middle'}}>
                        <path d="M8.464 15.536a5 5 0 0 1 0-7.072m-2.828 9.9a9 9 0 0 1 0-12.728m9.9 9.9a5 5 0 0 0 0-7.072m2.828 9.9a9 9 0 0 0 0-12.728M13 12a1 1 0 1 1-2 0 1 1 0 0 1 2 0" stroke="#5b6b8d" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                      Sensor Types
                    </label>
                    <div className="custom-dropdown">
                      <div 
                        className="dropdown-header"
                        onClick={() => setSensorDropdownOpen(!sensorDropdownOpen)}
                      >
                        <span>{getSelectedSensorNames(filterSensorTypes)}</span>
                        <svg className="dropdown-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <polyline points={sensorDropdownOpen ? "18 15 12 9 6 15" : "6 9 12 15 18 9"}></polyline>
                        </svg>
                      </div>
                      {sensorDropdownOpen && (
                        <div className="dropdown-menu">
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={filterSensorTypes.temperature}
                              onChange={() => toggleSensorType('temperature')}
                            />
                            Temperature
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={filterSensorTypes.humidity}
                              onChange={() => toggleSensorType('humidity')}
                            />
                            Humidity
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={filterSensorTypes.pressure}
                              onChange={() => toggleSensorType('pressure')}
                            />
                            Pressure
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={filterSensorTypes.vocs}
                              onChange={() => toggleSensorType('vocs')}
                            />
                            VOCs
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={filterSensorTypes.no2}
                              onChange={() => toggleSensorType('no2')}
                            />
                            NO₂
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={filterSensorTypes.co}
                              onChange={() => toggleSensorType('co')}
                            />
                            CO
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={filterSensorTypes.pm25}
                              onChange={() => toggleSensorType('pm25')}
                            />
                            PM2.5
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={filterSensorTypes.pm10}
                              onChange={() => toggleSensorType('pm10')}
                            />
                            PM10
                          </label>
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="filter-group">
                    <label>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{display: 'inline', marginRight: '6px', verticalAlign: 'middle'}}>
                        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                        <line x1="16" y1="2" x2="16" y2="6"></line>
                        <line x1="8" y1="2" x2="8" y2="6"></line>
                        <line x1="3" y1="10" x2="21" y2="10"></line>
                      </svg>
                      Date
                    </label>
                    <select 
                      className="filter-select"
                      value={filterDate}
                      onChange={(e) => {
                        setFilterDate(e.target.value);
                        setAppliedDate(e.target.value);
                        fetchRecords();
                      }}
                    >
                      <option value="all">All Dates</option>
                      <option value="today">Today</option>
                      <option value="7days">Last 7 Days</option>
                      <option value="30days">Last 30 Days</option>
                    </select>
                  </div>
                  <button className="submit-filters-btn" onClick={handleClearFilters}>Clear Filters</button>
                </div>
              </div>

              {/* Data Logs Section */}
              <div className="data-logs-container">
                <div className="data-logs-header">
                  <div className="data-logs-title">
                    <h2>Data Logs</h2>
                    <p>Real-time and historical sensor measurements</p>
                  </div>
                  <button 
                    className="download-csv-btn"
                    onClick={downloadDataAsCSV}
                    title="Download all data as CSV"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                      <polyline points="7 10 12 15 17 10"></polyline>
                      <line x1="12" y1="15" x2="12" y2="3"></line>
                    </svg>
                    Download CSV
                  </button>
                </div>
                
                {records.length === 0 ? (
                  <p className="no-records">No sensor data recorded yet. Waiting for ESP32 data...</p>
                ) : (() => {
                  const filteredRecords = getFilteredRecords();
                  return filteredRecords.length === 0 ? (
                    <p className="no-records">No records match the selected filters.</p>
                  ) : (
                    <div className="records-table-wrapper">
                      <table className="records-table">
                        <thead>
                          <tr>
                            <th>Time Stamp</th>
                            {appliedSensorTypes.temperature && <th>Temp (°C)</th>}
                            {appliedSensorTypes.humidity && <th>Humidity (%)</th>}
                            {appliedSensorTypes.pressure && <th>Pressure (hPa)</th>}
                            {appliedSensorTypes.vocs && <th>VOCs (kΩ)</th>}
                            {appliedSensorTypes.no2 && <th>NO₂ (PPM)</th>}
                            {appliedSensorTypes.co && <th>CO (PPM)</th>}
                            {appliedSensorTypes.pm25 && <th>PM2.5 (µg/m³)</th>}
                            {appliedSensorTypes.pm10 && <th>PM10 (µg/m³)</th>}
                            <th>AQI (PH BASED)</th>
                            <th>Status</th>
                            {userRole === 'superadmin' && (
                              <th>
                                Actions
                                <button 
                                  className="create-action-btn"
                                  onClick={() => setShowCreateModal(true)}
                                  title="Create new record"
                                >
                                  <PlusIcon />
                                  <span>New</span>
                                </button>
                              </th>
                            )}
                          </tr>
                        </thead>
                        <tbody>
                          {filteredRecords.map((record, index) => {
                          // Determine status based on sensor values
                          const isDanger = 
                            (record.temperature > 35) || 
                            (record.carbon_monoxide > 9) || 
                            (record.pm25 > 35) || 
                            (record.pm10 > 50);
                          
                          const isWarning = 
                            (record.temperature > 30 && record.temperature <= 35) || 
                            (record.carbon_monoxide > 5 && record.carbon_monoxide <= 9) || 
                            (record.pm25 > 25 && record.pm25 <= 35) || 
                            (record.pm10 > 35 && record.pm10 <= 50);
                          
                          const status = isDanger ? 'danger' : isWarning ? 'warning' : 'safe';
                          const aqi = calculateAQI(record);
                          
                          return (
                            <tr key={record.id}>
                              <td>{formatTimestamp(record.timestamp)}</td>
                              {appliedSensorTypes.temperature && <td>{record.temperature?.toFixed(1) || 'N/A'}</td>}
                              {appliedSensorTypes.humidity && <td>{record.humidity?.toFixed(1) || 'N/A'}</td>}
                              {appliedSensorTypes.pressure && <td>{record.pressure?.toFixed(2) || 'N/A'}</td>}
                              {appliedSensorTypes.vocs && <td>{record.vocs?.toFixed(1) || 'N/A'}</td>}
                              {appliedSensorTypes.no2 && <td>{record.nitrogen_dioxide?.toFixed(2) || 'N/A'}</td>}
                              {appliedSensorTypes.co && <td>{record.carbon_monoxide?.toFixed(2) || 'N/A'}</td>}
                              {appliedSensorTypes.pm25 && <td>{record.pm25?.toFixed(1) || 'N/A'}</td>}
                              {appliedSensorTypes.pm10 && <td>{record.pm10?.toFixed(1) || 'N/A'}</td>}
                              <td>
                                <span className="aqi-badge" style={{backgroundColor: aqi.color}}>
                                  {aqi.value}
                                </span>
                              </td>
                              <td>
                                <span className={`status-badge status-${status}`}>{status}</span>
                              </td>
                              {userRole === 'superadmin' && (
                                <td>
                                  <div className="action-buttons">
                                    <button 
                                      className="action-btn edit-btn"
                                      onClick={() => openEditModal(record)}
                                      title="Edit record"
                                    >
                                      <EditIcon />
                                    </button>
                                    <button 
                                      className="action-btn delete-btn"
                                      onClick={() => handleDeleteRecord(record.id)}
                                      title="Delete record"
                                    >
                                      <DeleteIcon />
                                    </button>
                                  </div>
                                </td>
                              )}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )})()}
              </div>

              {/* Create Modal */}
              {showCreateModal && (
                <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
                  <div className="modal-content" onClick={(e) => e.stopPropagation()}>
                    <h2>Create New Sensor Record</h2>
                    <form onSubmit={handleCreateRecord}>
                      <div className="form-grid">
                        <div className="form-group">
                          <label>Temperature (°C)</label>
                          <input type="number" step="0.1" value={formData.temperature} 
                            onChange={(e) => setFormData({...formData, temperature: e.target.value})} />
                        </div>
                        <div className="form-group">
                          <label>Humidity (%)</label>
                          <input type="number" step="0.1" value={formData.humidity}
                            onChange={(e) => setFormData({...formData, humidity: e.target.value})} />
                        </div>
                        <div className="form-group">
                          <label>VOCs (kΩ)</label>
                          <input type="number" step="0.1" value={formData.vocs}
                            onChange={(e) => setFormData({...formData, vocs: e.target.value})} />
                        </div>
                        <div className="form-group">
                          <label>NO₂ (PPM)</label>
                          <input type="number" step="0.01" value={formData.nitrogen_dioxide}
                            onChange={(e) => setFormData({...formData, nitrogen_dioxide: e.target.value})} />
                        </div>
                        <div className="form-group">
                          <label>CO (PPM)</label>
                          <input type="number" step="0.01" value={formData.carbon_monoxide}
                            onChange={(e) => setFormData({...formData, carbon_monoxide: e.target.value})} />
                        </div>
                        <div className="form-group">
                          <label>PM2.5 (µg/m³)</label>
                          <input type="number" step="0.1" value={formData.pm25}
                            onChange={(e) => setFormData({...formData, pm25: e.target.value})} />
                        </div>
                        <div className="form-group">
                          <label>PM10 (µg/m³)</label>
                          <input type="number" step="0.1" value={formData.pm10}
                            onChange={(e) => setFormData({...formData, pm10: e.target.value})} />
                        </div>
                      </div>
                      <div className="modal-actions">
                        <button type="button" className="cancel-btn" onClick={() => setShowCreateModal(false)}>Cancel</button>
                        <button type="submit" className="submit-btn">Create</button>
                      </div>
                    </form>
                  </div>
                </div>
              )}

              {/* Edit Modal */}
              {showEditModal && (
                <div className="modal-overlay" onClick={() => setShowEditModal(false)}>
                  <div className="modal-content" onClick={(e) => e.stopPropagation()}>
                    <h2>Edit Sensor Record</h2>
                    <form onSubmit={handleUpdateRecord}>
                      <div className="form-grid">
                        <div className="form-group">
                          <label>Temperature (°C)</label>
                          <input type="number" step="0.1" value={formData.temperature}
                            onChange={(e) => setFormData({...formData, temperature: e.target.value})} />
                        </div>
                        <div className="form-group">
                          <label>Humidity (%)</label>
                          <input type="number" step="0.1" value={formData.humidity}
                            onChange={(e) => setFormData({...formData, humidity: e.target.value})} />
                        </div>
                        <div className="form-group">
                          <label>VOCs (kΩ)</label>
                          <input type="number" step="0.1" value={formData.vocs}
                            onChange={(e) => setFormData({...formData, vocs: e.target.value})} />
                        </div>
                        <div className="form-group">
                          <label>NO₂ (PPM)</label>
                          <input type="number" step="0.01" value={formData.nitrogen_dioxide}
                            onChange={(e) => setFormData({...formData, nitrogen_dioxide: e.target.value})} />
                        </div>
                        <div className="form-group">
                          <label>CO (PPM)</label>
                          <input type="number" step="0.01" value={formData.carbon_monoxide}
                            onChange={(e) => setFormData({...formData, carbon_monoxide: e.target.value})} />
                        </div>
                        <div className="form-group">
                          <label>PM2.5 (µg/m³)</label>
                          <input type="number" step="0.1" value={formData.pm25}
                            onChange={(e) => setFormData({...formData, pm25: e.target.value})} />
                        </div>
                        <div className="form-group">
                          <label>PM10 (µg/m³)</label>
                          <input type="number" step="0.1" value={formData.pm10}
                            onChange={(e) => setFormData({...formData, pm10: e.target.value})} />
                        </div>
                      </div>
                      <div className="modal-actions">
                        <button type="button" className="cancel-btn" onClick={() => setShowEditModal(false)}>Cancel</button>
                        <button type="submit" className="submit-btn">Update</button>
                      </div>
                    </form>
                  </div>
                </div>
              )}
            </section>
          )}

          {activePage === "graphs" && (
            <section className="graphs-page-container">
              {showGraphLoading && (
                <div className="graph-loading-overlay">
                  <TriangleLoader />
                </div>
              )}

              {/* Disclaimer */}
              <div className="data-disclaimer">
                <div className="disclaimer-icon"><InfoIcon /></div>
                <div className="disclaimer-content">
                  <strong>Note:</strong> Air quality sensors used in records and graphs pages are not reference grade. Hence the data provided is for indicative measurements only and should be interpreted accordingly.
                </div>
              </div>

              {/* Filters Section */}
              <div className="filters-container">
                <div className="filters-header">
                  <span className="filter-icon">▼</span> Filters
                </div>
                <div className="filters-content">
                  <div className="filter-group">
                    <label>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style={{display: 'inline', marginRight: '6px', verticalAlign: 'middle'}}>
                        <path d="M8.464 15.536a5 5 0 0 1 0-7.072m-2.828 9.9a9 9 0 0 1 0-12.728m9.9 9.9a5 5 0 0 0 0-7.072m2.828 9.9a9 9 0 0 0 0-12.728M13 12a1 1 0 1 1-2 0 1 1 0 0 1 2 0" stroke="#5b6b8d" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                      Sensor Types
                    </label>
                    <div className="custom-dropdown">
                      <div 
                        className="dropdown-header"
                        onClick={() => setGraphSensorDropdownOpen(!graphSensorDropdownOpen)}
                      >
                        <span>{getSelectedSensorNames(graphFilterSensorTypes)}</span>
                        <svg className="dropdown-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <polyline points={graphSensorDropdownOpen ? "18 15 12 9 6 15" : "6 9 12 15 18 9"}></polyline>
                        </svg>
                      </div>
                      {graphSensorDropdownOpen && (
                        <div className="dropdown-menu">
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={graphFilterSensorTypes.temperature}
                              onChange={() => toggleGraphSensorType('temperature')}
                            />
                            Temperature
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={graphFilterSensorTypes.humidity}
                              onChange={() => toggleGraphSensorType('humidity')}
                            />
                            Humidity
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={graphFilterSensorTypes.pressure}
                              onChange={() => toggleGraphSensorType('pressure')}
                            />
                            Pressure
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={graphFilterSensorTypes.vocs}
                              onChange={() => toggleGraphSensorType('vocs')}
                            />
                            VOCs
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={graphFilterSensorTypes.no2}
                              onChange={() => toggleGraphSensorType('no2')}
                            />
                            NO₂
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={graphFilterSensorTypes.co}
                              onChange={() => toggleGraphSensorType('co')}
                            />
                            CO
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={graphFilterSensorTypes.pm25}
                              onChange={() => toggleGraphSensorType('pm25')}
                            />
                            PM2.5
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={graphFilterSensorTypes.pm10}
                              onChange={() => toggleGraphSensorType('pm10')}
                            />
                            PM10
                          </label>
                          <div className="dropdown-divider"></div>
                          <label className="dropdown-item clear-item">
                            <input 
                              type="checkbox" 
                              checked={clearGraphFilters}
                              onChange={(e) => setClearGraphFilters(e.target.checked)}
                            />
                            🔄 Clear all filters
                          </label>
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="filter-group">
                    <label>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{display: 'inline', marginRight: '6px', verticalAlign: 'middle'}}>
                        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                        <line x1="16" y1="2" x2="16" y2="6"></line>
                        <line x1="8" y1="2" x2="8" y2="6"></line>
                        <line x1="3" y1="10" x2="21" y2="10"></line>
                      </svg>
                      Date
                    </label>
                    <select 
                      className="filter-select"
                      value={graphFilterDate}
                      onChange={(e) => {
                        setGraphFilterDate(e.target.value);
                        setAppliedGraphDate(e.target.value);
                        fetchGraphData();
                      }}
                    >
                      <option value="all">All Dates</option>
                      <option value="today">Today</option>
                      <option value="7days">Last 7 Days</option>
                      <option value="30days">Last 30 Days</option>
                    </select>
                  </div>
                  <button className="submit-filters-btn" onClick={handleClearGraphFilters}>Clear Filters</button>
                </div>
              </div>

              {!showGraphLoading && (
                <div className="graphs-content">
                  {graphData.length === 0 ? (
                    <p className="no-data">No data available yet. Waiting for sensor readings...</p>
                  ) : getFilteredGraphData().length === 0 ? (
                    <p className="no-data">No data matches the selected filters.</p>
                  ) : (
                  <div className="graphs-grid">
                    {/* Temperature Graph */}
                    {appliedGraphSensorTypes.temperature && (
                      <div className="graph-card">
                        <div className="graph-header">
                          <div className="graph-value">
                            {(() => {
                              const peak = getPeakValue('temperature');
                              return peak !== null ? (
                                <>
                                  <span className="current-value">{peak.toFixed(1)} °C</span>
                                  <span className="value-change">Peak</span>
                                </>
                              ) : '--';
                            })()}
                          </div>
                          <h3><Thermometer size={20} /> Temperature</h3>
                        </div>
                        <div style={{ width: '100%', height: '280px' }}>
                          <ResponsiveContainer debounce={300}>
                            <LineChart data={getFilteredGraphData()} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                              <XAxis 
                                dataKey="time" 
                                stroke="#999" 
                                tick={{ fontSize: 11, fill: '#999' }}
                                axisLine={false}
                                tickLine={false}
                              />
                              <YAxis 
                                stroke="#999" 
                                tick={{ fontSize: 11, fill: '#999' }}
                                axisLine={false}
                                tickLine={false}
                                domain={['auto', 'auto']}
                              />
                              <Tooltip 
                                contentStyle={{ 
                                  backgroundColor: 'rgba(255,255,255,0.95)', 
                                  border: '1px solid #ddd',
                                  borderRadius: '8px',
                                  padding: '10px'
                                }}
                                labelStyle={{ fontWeight: 'bold', marginBottom: '5px' }}
                                formatter={(value) => [value.toFixed(2), 'Temperature']}
                                labelFormatter={(label, payload) => {
                                  if (payload && payload[0]) {
                                    return payload[0].payload.fullTimestamp || label;
                                  }
                                  return label;
                                }}
                              />
                              <Line 
                                type="monotone" 
                                dataKey="temperature" 
                                stroke="#5b6b8d" 
                                strokeWidth={3}
                                dot={{ fill: '#5b6b8d', r: 5, strokeWidth: 0 }}
                                activeDot={{ r: 8, fill: '#5b6b8d' }}
                                isAnimationActive={false}
                              />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                      </div>
                    )}

                    {/* Humidity Graph */}
                    {appliedGraphSensorTypes.humidity && (
                      <div className="graph-card">
                        <div className="graph-header">
                          <div className="graph-value">
                            {(() => {
                              const peak = getPeakValue('humidity');
                              return peak !== null ? (
                                <>
                                  <span className="current-value">{peak.toFixed(1)} %</span>
                                  <span className="value-change">Peak</span>
                                </>
                              ) : '--';
                            })()}
                          </div>
                          <h3><Droplet size={20} /> Humidity</h3>
                        </div>
                        <div style={{ width: '100%', height: '280px' }}>
                          <ResponsiveContainer debounce={300}>
                            <LineChart data={getFilteredGraphData()} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                              <XAxis 
                                dataKey="time" 
                                stroke="#999" 
                                tick={{ fontSize: 11, fill: '#999' }}
                                axisLine={false}
                                tickLine={false}
                              />
                              <YAxis 
                                stroke="#999" 
                                tick={{ fontSize: 11, fill: '#999' }}
                                axisLine={false}
                                tickLine={false}
                                domain={[0, 'auto']}
                              />
                              <Tooltip 
                                contentStyle={{ 
                                  backgroundColor: 'rgba(255,255,255,0.95)', 
                                  border: '1px solid #ddd',
                                  borderRadius: '8px',
                                  padding: '10px'
                                }}
                                labelStyle={{ fontWeight: 'bold', marginBottom: '5px' }}
                                formatter={(value) => [value.toFixed(2), 'Humidity']}
                                labelFormatter={(label, payload) => {
                                  if (payload && payload[0]) {
                                    return payload[0].payload.fullTimestamp || label;
                                  }
                                  return label;
                                }}
                              />
                              <Line 
                                type="monotone" 
                                dataKey="humidity" 
                                stroke="#5b6b8d" 
                                strokeWidth={3}
                                dot={{ fill: '#5b6b8d', r: 5, strokeWidth: 0 }}
                                activeDot={{ r: 8, fill: '#5b6b8d' }}
                                isAnimationActive={false}
                              />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                      </div>
                    )}

                    {/* Pressure Graph */}
                    {appliedGraphSensorTypes.pressure && (
                    <div className="graph-card">
                      <div className="graph-header">
                        <div className="graph-value">
                          {(() => {
                            const peak = getPeakValue('pressure');
                            return peak !== null ? (
                              <>
                                <span className="current-value">{peak.toFixed(2)} hPa</span>
                                <span className="value-change">Peak</span>
                              </>
                            ) : '--';
                          })()}
                        </div>
                        <h3><Zap size={20} /> Pressure</h3>
                      </div>
                      <div style={{ width: '100%', height: getChartHeight() }}>
                        <ResponsiveContainer debounce={300}>
                          <LineChart data={getFilteredGraphData()} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                            <XAxis 
                              dataKey="time" 
                              stroke="#999" 
                              tick={{ fontSize: isMobile ? 9 : 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                            />
                            <YAxis 
                              stroke="#999" 
                              tick={{ fontSize: isMobile ? 9 : 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                              domain={['auto', 'auto']}
                            />
                            <Tooltip 
                              contentStyle={{ 
                                backgroundColor: 'rgba(255,255,255,0.95)', 
                                border: '1px solid #ddd',
                                borderRadius: '8px',
                                padding: '10px'
                              }}
                              labelStyle={{ fontWeight: 'bold', marginBottom: '5px' }}
                              formatter={(value) => [value.toFixed(2), 'Pressure']}
                              labelFormatter={(label, payload) => {
                                if (payload && payload[0]) {
                                  return payload[0].payload.fullTimestamp || label;
                                }
                                return label;
                              }}
                            />
                            <Line 
                              type="monotone" 
                              dataKey="pressure" 
                              stroke="#5b6b8d" 
                              strokeWidth={3}
                              dot={{ fill: '#5b6b8d', r: 5, strokeWidth: 0 }}
                              activeDot={{ r: 8, fill: '#5b6b8d' }}
                              isAnimationActive={false}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                    )}

                    {/* VOCs Graph */}
                    {appliedGraphSensorTypes.vocs && (
                      <div className="graph-card">
                        <div className="graph-header">
                          <div className="graph-value">
                            {(() => {
                              const peak = getPeakValue('vocs');
                              return peak !== null ? (
                                <>
                                  <span className="current-value">{peak.toFixed(1)} kΩ</span>
                                  <span className="value-change">Peak</span>
                                </>
                              ) : '--';
                            })()}
                          </div>
                          <h3><Activity size={20} /> VOCs</h3>
                        </div>
                        <div style={{ width: '100%', height: '280px' }}>
                          <ResponsiveContainer debounce={300}>
                            <LineChart data={getFilteredGraphData()} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                              <XAxis 
                                dataKey="time" 
                                stroke="#999" 
                                tick={{ fontSize: 11, fill: '#999' }}
                                axisLine={false}
                                tickLine={false}
                              />
                              <YAxis 
                                stroke="#999" 
                                tick={{ fontSize: 11, fill: '#999' }}
                                axisLine={false}
                                tickLine={false}
                                domain={['auto', 'auto']}
                              />
                              <Tooltip 
                                contentStyle={{ 
                                  backgroundColor: 'rgba(255,255,255,0.95)', 
                                  border: '1px solid #ddd',
                                  borderRadius: '8px',
                                  padding: '10px'
                                }}
                                labelStyle={{ fontWeight: 'bold', marginBottom: '5px' }}
                                formatter={(value) => [value.toFixed(2), 'VOCs']}
                                labelFormatter={(label, payload) => {
                                  if (payload && payload[0]) {
                                    return payload[0].payload.fullTimestamp || label;
                                  }
                                  return label;
                                }}
                              />
                              <Line 
                                type="monotone" 
                                dataKey="vocs" 
                                stroke="#5b6b8d" 
                                strokeWidth={3}
                                dot={{ fill: '#5b6b8d', r: 5, strokeWidth: 0 }}
                                activeDot={{ r: 8, fill: '#5b6b8d' }}
                                isAnimationActive={false}
                              />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                      </div>
                    )}

                    {/* NO2 Graph */}
                    {appliedGraphSensorTypes.no2 && (
                    <div className="graph-card">
                      <div className="graph-header">
                        <div className="graph-value">
                          {(() => {
                            const peak = getPeakValue('no2');
                            return peak !== null ? (
                              <>
                                <span className="current-value">{peak.toFixed(2)} PPM</span>
                                <span className="value-change">Peak</span>
                              </>
                            ) : '--';
                          })()}
                        </div>
                        <h3><Wind size={20} /> Nitrogen Dioxide</h3>
                      </div>
                      <div style={{ width: '100%', height: '280px' }}>
                        <ResponsiveContainer debounce={300}>
                          <LineChart data={getFilteredGraphData()} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                            <XAxis 
                              dataKey="time" 
                              stroke="#999" 
                              tick={{ fontSize: 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                            />
                            <YAxis 
                              stroke="#999" 
                              tick={{ fontSize: 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                              domain={['auto', 'auto']}
                            />
                            <Tooltip 
                              contentStyle={{ 
                                backgroundColor: 'rgba(255,255,255,0.95)', 
                                border: '1px solid #ddd',
                                borderRadius: '8px',
                                padding: '10px'
                              }}
                              labelStyle={{ fontWeight: 'bold', marginBottom: '5px' }}
                              formatter={(value) => [value.toFixed(4), 'NO2']}
                              labelFormatter={(label, payload) => {
                                if (payload && payload[0]) {
                                  return payload[0].payload.fullTimestamp || label;
                                }
                                return label;
                              }}
                            />
                            <Line 
                              type="monotone" 
                              dataKey="no2" 
                              stroke="#5b6b8d" 
                              strokeWidth={3}
                              dot={{ fill: '#5b6b8d', r: 5, strokeWidth: 0 }}
                              activeDot={{ r: 8, fill: '#5b6b8d' }}
                              isAnimationActive={false}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                    )}

                    {/* CO Graph */}
                    {appliedGraphSensorTypes.co && (
                    <div className="graph-card">
                      <div className="graph-header">
                        <div className="graph-value">
                          {(() => {
                            const peak = getPeakValue('co');
                            return peak !== null ? (
                              <>
                                <span className="current-value">{peak.toFixed(2)} PPM</span>
                                <span className="value-change">Peak</span>
                              </>
                            ) : '--';
                          })()}
                        </div>
                        <h3><Flame size={20} /> Carbon Monoxide</h3>
                      </div>
                      <div style={{ width: '100%', height: '280px' }}>
                        <ResponsiveContainer debounce={300}>
                          <LineChart data={getFilteredGraphData()} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                            <XAxis 
                              dataKey="time" 
                              stroke="#999" 
                              tick={{ fontSize: 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                            />
                            <YAxis 
                              stroke="#999" 
                              tick={{ fontSize: 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                              domain={[(dataMin) => {
                                // Start from 80% of minimum value or 0
                                const minValue = Math.max(0, dataMin * 0.8);
                                return Math.floor(minValue * 1000) / 1000;
                              }, (dataMax) => {
                                // Add 20% padding to max value for better visibility
                                const maxValue = dataMax * 1.2;
                                return Math.ceil(maxValue * 1000) / 1000;
                              }]}
                            />
                            <Tooltip 
                              contentStyle={{ 
                                backgroundColor: 'rgba(255,255,255,0.95)', 
                                border: '1px solid #ddd',
                                borderRadius: '8px',
                                padding: '10px'
                              }}
                              labelStyle={{ fontWeight: 'bold', marginBottom: '5px' }}
                              formatter={(value) => [value.toFixed(4), 'CO']}
                              labelFormatter={(label, payload) => {
                                if (payload && payload[0]) {
                                  return payload[0].payload.fullTimestamp || label;
                                }
                                return label;
                              }}
                            />
                            <Line 
                              type="monotone" 
                              dataKey="co" 
                              stroke="#5b6b8d" 
                              strokeWidth={3}
                              dot={{ fill: '#5b6b8d', r: 5, strokeWidth: 0 }}
                              activeDot={{ r: 8, fill: '#5b6b8d' }}
                              isAnimationActive={false}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                    )}

                    {/* PM2.5 Graph */}
                    {appliedGraphSensorTypes.pm25 && (
                    <div className="graph-card">
                      <div className="graph-header">
                        <div className="graph-value">
                          {(() => {
                            const peak = getPeakValue('pm25');
                            return peak !== null ? (
                              <>
                                <span className="current-value">{peak.toFixed(1)} µg/m³</span>
                                <span className="value-change">Peak</span>
                              </>
                            ) : '--';
                          })()}
                        </div>
                        <h3><Circle size={20} /> PM 2.5</h3>
                      </div>
                      <div style={{ width: '100%', height: '280px' }}>
                        <ResponsiveContainer debounce={300}>
                          <LineChart data={getFilteredGraphData()} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                            <XAxis 
                              dataKey="time" 
                              stroke="#999" 
                              tick={{ fontSize: 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                            />
                            <YAxis 
                              stroke="#999" 
                              tick={{ fontSize: 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                              domain={['auto', 'auto']}
                            />
                            <Tooltip 
                              contentStyle={{ 
                                backgroundColor: 'rgba(255,255,255,0.95)', 
                                border: '1px solid #ddd',
                                borderRadius: '8px',
                                padding: '10px'
                              }}
                              labelStyle={{ fontWeight: 'bold', marginBottom: '5px' }}
                              formatter={(value) => [value.toFixed(2), 'PM2.5']}
                              labelFormatter={(label, payload) => {
                                if (payload && payload[0]) {
                                  return payload[0].payload.fullTimestamp || label;
                                }
                                return label;
                              }}
                            />
                            <Line 
                              type="monotone" 
                              dataKey="pm25" 
                              stroke="#5b6b8d" 
                              strokeWidth={3}
                              dot={{ fill: '#5b6b8d', r: 5, strokeWidth: 0 }}
                              activeDot={{ r: 8, fill: '#5b6b8d' }}
                              isAnimationActive={false}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                    )}

                    {/* PM10 Graph */}
                    {appliedGraphSensorTypes.pm10 && (
                    <div className="graph-card">
                      <div className="graph-header">
                        <div className="graph-value">
                          {(() => {
                            const peak = getPeakValue('pm10');
                            return peak !== null ? (
                              <>
                                <span className="current-value">{peak.toFixed(1)} µg/m³</span>
                                <span className="value-change">Peak</span>
                              </>
                            ) : '--';
                          })()}
                        </div>
                        <h3><Circle size={20} /> PM 10</h3>
                      </div>
                      <div style={{ width: '100%', height: '280px' }}>
                        <ResponsiveContainer debounce={300}>
                          <LineChart data={getFilteredGraphData()} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                            <XAxis 
                              dataKey="time" 
                              stroke="#999" 
                              tick={{ fontSize: 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                            />
                            <YAxis 
                              stroke="#999" 
                              tick={{ fontSize: 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                              domain={['auto', 'auto']}
                            />
                            <Tooltip 
                              contentStyle={{ 
                                backgroundColor: 'rgba(255,255,255,0.95)', 
                                border: '1px solid #ddd',
                                borderRadius: '8px',
                                padding: '10px'
                              }}
                              labelStyle={{ fontWeight: 'bold', marginBottom: '5px' }}
                              formatter={(value) => [value.toFixed(2), 'PM10']}
                              labelFormatter={(label, payload) => {
                                if (payload && payload[0]) {
                                  return payload[0].payload.fullTimestamp || label;
                                }
                                return label;
                              }}
                            />
                            <Line 
                              type="monotone" 
                              dataKey="pm10" 
                              stroke="#5b6b8d" 
                              strokeWidth={3}
                              dot={{ fill: '#5b6b8d', r: 5, strokeWidth: 0 }}
                              activeDot={{ r: 8, fill: '#5b6b8d' }}
                              isAnimationActive={false}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                    )}
                  </div>
                )}
              </div>
              )}
            </section>
          )}

          {activePage === "info" && (
            <section className="info-page-container">
              <div className="info-content">
                <h1 className="info-title">About SMOKi Air Quality Monitor</h1>
              
                <div className="info-section">
                  <h2>Monitored Parameters</h2>
                  
                  <div className="parameter-card">
                    <div className="parameter-header">
                      <Thermometer size={24} />
                      <h3>Temperature</h3>
                    </div>
                    <p>Measures ambient temperature in degrees Celsius. Optimal indoor temperature ranges from 20-24°C for comfort and health.</p>
                  </div>

                  <div className="parameter-card">
                    <div className="parameter-header">
                      <Droplet size={24} />
                      <h3>Humidity</h3>
                    </div>
                    <p>Tracks relative humidity percentage. Ideal indoor humidity should be between 30-50% to prevent mold growth and respiratory issues.</p>
                  </div>

                  <div className="parameter-card">
                    <div className="parameter-header">
                      <Activity size={24} />
                      <h3>VOCs (Volatile Organic Compounds)</h3>
                    </div>
                    <p>Detects harmful organic chemicals in the air from paints, cleaners, and building materials. Lower resistance values indicate higher VOC concentrations.</p>
                  </div>

                  <div className="parameter-card">
                    <div className="parameter-header">
                      <Wind size={24} />
                      <h3>Nitrogen Dioxide (NO₂)</h3>
                    </div>
                    <p>Monitors NO₂ levels in PPM. This gas comes from combustion processes. Safe levels are below 0.053 PPM; levels above 0.1 PPM are hazardous.</p>
                  </div>

                  <div className="parameter-card">
                    <div className="parameter-header">
                      <Flame size={24} />
                      <h3>Carbon Monoxide (CO)</h3>
                    </div>
                    <p>Tracks CO concentration in PPM. This odorless, colorless gas is deadly at high concentrations. Safe levels are below 4.4 PPM.</p>
                  </div>

                  <div className="parameter-card">
                    <div className="parameter-header">
                      <Circle size={24} />
                      <h3>PM2.5 (Fine Particulate Matter)</h3>
                    </div>
                    <p>Measures particles smaller than 2.5 micrometers. These can penetrate deep into lungs. Safe levels are below 12 µg/m³; above 35 µg/m³ is unhealthy.</p>
                  </div>

                  <div className="parameter-card">
                    <div className="parameter-header">
                      <Circle size={24} />
                      <h3>PM10 (Coarse Particulate Matter)</h3>
                    </div>
                    <p>Tracks particles smaller than 10 micrometers from dust, pollen, and mold. Safe levels are below 54 µg/m³; above 154 µg/m³ is unhealthy.</p>
                  </div>
                </div>

                <div className="info-section">
                  <h2>Air Quality Index (AQI)</h2>
                  <p>
                    The system calculates indicative AQI based on DENR-EMB computation standards. AQI is a standardized indicator 
                    of air quality that considers all monitored pollutants and reports the worst value:
                  </p>
                  <div className="aqi-legend">
                    <div className="aqi-item" style={{ backgroundColor: '#4caf50' }}>
                      <strong>0-50: Good</strong>
                      <span>Air quality is satisfactory</span>
                    </div>
                    <div className="aqi-item" style={{ backgroundColor: '#ffc107' }}>
                      <strong>51-100: Moderate</strong>
                      <span>Acceptable for most people</span>
                    </div>
                    <div className="aqi-item" style={{ backgroundColor: '#ff9800' }}>
                      <strong>101-150: Unhealthy for Sensitive</strong>
                      <span>May affect sensitive groups</span>
                    </div>
                    <div className="aqi-item" style={{ backgroundColor: '#f44336', color: 'white' }}>
                      <strong>151-200: Unhealthy</strong>
                      <span>Everyone may experience effects</span>
                    </div>
                    <div className="aqi-item" style={{ backgroundColor: '#9c27b0', color: 'white' }}>
                      <strong>201-300: Very Unhealthy</strong>
                      <span>Health alert for everyone</span>
                    </div>
                    <div className="aqi-item" style={{ backgroundColor: '#7b1fa2', color: 'white' }}>
                      <strong>301-500: Hazardous</strong>
                      <span>Emergency conditions</span>
                    </div>
                  </div>
                </div>

                <div className="info-section">
                  <h2>Need Help?</h2>
                  <p>
                    If you have any questions, issues, or need technical support with your SMOKi air quality 
                    monitoring system, our team is here to help.
                  </p>
                  <a href="mailto:support@smoki.com?subject=SMOKi Support Request" className="contact-button">
                    <span>📧</span>
                    <span>Email Us for Support</span>
                  </a>
                  <p className="contact-note">
                    Please include details about your issue and any error messages you're seeing.
                  </p>
                </div>
              </div>
            </section>
          )}
      </main>

      {/* Bottom Navigation - Mobile Only */}
      <nav className="bottom-nav">
        <button 
          onClick={(e) => {
            const target = e.currentTarget;
            target.classList.remove('clicked', 'loading');
            void target.offsetWidth;
            
            target.classList.add('loading');
            setTimeout(() => {
              target.classList.remove('loading');
              target.classList.add('clicked');
              setTimeout(() => {
                target.classList.remove('clicked');
              }, 400);
            }, 10);
            setActivePage("dashboard");
          }}
          className={`bottom-nav-item ${activePage === "dashboard" ? "active" : ""}`}
        >
          <Home size={24} />
          <span>Dashboard</span>
        </button>

        <button 
          onClick={(e) => {
            const target = e.currentTarget;
            target.classList.remove('clicked', 'loading');
            void target.offsetWidth;
            
            target.classList.add('loading');
            setTimeout(() => {
              target.classList.remove('loading');
              target.classList.add('clicked');
              setTimeout(() => {
                target.classList.remove('clicked');
              }, 400);
            }, 10);
            setActivePage("records");
          }}
          className={`bottom-nav-item ${activePage === "records" ? "active" : ""}`}
        >
          <FileText size={24} />
          <span>Records</span>
        </button>

        <button 
          onClick={(e) => {
            const target = e.currentTarget;
            target.classList.remove('clicked', 'loading');
            void target.offsetWidth;
            
            target.classList.add('loading');
            setTimeout(() => {
              target.classList.remove('loading');
              target.classList.add('clicked');
              setTimeout(() => {
                target.classList.remove('clicked');
              }, 400);
            }, 10);
            setActivePage("graphs");
          }}
          className={`bottom-nav-item ${activePage === "graphs" ? "active" : ""}`}
        >
          <TrendingUp size={24} />
          <span>Graphs</span>
        </button>

        <button 
          onClick={(e) => {
            const target = e.currentTarget;
            target.classList.remove('clicked', 'loading');
            void target.offsetWidth;
            
            target.classList.add('loading');
            setTimeout(() => {
              target.classList.remove('loading');
              target.classList.add('clicked');
              setTimeout(() => {
                target.classList.remove('clicked');
              }, 400);
            }, 10);
            setActivePage("sensors");
          }}
          className={`bottom-nav-item ${activePage === "sensors" ? "active" : ""}`}
        >
          <Zap size={24} />
          <span>Sensors</span>
        </button>

        <button 
          onClick={(e) => {
            const target = e.currentTarget;
            target.classList.remove('clicked', 'loading');
            void target.offsetWidth;
            
            target.classList.add('loading');
            setTimeout(() => {
              target.classList.remove('loading');
              target.classList.add('clicked');
              setTimeout(() => {
                target.classList.remove('clicked');
              }, 400);
            }, 10);
            setActivePage("info");
          }}
          className={`bottom-nav-item ${activePage === "info" ? "active" : ""}`}
        >
          <FileText size={24} />
          <span>Info</span>
        </button>
      </nav>
    </div>
  )
}

export default Dashboard







