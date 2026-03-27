#!/usr/bin/env python3
"""
rpi_snap.py  —  Smoki Project  |  Snapshot detection every 3 seconds
Sends to: https://smoki-backend-rpi.onrender.com (FastAPI)

Endpoints used (from /openapi.json):
  POST /api/stream/frame            — annotated JPEG every cycle
  POST /api/detections/snapshot     — DetectionSnapshot JSON every cycle
  POST /api/detections/smoke        — SmokeEvent JSON per smoke detection
  POST /api/detections/plate        — PlateEvent JSON per OCR result
  POST /api/stream/plate-crop       — plate crop JPEG per OCR result
  POST /api/detections/violation    — ViolationEvent when smoke+vehicle
  POST /api/vehicles/detect         — VehicleDetectionRequest per plate
  POST /api/vehicles/violation      — ViolationRequest per plate in violation
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
    PG_AVAILABLE = True
except ImportError:
    PG_AVAILABLE = False

# ─── CONFIGURATION ────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env.rpi'))
except ImportError:
    pass

INTERVAL        = 3.0
BACKEND_URL     = os.getenv('API_URL',         'https://smoki-backend-rpi.onrender.com')
CAMERA_ID       = os.getenv('DEVICE_ID',       'rpi_camera_01')
CAMERA_LOCATION = os.getenv('CAMERA_LOCATION', 'Main_Entrance')

DB_HOST     = os.getenv('DB_HOST',     'dpg-d5mc48fgi27c739ffhcg-a.oregon-postgres.render.com')
DB_NAME     = os.getenv('DB_NAME',     'smoki_db')
DB_USER     = os.getenv('DB_USER',     'smoki_db_user')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'HwlPtCgq1vW9KI45aHRuD1sbNwA03kFT')
DB_PORT     = int(os.getenv('DB_PORT', '5432'))

PLATE_CONF   = 0.3
SMOKE_CONF   = 0.53
VEHICLE_CONF = 0.3

ALL_MODELS = [
    {"hef": "/home/sevi/smoki_project/src/model-skhart-ready/smoke-hailo8l.hef",
     "classes": ["smoke_black", "smoke_white"], "type": "seg",
     "conf": SMOKE_CONF, "role": "smoke"},
    {"hef": "/home/sevi/smoki_project/src/model-skhart-ready/license-plate-opt-hailo8l.hef",
     "classes": ["license_plate"], "type": "detect",
     "conf": PLATE_CONF, "role": "plate_detect"},
    {"hef": "/home/sevi/smoki_project/src/model-skhart-ready/vehicle-class-hailo8l.hef",
     "classes": ["passenger", "puv", "services", "two_wheel"], "type": "detect",
     "conf": VEHICLE_CONF, "role": "vehicle"},
]

QUANT_PARAMS = {
    "yolov8n_seg/conv73": (0.087893,  69.0), "yolov8n_seg/conv74": (0.003922,  0.0),
    "yolov8n_seg/conv75": (0.018757, 162.0), "yolov8n_seg/conv60": (0.085621, 64.0),
    "yolov8n_seg/conv61": (0.003922,   0.0), "yolov8n_seg/conv62": (0.017188,174.0),
    "yolov8n_seg/conv44": (0.093213,  79.0), "yolov8n_seg/conv45": (0.003922,  0.0),
    "yolov8n_seg/conv46": (0.018580, 173.0), "yolov8n_seg/conv48": (0.021440, 14.0),
    "yolov8n/conv41":     (0.116865, 118.0), "yolov8n/conv42":     (0.040536,255.0),
    "yolov8n/conv52":     (0.120670,  92.0), "yolov8n/conv53":     (0.032743,255.0),
    "yolov8n/conv62":     (0.071806,  71.0), "yolov8n/conv63":     (0.022815,255.0),
}
VEHICLE_QUANT = {
    "yolov8n/conv41": (0.173322,145.0), "yolov8n/conv42": (0.160111,255.0),
    "yolov8n/conv52": (0.108191,147.0), "yolov8n/conv53": (0.123836,255.0),
    "yolov8n/conv62": (0.116450,101.0), "yolov8n/conv63": (0.152770,245.0),
}
COLORS = [(0,0,255),(0,255,0),(255,0,0),(0,255,255),(255,0,255),(255,255,0)]

# ─── BACKEND POOL ─────────────────────────────────────────────────────────────
_executor = ThreadPoolExecutor(max_workers=6, thread_name_prefix="backend")

def _post(url, **kwargs):
    try:
        r = requests.post(url, timeout=15, **kwargs)
        if r.status_code not in (200, 201):
            print(f"[HTTP] {r.status_code} {url}")
    except Exception as e:
        print(f"[HTTP] Failed {url}: {e}")

def submit(fn, *args):
    _executor.submit(fn, *args)

# ─── POSTGRESQL ───────────────────────────────────────────────────────────────
_pg_conn = None

def _get_pg():
    global _pg_conn
    if not PG_AVAILABLE:
        return None
    try:
        if _pg_conn is None or _pg_conn.closed:
            _pg_conn = psycopg2.connect(
                host=DB_HOST, dbname=DB_NAME, user=DB_USER,
                password=DB_PASSWORD, port=DB_PORT,
                connect_timeout=10, sslmode='require')
            _pg_conn.autocommit = True
        return _pg_conn
    except Exception as e:
        print(f"[PG] Connect failed: {e}")
        return None

def init_db():
    conn = _get_pg()
    if conn is None:
        print("[PG] No connection")
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT table_name FROM information_schema.tables
                           WHERE table_schema='public' ORDER BY table_name;""")
            tables = [r[0] for r in cur.fetchall()]
        print(f"[PG] Connected  tables: {', '.join(tables)}")
    except Exception as e:
        print(f"[PG] Error: {e}")

def pg_save_vehicle_detection(timestamp, plate_text, vehicle_type,
                               confidence, smoke_detected, emission_level, metadata):
    conn = _get_pg()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            vehicle_id = None
            if plate_text:
                cur.execute("""
                    INSERT INTO vehicles
                        (license_plate, vehicle_type, first_detected,
                         last_detected, total_violations, status)
                    VALUES (%s,%s,%s,%s,0,'active')
                    ON CONFLICT (license_plate) DO UPDATE
                        SET last_detected=EXCLUDED.last_detected,
                            vehicle_type=EXCLUDED.vehicle_type,
                            updated_at=NOW()
                    RETURNING id;
                """, (plate_text, vehicle_type, timestamp, timestamp))
                vehicle_id = cur.fetchone()[0]
            cur.execute("""
                INSERT INTO vehicle_detections
                    (vehicle_id, timestamp, location, confidence,
                     smoke_detected, emission_level, metadata)
                VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id;
            """, (vehicle_id, timestamp, CAMERA_LOCATION, confidence,
                  smoke_detected, emission_level, json.dumps(metadata)))
            return vehicle_id, cur.fetchone()[0]
    except Exception as e:
        print(f"[PG] vehicle_detection: {e}")
        return None

def pg_save_violation(vehicle_id, detection_id, timestamp,
                       violation_type, severity, description):
    conn = _get_pg()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO violations
                    (vehicle_id, detection_id, violation_type,
                     severity, timestamp, description, resolved)
                VALUES (%s,%s,%s,%s,%s,%s,FALSE) RETURNING id;
            """, (vehicle_id, detection_id, violation_type,
                  severity, timestamp, description))
            vid = cur.fetchone()[0]
            if vehicle_id:
                cur.execute("UPDATE vehicles SET total_violations=total_violations+1 WHERE id=%s;",
                            (vehicle_id,))
            return vid
    except Exception as e:
        print(f"[PG] violation: {e}")
        return None

def pg_save_image(violation_id, detection_id, frame_bgr, timestamp):
    conn = _get_pg()
    if not conn:
        return
    try:
        _, jpg = cv2.imencode('.jpg', frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
        jpg_b = jpg.tobytes()
        h, w = frame_bgr.shape[:2]
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO images
                    (violation_id, vehicle_detection_id, image_data,
                     image_format, file_size, width, height, timestamp)
                VALUES (%s,%s,%s,'jpeg',%s,%s,%s,%s);
            """, (violation_id, detection_id,
                  psycopg2.Binary(jpg_b), len(jpg_b), w, h, timestamp))
    except Exception as e:
        print(f"[PG] image: {e}")

def pg_save_notification(violation_id, timestamp, plate_text, opacity_level, smoke_type):
    conn = _get_pg()
    if not conn:
        return
    sev = {"dense":"CRITICAL","moderate":"WARNING","thin":"INFO"}.get(opacity_level,"WARNING")
    title = f"Smoke Violation — {sev}"
    msg = (f"Vehicle {plate_text or 'unknown'} emitting {smoke_type} "
           f"({opacity_level}) at {CAMERA_LOCATION}.")
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO notifications
                    (violation_id, title, message, notification_type, is_read, timestamp)
                VALUES (%s,%s,%s,%s,FALSE,%s);
            """, (violation_id, title, msg, sev, timestamp))
    except Exception as e:
        print(f"[PG] notification: {e}")

# ─── DEQUANTIZATION + DECODE ──────────────────────────────────────────────────
def dequant(raw, name, qmap):
    arr = raw.astype(np.float32)
    if name in qmap:
        s, z = qmap[name]
        return (arr - z) * s
    return arr

def dfl_decode(reg, stride):
    H, W, _ = reg.shape
    nb = 16
    r = reg.reshape(H, W, 4, nb)
    r = r - r.max(axis=-1, keepdims=True)
    rs = np.exp(r); rs /= rs.sum(axis=-1, keepdims=True)
    d = (rs * np.arange(nb, dtype=np.float32)).sum(axis=-1)
    gy, gx = np.meshgrid(np.arange(H), np.arange(W), indexing='ij')
    return ((gx+0.5-d[...,0])*stride, (gy+0.5-d[...,1])*stride,
            (gx+0.5+d[...,2])*stride, (gy+0.5+d[...,3])*stride)

def nms(dets, score_thresh=0.0, iou_thresh=0.45):
    if not dets:
        return []
    boxes = [[d["bbox"][0],d["bbox"][1],
              d["bbox"][2]-d["bbox"][0],d["bbox"][3]-d["bbox"][1]] for d in dets]
    scores = [d["conf"] for d in dets]
    idx = cv2.dnn.NMSBoxes(boxes, scores, float(score_thresh), float(iou_thresh))
    return [dets[i] for i in idx.flatten()] if len(idx) else []

def _lt(conf):
    eps = 1e-6
    c = float(np.clip(conf, eps, 1-eps))
    return float(np.log(c/(1-c)))

def decode_detect(outputs, orig_size, input_size, classes, conf_thresh,
                  iou_thresh=0.45, qmap=None):
    if qmap is None:
        qmap = QUANT_PARAMS
    rkeys = ["yolov8n/conv41","yolov8n/conv52","yolov8n/conv62"]
    ckeys = ["yolov8n/conv42","yolov8n/conv53","yolov8n/conv63"]
    oh, ow = orig_size
    sx, sy = ow/input_size[0], oh/input_size[1]
    lt = _lt(conf_thresh)
    dets = []
    for stride, rk, ck in zip([8,16,32], rkeys, ckeys):
        if rk not in outputs or ck not in outputs:
            continue
        reg = dequant(outputs[rk][0], rk, qmap)
        lg  = dequant(outputs[ck][0], ck, qmap)
        ls  = lg[...,0] if lg.shape[-1]==1 else lg.max(axis=-1)
        ci  = np.zeros(ls.shape,dtype=int) if lg.shape[-1]==1 else lg.argmax(axis=-1)
        mask = ls >= lt
        if not mask.any():
            continue
        sc = 1/(1+np.exp(-ls))
        x1, y1, x2, y2 = dfl_decode(reg, stride)
        for iy, ix in zip(*np.where(mask)):
            cid = int(ci[iy,ix])
            dets.append({"bbox":(int(np.clip(x1[iy,ix]*sx,0,ow)),
                                  int(np.clip(y1[iy,ix]*sy,0,oh)),
                                  int(np.clip(x2[iy,ix]*sx,0,ow)),
                                  int(np.clip(y2[iy,ix]*sy,0,oh))),
                          "conf":float(sc[iy,ix]), "class_id":cid,
                          "class_name":classes[cid] if cid<len(classes) else "?"})
    return nms(dets, score_thresh=conf_thresh, iou_thresh=iou_thresh)

def decode_seg(outputs, orig_size, input_size, classes, conf_thresh, iou_thresh=0.45):
    rkeys = ["yolov8n_seg/conv44","yolov8n_seg/conv60","yolov8n_seg/conv73"]
    ckeys = ["yolov8n_seg/conv45","yolov8n_seg/conv61","yolov8n_seg/conv74"]
    oh, ow = orig_size
    sx, sy = ow/input_size[0], oh/input_size[1]
    lt = _lt(conf_thresh)
    dets = []
    for stride, rk, ck in zip([8,16,32], rkeys, ckeys):
        if rk not in outputs:
            continue
        reg = dequant(outputs[rk][0], rk, QUANT_PARAMS)
        lg  = dequant(outputs[ck][0], ck, QUANT_PARAMS)
        ls  = lg.max(axis=-1)
        ci  = lg.argmax(axis=-1)
        mask = ls >= lt
        if not mask.any():
            continue
        sc = 1/(1+np.exp(-ls))
        x1, y1, x2, y2 = dfl_decode(reg, stride)
        for iy, ix in zip(*np.where(mask)):
            cid = int(ci[iy,ix])
            dets.append({"bbox":(int(np.clip(x1[iy,ix]*sx,0,ow)),
                                  int(np.clip(y1[iy,ix]*sy,0,oh)),
                                  int(np.clip(x2[iy,ix]*sx,0,ow)),
                                  int(np.clip(y2[iy,ix]*sy,0,oh))),
                          "conf":float(sc[iy,ix]), "class_id":cid,
                          "class_name":classes[cid] if cid<len(classes) else "?"})
    return nms(dets, score_thresh=conf_thresh, iou_thresh=iou_thresh)

# ─── SMOKE OPACITY ────────────────────────────────────────────────────────────
FRAME_AREA = 1280 * 720

def classify_smoke_opacity(det, frame_bgr=None):
    x1, y1, x2, y2 = det["bbox"]
    conf = det["conf"]
    area_score = min(1.0, ((x2-x1)*(y2-y1)/FRAME_AREA)/0.5)
    dark_score = 0.0
    if frame_bgr is not None:
        try:
            roi = frame_bgr[max(0,y1):min(frame_bgr.shape[0],y2),
                            max(0,x1):min(frame_bgr.shape[1],x2)]
            if roi.size > 0:
                g = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                dark_score = max(float(np.mean(g<80)), float(np.mean(g>200))*0.7)
        except:
            pass
    score = (0.5*conf + 0.3*area_score + 0.2*dark_score if dark_score > 0
             else 0.6*conf + 0.4*area_score)
    level = "dense" if score>=0.70 else "moderate" if score>=0.45 else "thin"
    return level, round(score, 3)

# ─── PLATE OCR ────────────────────────────────────────────────────────────────
def load_ocr():
    try:
        import easyocr
        reader = easyocr.Reader(['en'], gpu=False, verbose=False)
        print("[OK] EasyOCR ready")
        return reader
    except Exception as e:
        print(f"[WARNING] EasyOCR: {e}")
        return None

def read_plate(reader, crop_bgr):
    if reader is None or crop_bgr is None:
        return "", 0.0
    try:
        h, w = crop_bgr.shape[:2]
        if h < 100:
            crop_bgr = cv2.resize(crop_bgr, (int(w*100/h), 100),
                                  interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
        thresh = cv2.adaptiveThreshold(gray, 255,
                                       cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY, 11, 2)
        proc = cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)
        res = reader.readtext(proc,
                              allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
                              width_ths=0.7, height_ths=0.7,
                              detail=1, paragraph=False, batch_size=1)
        if not res:
            return "", 0.0
        res = sorted(res, key=lambda r: r[2], reverse=True)
        text = ''.join(c for c in ''.join(r[1] for r in res) if c.isalnum())
        return text.strip(), float(res[0][2])
    except Exception as e:
        print(f"[OCR] {e}")
        return "", 0.0

# ─── FRAME SERVER (port 8001) ─────────────────────────────────────────────────
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

_latest_jpg  = b''
_latest_lock = threading.Lock()

def update_frame(frame_bgr):
    global _latest_jpg
    _, jpg = cv2.imencode('.jpg', frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
    with _latest_lock:
        _latest_jpg = jpg.tobytes()

class _FrameHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/latest.jpg':
            with _latest_lock:
                data = _latest_jpg
            if not data:
                self.send_response(503); self.end_headers(); return
            self.send_response(200)
            self.send_header('Content-Type', 'image/jpeg')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(data)
        elif self.path == '/stream.mjpeg':
            self.send_response(200)
            self.send_header('Content-Type',
                             'multipart/x-mixed-replace; boundary=frame')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            try:
                while True:
                    with _latest_lock:
                        data = _latest_jpg
                    if data:
                        self.wfile.write(
                            b'--frame\r\nContent-Type: image/jpeg\r\n'
                            b'Content-Length: ' + str(len(data)).encode() +
                            b'\r\n\r\n' + data + b'\r\n')
                        self.wfile.flush()
                    time.sleep(0.5)
            except:
                pass
        else:
            self.send_response(404); self.end_headers()

    def log_message(self, *args):
        pass

class _ThreadedHTTP(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True

def start_frame_server(port=8001):
    srv = _ThreadedHTTP(('', port), _FrameHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    print(f"[OK] Frame server → http://<pi-ip>:{port}/latest.jpg")
    print(f"[OK] MJPEG stream → http://<pi-ip>:{port}/stream.mjpeg")

# ─── BACKEND SENDERS ──────────────────────────────────────────────────────────
def send_snapshot(frame_bgr, timestamp, all_dets, smoke_dets,
                  vehicle_dets, plate_results, inf_ms):
    is_violation = len(smoke_dets) > 0 and len(vehicle_dets) > 0
    _, jpg = cv2.imencode('.jpg', frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])

    # Send frame with properly formatted metadata for stream status
    _post(f"{BACKEND_URL}/api/stream/frame",
          files={"frame": ("frame.jpg", jpg.tobytes(), "image/jpeg")},
          data={"metadata": json.dumps({
              "camera_id": CAMERA_ID, 
              "camera_location": CAMERA_LOCATION,
              "timestamp": timestamp, 
              "is_violation": is_violation,
              "detections": all_dets,  # Include actual detection objects
              "summary": {
                  "total_detections": len(all_dets),
                  "smoke_detections": len(smoke_dets),
                  "vehicle_detections": len(vehicle_dets),
                  "plate_detections": len(plate_results)
              }
          })})

    # Send detection snapshot to database
    _post(f"{BACKEND_URL}/api/detections/snapshot", json={
        "timestamp": timestamp, "camera_id": CAMERA_ID, "location": CAMERA_LOCATION,
        "smoke_count": len(smoke_dets), "vehicle_count": len(vehicle_dets),
        "plate_count": len(plate_results), "is_violation": is_violation,
        "inference_ms": inf_ms, "detections_json": {"detections": all_dets},
    })

    flag = " VIOLATION" if is_violation else ""
    print(f"[Sent] smoke={len(smoke_dets)} veh={len(vehicle_dets)} "
          f"plates={len(plate_results)} inf={inf_ms}ms{flag}")


def send_smoke(timestamp, det, inf_ms, opacity_level, opacity_score):
    x1, y1, x2, y2 = det["bbox"]
    _post(f"{BACKEND_URL}/api/detections/smoke", json={
        "timestamp": timestamp, "camera_id": CAMERA_ID, "location": CAMERA_LOCATION,
        "smoke_type": det["class_name"], "opacity_level": opacity_level,
        "opacity_score": opacity_score, "confidence": det["conf"],
        "bbox": {"x1":x1,"y1":y1,"x2":x2,"y2":y2},
        "bbox_area_px": (x2-x1)*(y2-y1), "inference_ms": inf_ms,
    })
    print(f"  Smoke: {det['class_name']} | {opacity_level} "
          f"score={opacity_score:.2f} conf={det['conf']:.2f}")


def send_plate(timestamp, plate_text, ocr_conf, bbox, crop_bgr, inf_ms):
    x1, y1, x2, y2 = bbox
    _, jpg = cv2.imencode('.jpg', crop_bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])
    fname = f"plate_{plate_text}_{timestamp[11:19].replace(':','')}.jpg"
    _post(f"{BACKEND_URL}/api/stream/plate-crop",
          files={"plate_crop": (fname, jpg.tobytes(), "image/jpeg")},
          data={"metadata": json.dumps({
              "camera_id": CAMERA_ID, "location": CAMERA_LOCATION,
              "timestamp": timestamp, "plate_text": plate_text,
              "ocr_confidence": ocr_conf,
              "bbox": {"x1":x1,"y1":y1,"x2":x2,"y2":y2},
          })})
    _post(f"{BACKEND_URL}/api/detections/plate", json={
        "timestamp": timestamp, "camera_id": CAMERA_ID, "location": CAMERA_LOCATION,
        "plate_text": plate_text, "ocr_confidence": ocr_conf,
        "bbox": {"x1":x1,"y1":y1,"x2":x2,"y2":y2}, "inference_ms": inf_ms,
    })
    print(f"  Plate: '{plate_text}' ({ocr_conf:.2f})")


def send_vehicle_detect(timestamp, plate_text, vehicle_type,
                         confidence, smoke_detected, emission_level):
    if not plate_text:
        return
    _post(f"{BACKEND_URL}/api/vehicles/detect", json={
        "license_plate": plate_text, "vehicle_type": vehicle_type,
        "location": CAMERA_LOCATION, "confidence": confidence,
        "smoke_detected": smoke_detected, "emission_level": emission_level,
        "metadata": {"camera_id": CAMERA_ID, "timestamp": timestamp},
    })


def send_violation(timestamp, smoke_dets, vehicle_dets, plate_results, all_dets, inf_ms):
    plate_texts    = [p["text"] for p in plate_results if p.get("text")]
    opacity_levels = [d.get("opacity_level","thin") for d in smoke_dets]
    worst = max(smoke_dets, key=lambda d: d.get("opacity_score",0), default=None)
    sev = {"dense":"critical","moderate":"warning","thin":"low"}.get(
        worst.get("opacity_level","thin") if worst else "thin", "warning")

    _post(f"{BACKEND_URL}/api/detections/violation", json={
        "timestamp": timestamp, "camera_id": CAMERA_ID, "location": CAMERA_LOCATION,
        "smoke_count": len(smoke_dets), "vehicle_count": len(vehicle_dets),
        "plate_texts": plate_texts, "opacity_levels": opacity_levels,
        "detections_json": {"detections": all_dets}, "inference_ms": inf_ms,
    })

    smoke_type = worst.get("class_name","smoke") if worst else "smoke"
    opacity    = worst.get("opacity_level","unknown") if worst else "unknown"
    conf_val   = worst.get("conf", 0.0) if worst else 0.0
    for plate in plate_texts:
        _post(f"{BACKEND_URL}/api/vehicles/violation", json={
            "license_plate": plate, "violation_type": smoke_type, "severity": sev,
            "description": (f"Smoke ({smoke_type},{opacity}) at {CAMERA_LOCATION}. "
                            f"Confidence:{conf_val:.2f}."),
        })
    print(f"  VIOLATION: {len(plate_texts)} plates severity={sev}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print("[INFO] Starting camera...")
    picam2 = Picamera2()
    picam2.configure(picam2.create_still_configuration(
        main={"format": "RGB888", "size": (1280, 720)}))
    picam2.start()
    time.sleep(1)
    print("[OK] Camera ready")

    ocr = load_ocr()
    init_db()
    start_frame_server(8001)

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
            configured.append({"cfg":m,"ng":ng,"ngp":ngp,
                                "in_p":in_p,"out_p":out_p,"iname":iname})
            print(f"[OK] Configured: {m['hef'].split('/')[-1]}")

        print(f"\nPipeline ready — {BACKEND_URL}")
        print(f"Location: {CAMERA_LOCATION}  Interval: every {INTERVAL}s\n")

        snap_count = 0
        while True:
            loop_start = time.time()
            ts = datetime.now(timezone.utc).isoformat()

            # 1. Capture
            frame_bgr = cv2.cvtColor(picam2.capture_array(), cv2.COLOR_RGB2BGR)
            oh, ow = frame_bgr.shape[:2]
            orig_size = (oh, ow)
            resized   = cv2.resize(frame_bgr, (640, 640))
            rgb       = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            inp_uint8 = np.expand_dims(rgb.astype(np.uint8), 0)
            vis_frame = frame_bgr.copy()

            all_dets = []; smoke_dets = []; vehicle_dets = []; plate_dets = []

            # 2. Hailo inference
            t_inf = time.time()
            for cm in configured:
                cfg = cm["cfg"]
                try:
                    with hp.InferVStreams(cm["ng"], cm["in_p"], cm["out_p"]) as vs:
                        with cm["ng"].activate(cm["ngp"]):
                            raw_out = vs.infer({cm["iname"]: inp_uint8})
                except Exception as e:
                    print(f"[ERROR] {cfg['role']}: {e}")
                    continue

                dets = (decode_seg(raw_out, orig_size, (640,640),
                                   cfg["classes"], cfg["conf"])
                        if cfg["type"] == "seg"
                        else decode_detect(raw_out, orig_size, (640,640),
                                           cfg["classes"], cfg["conf"],
                                           qmap=VEHICLE_QUANT if cfg["role"]=="vehicle"
                                           else QUANT_PARAMS))

                for det in dets:
                    x1, y1, x2, y2 = det["bbox"]
                    color = COLORS[det["class_id"] % len(COLORS)]
                    cv2.rectangle(vis_frame, (x1,y1), (x2,y2), color, 2)
                    cv2.putText(vis_frame, f"{det['class_name']} {det['conf']:.2f}",
                                (x1, max(0,y1-8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                    rec = {"class": det["class_name"], "conf": round(det["conf"],3),
                           "bbox": {"x1":x1,"y1":y1,"x2":x2,"y2":y2}}
                    all_dets.append(rec)
                    if cfg["role"] == "smoke":
                        lvl, score = classify_smoke_opacity(det, frame_bgr)
                        det["opacity_level"] = lvl
                        det["opacity_score"] = score
                        smoke_dets.append(det)
                    elif cfg["role"] == "vehicle":
                        vehicle_dets.append(rec)
                    elif cfg["role"] == "plate_detect":
                        plate_dets.append(det)

            inf_ms = int((time.time() - t_inf) * 1000)

            # 3. Plate OCR
            plate_results = []
            for det in plate_dets:
                x1, y1, x2, y2 = det["bbox"]
                x1c, y1c = max(0,x1), max(0,y1)
                x2c, y2c = min(ow-1,x2), min(oh-1,y2)
                if x2c > x1c and y2c > y1c:
                    crop = frame_bgr[y1c:y2c, x1c:x2c].copy()
                    text, oconf = read_plate(ocr, crop)
                    if text:
                        plate_results.append({
                            "text": text, "confidence": round(oconf,3),
                            "bbox": {"x1":x1,"y1":y1,"x2":x2,"y2":y2}})
                        cv2.putText(vis_frame, text, (x1, y2+18),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 2)
                        submit(send_plate, ts, text, oconf, (x1,y1,x2,y2), crop, inf_ms)

            # 4. Send smoke events
            for det in smoke_dets:
                submit(send_smoke, ts, det, inf_ms,
                       det.get("opacity_level","thin"), det.get("opacity_score",0.0))

            # 5. Send vehicle detects
            is_violation = len(smoke_dets) > 0 and len(vehicle_dets) > 0
            for p in plate_results:
                vtype = vehicle_dets[0]["class"] if vehicle_dets else "unknown"
                submit(send_vehicle_detect, ts, p["text"], vtype, p["confidence"],
                       is_violation,
                       smoke_dets[0].get("opacity_level","none") if smoke_dets else "none")

            # 6. Send violation
            if is_violation:
                submit(send_violation, ts, smoke_dets, vehicle_dets,
                       plate_results, all_dets, inf_ms)

            # 7. Update local frame server + send snapshot
            update_frame(vis_frame)
            t_upload = time.time()
            send_snapshot(vis_frame.copy(), ts, all_dets, smoke_dets,
                          vehicle_dets, plate_results, inf_ms)
            upload_ms = int((time.time() - t_upload) * 1000)

            # 8. PostgreSQL
            ts_dt = datetime.fromisoformat(ts)
            if is_violation or plate_results:
                worst = max(smoke_dets, key=lambda d: d.get("opacity_score",0), default=None)
                sev = {"dense":"critical","moderate":"warning","thin":"low"}.get(
                    worst.get("opacity_level","thin") if worst else "thin", "warning")
                emission   = worst.get("opacity_level","none") if worst else "none"
                smoke_type = worst.get("class_name","smoke") if worst else "smoke"

                for p in plate_results:
                    vtype = vehicle_dets[0]["class"] if vehicle_dets else "unknown"
                    result = pg_save_vehicle_detection(
                        ts_dt, p["text"], vtype, p["confidence"],
                        is_violation, emission,
                        {"camera_id": CAMERA_ID, "inference_ms": inf_ms})
                    if result and is_violation:
                        vehicle_id, detection_id = result
                        violation_id = pg_save_violation(
                            vehicle_id, detection_id, ts_dt, smoke_type, sev,
                            f"{smoke_type} ({emission}) at {CAMERA_LOCATION}. Plate:{p['text']}.")
                        if violation_id:
                            submit(pg_save_image, violation_id, detection_id,
                                   vis_frame.copy(), ts_dt)
                            submit(pg_save_notification, violation_id, ts_dt,
                                   p["text"], emission, smoke_type)

            # 9. Summary
            snap_count += 1
            elapsed   = time.time() - loop_start
            sleep_for = max(0.0, INTERVAL - elapsed)
            print(f"[Snap #{snap_count}] {ts[11:19]}Z | "
                  f"Smoke:{len(smoke_dets)} Veh:{len(vehicle_dets)} "
                  f"Plates:{len(plate_results)} | "
                  f"inf={inf_ms}ms upload={upload_ms}ms "
                  f"total={elapsed*1000:.0f}ms next={sleep_for:.1f}s")
            time.sleep(sleep_for)


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--test',     action='store_true')
    parser.add_argument('--interval', type=float, default=INTERVAL)
    parser.add_argument('--output',   default='/home/sevi/smoki_project/test_snap.jpg')
    args = parser.parse_args()
    INTERVAL = args.interval
    print("[START] rpi_snap.py")

    if args.test:
        print("\n[TEST MODE] Single frame — no backend, saves annotated image\n")
        import sys

        picam2 = Picamera2()
        picam2.configure(picam2.create_still_configuration(
            main={"format": "RGB888", "size": (1280, 720)}))
        picam2.start()
        time.sleep(1)
        print("[OK] Camera ready")

        ocr = load_ocr()
        init_db()

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
                configured.append({"cfg":m,"ng":ng,"ngp":ngp,
                                    "in_p":in_p,"out_p":out_p,"iname":iname})
                print(f"[OK] {m['hef'].split('/')[-1]}")

            print("\n[TEST] Capturing frame...")
            frame_bgr = cv2.cvtColor(picam2.capture_array(), cv2.COLOR_RGB2BGR)
            picam2.stop(); picam2.close()

            oh, ow = frame_bgr.shape[:2]
            orig_size = (oh, ow)
            resized   = cv2.resize(frame_bgr, (640, 640))
            rgb       = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            inp_uint8 = np.expand_dims(rgb.astype(np.uint8), 0)
            vis_frame = frame_bgr.copy()
            print(f"[TEST] Frame: {ow}x{oh}")

            t_inf = time.time()
            for cm in configured:
                cfg = cm["cfg"]
                try:
                    with hp.InferVStreams(cm["ng"], cm["in_p"], cm["out_p"]) as vs:
                        with cm["ng"].activate(cm["ngp"]):
                            raw_out = vs.infer({cm["iname"]: inp_uint8})
                except Exception as e:
                    print(f"[ERROR] {cfg['role']}: {e}")
                    continue

                dets = (decode_seg(raw_out, orig_size, (640,640),
                                   cfg["classes"], cfg["conf"])
                        if cfg["type"] == "seg"
                        else decode_detect(raw_out, orig_size, (640,640),
                                           cfg["classes"], cfg["conf"],
                                           qmap=VEHICLE_QUANT if cfg["role"]=="vehicle"
                                           else QUANT_PARAMS))

                print(f"\n  [{cfg['role'].upper()}] {len(dets)} detection(s):")
                for det in dets:
                    extra = ""
                    if cfg["role"] == "smoke":
                        lvl, score = classify_smoke_opacity(det, frame_bgr)
                        extra = f"  opacity={lvl} ({score:.2f})"
                    print(f"    {det['class_name']:20s} conf={det['conf']:.3f} "
                          f"bbox={det['bbox']}{extra}")
                    x1, y1, x2, y2 = det["bbox"]
                    color = COLORS[det["class_id"] % len(COLORS)]
                    cv2.rectangle(vis_frame, (x1,y1), (x2,y2), color, 2)
                    cv2.putText(vis_frame, f"{det['class_name']} {det['conf']:.2f}",
                                (x1, max(0,y1-8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                    if cfg["role"] == "plate_detect":
                        x1c, y1c = max(0,x1), max(0,y1)
                        x2c, y2c = min(ow-1,x2), min(oh-1,y2)
                        if x2c > x1c and y2c > y1c:
                            crop = frame_bgr[y1c:y2c, x1c:x2c]
                            text, oconf = read_plate(ocr, crop)
                            if text:
                                print(f"    OCR: '{text}' ({oconf:.2f})")
                                cv2.putText(vis_frame, text, (x1, y2+18),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 2)

            inf_ms = int((time.time() - t_inf) * 1000)
            cv2.imwrite(args.output, vis_frame)
            print(f"\n[TEST] Done — inf={inf_ms}ms")
            print(f"[TEST] Saved → {args.output}")
            print(f"[TEST] scp sevi@<pi-ip>:{args.output} .")
            sys.exit(0)

try:
    main()
except KeyboardInterrupt:
    print("\n[INFO] Stopped.")
finally:
    _executor.shutdown(wait=False)