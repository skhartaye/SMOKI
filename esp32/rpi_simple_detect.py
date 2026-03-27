#!/usr/bin/env python3
"""
rpi_snap.py  —  Smoki Project  |  Snapshot detection every N seconds
═══════════════════════════════════════════════════════════════════════
Every INTERVAL seconds:
  1. Capture one frame from picam2
  2. Run smoke / license-plate / vehicle Hailo models
  3. Crop plate regions → EasyOCR
  4. Draw bounding boxes on annotated frame
  5. POST annotated JPEG + all metadata to backend
  6. Sleep until next interval

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

try:
    import psycopg2
    from psycopg2.extras import Json
    PG_AVAILABLE = True
except ImportError:
    PG_AVAILABLE = False
    print("[WARNING] psycopg2 not installed — PostgreSQL disabled")
    print("[INFO] Install: pip install psycopg2-binary --break-system-packages")

# ─── CONFIGURATION ────────────────────────────────────────────────────────────
# Load .env.rpi if present
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env.rpi'))
except ImportError:
    pass

INTERVAL        = 3.0
BACKEND_URL     = os.getenv('API_URL',          'https://smoki-backend-rpi.onrender.com')
CAMERA_ID       = os.getenv('DEVICE_ID',        'rpi_camera_01')
CAMERA_LOCATION = os.getenv('CAMERA_LOCATION',  'Main_Entrance')

# ─── POSTGRESQL CONFIG ────────────────────────────────────────────────────────
DB_HOST     = os.getenv('DB_HOST',     'dpg-d5mc48fgi27c739ffhcg-a.oregon-postgres.render.com')
DB_NAME     = os.getenv('DB_NAME',     'smoki_db')
DB_USER     = os.getenv('DB_USER',     'smoki_db_user')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'HwlPtCgq1vW9KI45aHRuD1sbNwA03kFT')
DB_PORT     = int(os.getenv('DB_PORT', '5432'))

SMOKE_CONF   = 0.53
VEHICLE_CONF = 0.3
PLATE_CONF   = 0.3

SMOKE_CLASSES   = {'smoke_black', 'smoke_white'}
VEHICLE_CLASSES = {'passenger', 'puv', 'services', 'two_wheel'}

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

# ─── PER-TENSOR QUANT PARAMS (from hef.get_output_vstream_infos()) ────────────
# float_value = (raw_uint8 - zp) * scale
QUANT_PARAMS = {
    # smoke
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
    # plate
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

# ─── POSTGRESQL ───────────────────────────────────────────────────────────────
_pg_conn = None

def _get_pg():
    """Return a live psycopg2 connection, reconnecting if dropped."""
    global _pg_conn
    if not PG_AVAILABLE:
        return None
    try:
        if _pg_conn is None or _pg_conn.closed:
            _pg_conn = psycopg2.connect(
                host=DB_HOST, dbname=DB_NAME,
                user=DB_USER, password=DB_PASSWORD, port=DB_PORT,
                connect_timeout=10,
                sslmode='require',
            )
            _pg_conn.autocommit = True
        return _pg_conn
    except Exception as e:
        print(f"[PG] Connect failed: {e}")
        return None

def init_db():
    """Create tables if they don't exist. Safe to call on every startup."""
    conn = _get_pg()
    if conn is None:
        print("[PG] Skipping schema init — no connection")
        return
    try:
        with conn.cursor() as cur:
            # Create tables first
            cur.execute("""
                CREATE TABLE IF NOT EXISTS detections (
                    id              BIGSERIAL PRIMARY KEY,
                    timestamp       TIMESTAMPTZ NOT NULL,
                    camera_id       TEXT NOT NULL,
                    location        TEXT,
                    smoke_count     INT  DEFAULT 0,
                    vehicle_count   INT  DEFAULT 0,
                    plate_count     INT  DEFAULT 0,
                    is_violation    BOOLEAN DEFAULT FALSE,
                    inference_ms    INT,
                    upload_ms       INT,
                    detections_json JSONB,
                    created_at      TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS smoke_events (
                    id            BIGSERIAL PRIMARY KEY,
                    timestamp     TIMESTAMPTZ NOT NULL,
                    camera_id     TEXT NOT NULL,
                    location      TEXT,
                    smoke_type    TEXT,
                    opacity_level TEXT,
                    opacity_score FLOAT,
                    confidence    FLOAT,
                    bbox          JSONB,
                    bbox_area_px  INT,
                    inference_ms  INT,
                    created_at    TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS plate_events (
                    id             BIGSERIAL PRIMARY KEY,
                    timestamp      TIMESTAMPTZ NOT NULL,
                    camera_id      TEXT NOT NULL,
                    location       TEXT,
                    plate_text     TEXT,
                    ocr_confidence FLOAT,
                    bbox           JSONB,
                    inference_ms   INT,
                    created_at     TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS violations (
                    id            BIGSERIAL PRIMARY KEY,
                    timestamp     TIMESTAMPTZ NOT NULL,
                    camera_id     TEXT NOT NULL,
                    location      TEXT,
                    smoke_count   INT DEFAULT 0,
                    vehicle_count INT DEFAULT 0,
                    plate_texts   TEXT[],
                    opacity_levels TEXT[],
                    detections_json JSONB,
                    inference_ms  INT,
                    created_at    TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            
            # Create indexes with individual error handling
            indexes = [
                ("idx_detections_ts", "detections(timestamp DESC)"),
                ("idx_smoke_events_ts", "smoke_events(timestamp DESC)"),
                ("idx_plate_events_ts", "plate_events(timestamp DESC)"),
                ("idx_violations_ts", "violations(timestamp DESC)"),
                ("idx_detections_cam", "detections(camera_id)"),
                ("idx_violations_cam", "violations(camera_id)")
            ]
            
            for idx_name, idx_def in indexes:
                try:
                    cur.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_def};")
                except Exception as idx_error:
                    print(f"[PG] Index {idx_name} creation failed (non-fatal): {idx_error}")
                    # Continue with other indexes
            
        print("[PG] Schema ready ✓")
    except Exception as e:
        print(f"[PG] Schema init error: {e}")
        # Don't raise - allow script to continue without local database


def pg_insert_detection(timestamp, smoke_count, vehicle_count, plate_count,
                         is_violation, inference_ms, upload_ms,
                         all_dets):
    conn = _get_pg()
    if conn is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO detections
                    (timestamp, camera_id, location, smoke_count, vehicle_count,
                     plate_count, is_violation, inference_ms,
                     upload_ms, detections_json)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (timestamp, CAMERA_ID, CAMERA_LOCATION,
                  smoke_count, vehicle_count, plate_count,
                  is_violation, inference_ms, upload_ms,
                  json.dumps(all_dets)))
    except Exception as e:
        print(f"[PG] detections insert error: {e}")


def pg_insert_smoke(timestamp, det, inference_ms):
    conn = _get_pg()
    if conn is None:
        return
    x1, y1, x2, y2 = det["bbox"]
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO smoke_events
                    (timestamp, camera_id, location, smoke_type, opacity_level,
                     opacity_score, confidence, bbox, bbox_area_px, inference_ms)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (timestamp, CAMERA_ID, CAMERA_LOCATION,
                  det.get("class_name"), det.get("opacity_level", "thin"),
                  det.get("opacity_score", 0.0), det.get("conf", 0.0),
                  json.dumps({"x1": x1, "y1": y1, "x2": x2, "y2": y2}),
                  (x2-x1)*(y2-y1), inference_ms))
    except Exception as e:
        print(f"[PG] smoke_events insert error: {e}")


def pg_insert_plate(timestamp, plate_text, ocr_conf, bbox, inference_ms):
    conn = _get_pg()
    if conn is None:
        return
    x1, y1, x2, y2 = bbox
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO plate_events
                    (timestamp, camera_id, location, plate_text,
                     ocr_confidence, bbox, inference_ms)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (timestamp, CAMERA_ID, CAMERA_LOCATION,
                  plate_text, ocr_conf,
                  json.dumps({"x1": x1, "y1": y1, "x2": x2, "y2": y2}),
                  inference_ms))
    except Exception as e:
        print(f"[PG] plate_events insert error: {e}")


def pg_insert_violation(timestamp, smoke_dets, vehicle_dets,
                         plate_results, all_dets, inference_ms):
    conn = _get_pg()
    if conn is None:
        return
    try:
        plate_texts    = [p["text"] for p in plate_results if p.get("text")]
        opacity_levels = [d.get("opacity_level", "thin") for d in smoke_dets]
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO violations
                    (timestamp, camera_id, location, smoke_count, vehicle_count,
                     plate_texts, opacity_levels, detections_json, inference_ms)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (timestamp, CAMERA_ID, CAMERA_LOCATION,
                  len(smoke_dets), len(vehicle_dets),
                  plate_texts, opacity_levels,
                  json.dumps(all_dets), inference_ms))
    except Exception as e:
        print(f"[PG] violations insert error: {e}")

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
# Opacity is determined by two factors combined:
#   1. Detection confidence  (model certainty)
#   2. Bounding box area ratio (larger = more spread smoke = denser)
# Thresholds tuned for 1280x720 frame (921600 total pixels)
FRAME_AREA = 1280 * 720

def classify_smoke_opacity(det, frame_bgr=None):
    """
    Returns 'thin' | 'moderate' | 'dense' + opacity_score (0.0–1.0).

    Scoring:
      conf_score  = sigmoid-space confidence (already 0–1)
      area_score  = bbox_area / FRAME_AREA, clamped to [0, 0.5], normalized
      opacity_score = 0.6 * conf_score + 0.4 * area_score

    Optionally uses pixel darkness analysis on the ROI if frame_bgr provided:
      dark_ratio = fraction of pixels below brightness threshold in the bbox
      If available, blends in: 0.5*conf + 0.3*area + 0.2*dark
    """
    x1, y1, x2, y2 = det["bbox"]
    conf = det["conf"]

    bbox_area  = max(1, (x2 - x1) * (y2 - y1))
    area_score = min(1.0, (bbox_area / FRAME_AREA) / 0.5)   # saturates at 50% frame

    # Optional pixel darkness — black smoke is darker than white smoke
    dark_score = 0.0
    if frame_bgr is not None:
        try:
            roi = frame_bgr[max(0,y1):min(frame_bgr.shape[0],y2),
                            max(0,x1):min(frame_bgr.shape[1],x2)]
            if roi.size > 0:
                gray       = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                dark_ratio = float(np.mean(gray < 80))   # fraction of dark pixels
                bright_ratio = float(np.mean(gray > 200))  # white smoke
                dark_score = max(dark_ratio, bright_ratio * 0.7)
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
    """
    Upscale + adaptive threshold for best OCR accuracy on PH plates.
    Returns BGR image suitable for EasyOCR.
    """
    h, w = crop_bgr.shape[:2]
    # Upscale to at least 100px tall
    if h < 100:
        scale = 100 / h
        crop_bgr = cv2.resize(crop_bgr, (int(w * scale), 100),
                              interpolation=cv2.INTER_CUBIC)
    # Adaptive threshold — handles varied lighting
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
        results = reader.readtext(
            processed,
            allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
            width_ths=0.7, height_ths=0.7,
            detail=1, paragraph=False, batch_size=1,
        )
        if not results:
            return "", 0.0
        results = sorted(results, key=lambda r: r[2], reverse=True)
        # Strip non-alphanumeric and join
        text = ''.join(c for c in ''.join(r[1] for r in results) if c.isalnum())
        conf = float(results[0][2])
        return text.strip(), conf
    except Exception as e:
        print(f"[OCR] Error: {e}")
        return "", 0.0

# ─── BACKEND SENDERS ──────────────────────────────────────────────────────────
def send_snapshot(frame_bgr, timestamp, all_dets, smoke_dets,
                  vehicle_dets, plate_results, inf_ms):
    _, jpg = cv2.imencode('.jpg', frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])

    is_violation = len(smoke_dets) > 0 and len(vehicle_dets) > 0

    payload = {
        "camera_id":       CAMERA_ID,
        "location":        CAMERA_LOCATION,
        "timestamp":       timestamp,
        "has_detection":   len(all_dets) > 0,
        "is_violation":    is_violation,
        "detections":      all_dets,
        "plates":          plate_results,
        "summary": {
            "total_detections":  len(all_dets),
            "smoke_detections":  len(smoke_dets),
            "smoke_opacity_levels": {
                "thin":     sum(1 for d in smoke_dets if d.get("opacity_level") == "thin"),
                "moderate": sum(1 for d in smoke_dets if d.get("opacity_level") == "moderate"),
                "dense":    sum(1 for d in smoke_dets if d.get("opacity_level") == "dense"),
            },
            "vehicle_detections": len(vehicle_dets),
            "plate_detections":  len(plate_results),
            "plates_with_text":  sum(1 for p in plate_results if p.get("text")),
            "inference_time_ms": inf_ms,
            "frame_size_bytes":  len(jpg),
            "violation_detected": is_violation,
        },
    }
    _post(f"{BACKEND_URL}/api/stream/frame",
          files={"frame": ("frame.jpg", jpg.tobytes(), "image/jpeg")},
          data={"metadata": json.dumps(payload)})

    flag = " 🚨 VIOLATION" if is_violation else ""
    print(f"[Sent] smoke={len(smoke_dets)} veh={len(vehicle_dets)} "
          f"plates={len(plate_results)} "
          f"inf={inf_ms}ms{flag}")


def send_smoke(timestamp, det, inf_ms, opacity_level, opacity_score, frame_bgr=None):
    x1, y1, x2, y2 = det["bbox"]

    # Optionally attach a cropped smoke ROI
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
        "timestamp":      timestamp,
        "camera_id":      CAMERA_ID,
        "location":       CAMERA_LOCATION,
        "confidence":     det["conf"],
        "smoke_type":     det["class_name"],   # smoke_black | smoke_white
        "opacity_level":  opacity_level,        # thin | moderate | dense
        "opacity_score":  opacity_score,        # 0.0 – 1.0
        "bounding_box":   {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
        "bbox_area_px":   (x2-x1) * (y2-y1),
        "inference_time_ms": inf_ms,
    }

    if files:
        _post(f"{BACKEND_URL}/api/detections/smoke",
              files=files,
              data={"metadata": json.dumps(payload)})
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
              "camera_id":    CAMERA_ID,
              "location":     CAMERA_LOCATION,
              "timestamp":    timestamp,
              "plate_text":   plate_text,
              "ocr_confidence": ocr_conf,
              "bbox":         {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
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
    time.sleep(1)   # warm up
    print("[OK] Camera ready")

    # ── OCR ───────────────────────────────────────────────────────────────────
    ocr = load_ocr()

    # ── PostgreSQL ────────────────────────────────────────────────────────────
    init_db()

    # ── Hailo ─────────────────────────────────────────────────────────────────
    print("[INFO] Loading Hailo models...")
    from hailo_platform import HailoSchedulingAlgorithm
    vparams = hp.VDevice.create_params()
    vparams.scheduling_algorithm = HailoSchedulingAlgorithm.ROUND_ROBIN

    hefs = [hp.HEF(m["hef"]) for m in ALL_MODELS]
    for m in ALL_MODELS:
        print(f"[OK] Loaded: {m['hef'].split('/')[-1]}")

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
            # picamera2 returns RGB even with BGR888 format — convert to BGR
            frame_bgr = cv2.cvtColor(picam2.capture_array(), cv2.COLOR_RGB2BGR)
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
                        with cm["ng"].activate(cm["ngp"]):
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

            # ── 3. Plate OCR ──────────────────────────────────────────────────
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
                        # Draw plate text on frame
                        cv2.putText(vis_frame, text, (x1, y2+18),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 2)
                        # Send individual plate event
                        submit(send_plate, ts, text, oconf,
                               (x1,y1,x2,y2), crop, inf_ms)

            # ── 5. Send smoke events ──────────────────────────────────────────
            for det in smoke_dets:
                submit(send_smoke, ts, det, inf_ms,
                       det.get("opacity_level", "thin"),
                       det.get("opacity_score", 0.0),
                       frame_bgr.copy())

            # ── 6. Send full snapshot (timed) ────────────────────────────────
            t_upload = time.time()
            send_snapshot(vis_frame.copy(), ts, all_dets,
                          smoke_dets, vehicle_dets, plate_results, inf_ms)
            upload_ms = int((time.time() - t_upload) * 1000)

            # ── 7. Save to PostgreSQL ─────────────────────────────────────────
            is_violation = len(smoke_dets) > 0 and len(vehicle_dets) > 0
            ts_dt = datetime.fromisoformat(ts)

            submit(pg_insert_detection, ts_dt,
                   len(smoke_dets), len(vehicle_dets), len(plate_results),
                   is_violation, inf_ms, upload_ms, all_dets)

            for det in smoke_dets:
                submit(pg_insert_smoke, ts_dt, det, inf_ms)

            for p in plate_results:
                if p.get("text"):
                    bbox = (p["bbox"]["x1"], p["bbox"]["y1"],
                            p["bbox"]["x2"], p["bbox"]["y2"])
                    submit(pg_insert_plate, ts_dt, p["text"],
                           p["confidence"], bbox, inf_ms)

            if is_violation:
                submit(pg_insert_violation, ts_dt, smoke_dets,
                       vehicle_dets, plate_results, all_dets, inf_ms)

            # ── 7. Print summary ──────────────────────────────────────────────
            snap_count += 1
            elapsed = time.time() - loop_start
            sleep_for = max(0.0, INTERVAL - elapsed)
            print(f"[Snap #{snap_count}] {ts[:19]}Z | "
                  f"Smoke:{len(smoke_dets)} Veh:{len(vehicle_dets)} "
                  f"Plates:{len(plate_results)} | "
                  f"inf={inf_ms}ms upload={upload_ms}ms total={elapsed*1000:.0f}ms "
                  f"next_in={sleep_for:.1f}s")

            # ── 8. Sleep remainder of interval ────────────────────────────────
            sleep_for = max(0.0, INTERVAL - elapsed)
            time.sleep(sleep_for)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--test',     action='store_true',
                        help='Capture one frame, run inference, save annotated image, exit')
    parser.add_argument('--interval', type=float, default=INTERVAL,
                        help=f'Seconds between snapshots (default {INTERVAL})')
    parser.add_argument('--output',   default='/home/sevi/smoki_project/test_snap.jpg',
                        help='Output path for --test image')
    args = parser.parse_args()

    INTERVAL = args.interval

    print("[START] rpi_snap.py")

    if args.test:
        # ── Single-frame test ─────────────────────────────────────────────────
        print("\n[TEST MODE] Single frame — no backend, saves annotated image\n")
        import sys

        picam2 = Picamera2()
        picam2.configure(picam2.create_still_configuration(
            main={"format": "RGB888", "size": (1280, 720)}))
        picam2.start()
        time.sleep(1)
        print("[OK] Camera ready")

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
            frame_bgr = cv2.cvtColor(picam2.capture_array(), cv2.COLOR_RGB2BGR)
            picam2.stop(); picam2.close()

            orig_h, orig_w = frame_bgr.shape[:2]
            orig_size  = (orig_h, orig_w)
            resized    = cv2.resize(frame_bgr, (640, 640))
            rgb        = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            inp_uint8  = np.expand_dims(rgb.astype(np.uint8), 0)
            vis_frame  = frame_bgr.copy()

            print(f"[TEST] Frame: {orig_w}x{orig_h}")

            t_inf = time.time()
            for cm in configured:
                cfg      = cm["cfg"]
                inp_data = {cm["iname"]: inp_uint8}
                try:
                    with hp.InferVStreams(cm["ng"], cm["in_p"], cm["out_p"]) as vs:
                        with cm["ng"].activate(cm["ngp"]):
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

                    # OCR on plate crops
                    if cfg["role"] == "plate_detect":
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

            cv2.imwrite(args.output, vis_frame)
            print(f"\n[TEST] Done — inf={inf_ms}ms")
            print(f"[TEST] Saved annotated image → {args.output}")
            print(f"[TEST] Copy to view: scp sevi@192.168.100.199:{args.output} .")
            sys.exit(0)

    # ── Normal loop mode ──────────────────────────────────────────────────────
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INFO] Stopped.")
    finally:
        _executor.shutdown(wait=False)