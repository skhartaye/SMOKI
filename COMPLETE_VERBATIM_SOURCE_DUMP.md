SMOKI PROJECT COMPLETE SOURCE CODE DUMP
=======================================

File: esp32/rpi_simple_detect.py
=================================

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


File: backend/requirements.txt
==============================

fastapi==0.115.0
uvicorn[standard]==0.32.0
psycopg[binary]==3.3.2
python-dotenv==1.0.0
python-jose[cryptography]==3.3.0
bcrypt==4.2.1
python-multipart==0.0.9
websockets==14.1
requests==2.32.3


File: postgre/requirements.txt
==============================

psycopg2-binary==2.9.9
python-dotenv==1.0.0


File: frontend/.env
===================

VITE_API_URL=https://smoki-backend-rpi.onrender.com
VITE_API_URL_FALLBACK=http://192.168.100.199:8000
VITE_RPI_IP=192.168.100.199
VITE_HLS_PORT=8001

File: backend/stream.py
=======================

"""
Camera streaming module - serves HLS stream
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from collections import deque
import threading
import time
import os
import json
from pathlib import Path
from datetime import datetime, timezone

# Import database functions
import sys
sys.path.insert(0, '../postgre')
from database import insert_vehicle_detection_from_rpi, register_vehicle, create_violation

router = APIRouter(prefix="/api/stream", tags=["stream"])

class StreamManager:
    def __init__(self):
        self.latest_frame = None
        self.frame_buffer = deque(maxlen=60)  # Increased from 30 to 60 frames
        self.latest_metadata = None  # Store latest detection metadata
        self.lock = threading.Lock()
        self.fps = 0
        self.frame_count = 0
        self.last_time = time.time()
    
    def add_frame(self, frame_data: bytes, metadata: dict = None):
        """Store latest frame and metadata"""
        try:
            with self.lock:
                self.latest_frame = frame_data
                self.frame_buffer.append(frame_data)
                if metadata:
                    self.latest_metadata = metadata
                self.frame_count += 1
                
                # Calculate FPS
                current_time = time.time()
                if current_time - self.last_time >= 1.0:
                    self.fps = self.frame_count
                    self.frame_count = 0
                    self.last_time = current_time
            return True
        except Exception as e:
            print(f"Error adding frame: {e}")
            return False
    
    def get_latest_frame(self):
        """Get latest frame"""
        with self.lock:
            return self.latest_frame
    
    def get_mjpeg_stream(self):
        """Generate MJPEG stream at 60 FPS"""
        last_frame = None
        while True:
            frame = self.get_latest_frame()
            if frame and frame != last_frame:  # Only send if frame changed
                last_frame = frame
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Content-Length: ' + str(len(frame)).encode() + b'\r\n\r\n' + frame + b'\r\n')
            time.sleep(0.0167)  # ~60 FPS (1/60 = 0.0167)

# Global stream manager
stream_manager = StreamManager()

# ============ DETECTION PROCESSING ============

async def process_detections(frame_data: bytes, metadata: dict):
    """Process detection metadata and save to database"""
    try:
        if not metadata or not metadata.get('detections'):
            return
        
        detections = metadata.get('detections', [])
        camera_id = metadata.get('camera_id', 'unknown')
        location = metadata.get('location', 'Unknown')
        timestamp = metadata.get('timestamp')
        
        # Parse timestamp
        if timestamp:
            try:
                timestamp_dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except:
                timestamp_dt = datetime.now(timezone.utc)
        else:
            timestamp_dt = datetime.now(timezone.utc)
        
        # Filter for vehicle and license plate detections
        vehicle_detections = []
        license_plates = []
        smoke_detected = False
        
        for detection in detections:
            class_name = detection.get('class_name', '').lower()
            confidence = detection.get('confidence', 0.0)
            
            # Check for smoke detection
            if 'smoke' in class_name:
                smoke_detected = True
            
            # Check for vehicle detection
            elif class_name in ['passenger', 'puv', 'services', 'two_wheel', 'vehicle']:
                vehicle_detections.append(detection)
            
            # Check for license plate detection
            elif 'license' in class_name or 'plate' in class_name:
                license_plates.append(detection)
        
        # Always save detection data to database (even if no detections for monitoring)
        print(f"[DETECTION] Processing {len(vehicle_detections)} vehicles, {len(license_plates)} plates, smoke: {smoke_detected}")
        
        # Save to database using the existing function
        result = insert_vehicle_detection_from_rpi(
            timestamp=timestamp_dt,
            camera_id=camera_id,
            location=location,
            detections=detections,
            frame_data=frame_data,
            metadata=metadata
        )
        
        if result:
            print(f"[DB] Saved detection: ID={result['id']}, detections={result['detections_count']}")
            
            # Create violations for vehicles with smoke
            if smoke_detected and vehicle_detections:
                await create_smoke_violations(vehicle_detections, location, timestamp_dt)
            
    except Exception as e:
        print(f"[ERROR] Processing detections: {e}")
        import traceback
        traceback.print_exc()

async def create_smoke_violations(vehicle_detections: list, location: str, timestamp: datetime):
    """Create violations for vehicles detected with smoke"""
    try:
        for vehicle in vehicle_detections:
            # Generate a mock license plate for now (in real system, this would come from OCR)
            vehicle_type = vehicle.get('class_name', 'unknown')
            confidence = vehicle.get('confidence', 0.0)
            
            # Generate mock license plate based on vehicle type and timestamp
            plate_suffix = str(timestamp.minute).zfill(2) + str(timestamp.second).zfill(2)
            if vehicle_type == 'passenger':
                license_plate = f"ABC-{plate_suffix}"
            elif vehicle_type == 'puv':
                license_plate = f"PUV-{plate_suffix}"
            elif vehicle_type == 'services':
                license_plate = f"SVC-{plate_suffix}"
            elif vehicle_type == 'two_wheel':
                license_plate = f"MC-{plate_suffix}"
            else:
                license_plate = f"VEH-{plate_suffix}"
            
            print(f"[VIOLATION] Creating smoke violation for {license_plate} ({vehicle_type})")
            
            # Register vehicle
            vehicle_record = register_vehicle(license_plate, vehicle_type)
            
            if vehicle_record:
                # Create violation
                violation = create_violation(
                    vehicle_id=vehicle_record['id'],
                    detection_id=None,
                    violation_type="smoke_emission",
                    severity="warning" if confidence < 0.7 else "critical",
                    description=f"Smoke detected from {vehicle_type} at {location} (confidence: {confidence:.2f})"
                )
                
                if violation:
                    print(f"[VIOLATION] Created violation ID={violation['id']} for {license_plate}")
                
    except Exception as e:
        print(f"[ERROR] Creating smoke violations: {e}")

# ============ ENDPOINTS ============

@router.post("/frame")
async def receive_frame(frame: UploadFile = File(...), metadata: str = Form(None)):
    """Receive frame from RPi camera with optional metadata"""
    try:
        frame_data = await frame.read()
        print(f"[FRAME] Received frame: {len(frame_data)} bytes")
        
        # Parse metadata if provided
        meta_data = None
        if metadata:
            try:
                meta_data = json.loads(metadata)
                detections_count = meta_data.get('summary', {}).get('total_detections', 0)
                smoke_count = meta_data.get('summary', {}).get('smoke_detections', 0)
                vehicle_count = meta_data.get('summary', {}).get('vehicle_detections', 0)
                print(f"[FRAME] Metadata: {meta_data.get('camera_id', 'unknown')} - {detections_count} total, {smoke_count} smoke, {vehicle_count} vehicles")
                
                # Process detections and save to database
                await process_detections(frame_data, meta_data)
                
            except Exception as e:
                print(f"[FRAME] Metadata parse error: {e}")
        else:
            print(f"[FRAME] No metadata provided")
        
        if stream_manager.add_frame(frame_data, meta_data):
            return {
                "success": True,
                "fps": stream_manager.fps,
                "buffered_frames": len(stream_manager.frame_buffer)
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to process frame")
    except Exception as e:
        print(f"[FRAME] Frame receive error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stream.mjpeg")
async def get_mjpeg_stream():
    """Get MJPEG stream"""
    response = StreamingResponse(
        stream_manager.get_mjpeg_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Connection"] = "keep-alive"
    return response

@router.get("/latest.jpg")
async def get_latest_frame():
    """Get latest frame as JPEG"""
    frame = stream_manager.get_latest_frame()
    if not frame:
        raise HTTPException(status_code=503, detail="No frame available")
    
    response = StreamingResponse(
        iter([frame]),
        media_type="image/jpeg"
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    return response

@router.get("/status")
async def get_stream_status():
    """Get stream status with latest detection metadata"""
    with stream_manager.lock:
        latest_metadata = stream_manager.latest_metadata
    
    status_data = {
        "status": "active" if stream_manager.latest_frame else "idle",
        "fps": stream_manager.fps,
        "buffered_frames": len(stream_manager.frame_buffer),
        "latest_frame_size": len(stream_manager.latest_frame) if stream_manager.latest_frame else 0
    }
    
    # Include latest detection metadata if available
    if latest_metadata:
        status_data["latest_detections"] = latest_metadata.get("detections", [])
        status_data["detection_summary"] = latest_metadata.get("summary", {})
        status_data["camera_info"] = {
            "camera_id": latest_metadata.get("camera_id"),
            "location": latest_metadata.get("camera_location"),
            "timestamp": latest_metadata.get("timestamp")
        }
    
    return status_data

@router.post("/plate-crop")
async def receive_plate_crop(plate_crop: UploadFile = File(...), metadata: str = Form(None)):
    """Receive license plate crop from RPi for violator documentation"""
    try:
        crop_data = await plate_crop.read()
        print(f"[PLATE] Received crop: {len(crop_data)} bytes")
        
        # Parse metadata if provided
        meta_data = None
        if metadata:
            try:
                meta_data = json.loads(metadata)
                plate_text = meta_data.get('plate_text', 'unknown')
                ocr_conf = meta_data.get('ocr_confidence', 0.0)
                camera_id = meta_data.get('camera_id', 'unknown')
                location = meta_data.get('location', 'unknown')
                
                print(f"[PLATE] Violator plate crop: '{plate_text}' (OCR: {ocr_conf:.2f}) from {camera_id}")
                
                # TODO: Save plate crop to database or file system for evidence
                # For now, just log the receipt
                
            except Exception as e:
                print(f"[PLATE] Metadata parse error: {e}")
        
        return {
            "success": True,
            "message": "Plate crop received",
            "crop_size": len(crop_data)
        }
        
    except Exception as e:
        print(f"[PLATE] Crop receive error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ HLS PROXY ENDPOINTS ============

import requests

@router.get("/hls-proxy")
def hls_proxy():
    """Proxy HLS stream from RPi over HTTPS"""
    rpi_ip = os.getenv('RPI_IP', '192.168.1.35')
    hls_url = f"http://{rpi_ip}:8000/stream.m3u8"
    
    try:
        print(f"[HLS PROXY] Fetching from {hls_url}")
        response = requests.get(hls_url, timeout=5)
        response.raise_for_status()
        print(f"[HLS PROXY] Success: {len(response.content)} bytes")
        
        return StreamingResponse(
            iter([response.content]),
            media_type="application/vnd.apple.mpegurl",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-cache, no-store, must-revalidate"
            }
        )
    except requests.exceptions.Timeout:
        print(f"[HLS PROXY] Timeout connecting to {hls_url}")
        raise HTTPException(status_code=504, detail="RPi stream timeout")
    except requests.exceptions.ConnectionError as e:
        print(f"[HLS PROXY] Connection error: {e}")
        raise HTTPException(status_code=503, detail="Cannot reach RPi stream")
    except Exception as e:
        print(f"[HLS PROXY] Error: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to fetch HLS stream: {str(e)}")

@router.get("/debug")
async def debug_stream():
    """Debug endpoint to check stream state"""
    return {
        "has_frames": stream_manager.latest_frame is not None,
        "frame_size": len(stream_manager.latest_frame) if stream_manager.latest_frame else 0,
        "buffer_size": len(stream_manager.frame_buffer),
        "fps": stream_manager.fps,
        "endpoints": {
            "latest_frame": "/api/stream/latest.jpg",
            "mjpeg_stream": "/api/stream/stream.mjpeg",
            "status": "/api/stream/status",
            "plate_crop": "/api/stream/plate-crop"
        }
    }
File: postgre/database.py
==========================

import psycopg
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
File: frontend/src/Dashboard.jsx
=================================

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