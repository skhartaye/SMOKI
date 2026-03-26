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