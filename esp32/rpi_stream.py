import hailo_platform as hp

import numpy as np

import cv2

import time

import subprocess

import os

import shutil

import threading

import requests

import json

from datetime import datetime, timezone

from picamera2 import Picamera2

from http.server import SimpleHTTPRequestHandler, HTTPServer

from socketserver import ThreadingMixIn



# CONFIGURATION

HEF_PATH    = os.getenv('HEF_PATH', r'/home/sevi/smoki_project/src/model-skhart-ready/smoke-seg-v3.hef')

HLS_DIR     = '/dev/shm/hls'  # RAM disk to prevent SD card lag

CONF_THRESH = 0.1

IOU_THRESH  = 0.45

CLASS_NAMES = ['smoke_black', 'smoke_white']

SMOKE_CLASSES = {'smoke_black', 'smoke_white'}

# All models to run consecutively per frame
ALL_MODELS = [
    {
        "hef": "/home/sevi/smoki_project/src/model-skhart-ready/smoke-seg-v3.hef",
        "classes": ["smoke_black", "smoke_white"],
        "type": "seg",
        "conf": 0.1
    },
    {
        "hef": "/home/sevi/smoki_project/src/model-skhart-ready/license-plate-v2.hef",
        "classes": ["license_plate"],
        "type": "detect",
        "conf": 0.3
    },
    {
        "hef": "/home/sevi/smoki_project/src/model-skhart-ready/vehicle-class-v2.hef",
        "classes": ["passenger", "puv", "services", "two_wheel"],
        "type": "detect",
        "conf": 0.3
    }
]



# Backend API configuration

BACKEND_URL = os.getenv('BACKEND_URL', 'http://192.168.1.20:8000')

CAMERA_ID = os.getenv('CAMERA_ID', 'rpi_camera_01')

CAMERA_LOCATION = os.getenv('CAMERA_LOCATION', 'unknown')



# Clean up and prepare RAM disk directory

if os.path.exists(HLS_DIR): shutil.rmtree(HLS_DIR)

os.makedirs(HLS_DIR, exist_ok=True)



# HLS SERVER

class HLSHandler(SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):

        super().__init__(*args, directory=HLS_DIR, **kwargs)

    

    def end_headers(self):

        self.send_header('Access-Control-Allow-Origin', '*')

        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')

        self.send_header('Access-Control-Allow-Headers', '*')

        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')

        super().end_headers()

    

    def do_OPTIONS(self):

        self.send_response(200)

        self.end_headers()



class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):

    allow_reuse_address = True



# HELPERS

def letterbox(img, size=640):

    h, w = img.shape[:2]

    r = size / max(h, w)

    new_w, new_h = int(w * r), int(h * r)

    img = cv2.resize(img, (new_w, new_h))

    pad_w, pad_h = size - new_w, size - new_h

    top, left = pad_h // 2, pad_w // 2

    img = cv2.copyMakeBorder(img, top, pad_h-top, left, pad_w-left, cv2.BORDER_CONSTANT, value=(114, 114, 114))

    return img, r, left, top



def decode(outputs, strides=[8, 16, 32], reg_max=16, conf_thresh=0.25):

    all_boxes, all_scores, all_classes = [], [], []

    for feat_idx, (feat, stride) in enumerate(zip(outputs, strides)):

        # Skip if output is too small or malformed

        if feat.size == 0:

            continue

        

        # Handle different output shapes

        if feat.ndim == 1:

            # 1D output - skip

            continue

        elif feat.ndim == 2:

            # 2D output (H*W, C) - transpose to (C, H, W)

            if feat.shape[0] < feat.shape[1]:

                feat = feat.T

            # Try to reshape

            try:

                H = W = int(np.sqrt(feat.shape[0]))

                if H * W == feat.shape[0]:

                    feat = feat.reshape(H, W, -1).transpose(2, 0, 1)

                else:

                    continue

            except:

                continue

        

        if feat.ndim != 3:

            continue

        

        C, H, W = feat.shape

        if C < 5:  # Need at least 4 box coords + 1 class

            continue

        

        box_feat, cls_feat = feat[:4*reg_max], feat[4*reg_max:]

        if cls_feat.size == 0:

            continue

        

        cls_scores = 1 / (1 + np.exp(-cls_feat))

        max_scores = cls_scores.max(axis=0)

        ys, xs = np.where(max_scores > conf_thresh)

        for y, x in zip(ys, xs):

            score = max_scores[y, x]

            cls_id = cls_scores[:, y, x].argmax()

            reg = box_feat[:, y, x].reshape(4, reg_max)

            reg_exp = np.exp(reg)

            reg = (reg_exp / reg_exp.sum(axis=1, keepdims=True) * np.arange(reg_max)).sum(axis=1)

            cx, cy = (x + 0.5) * stride, (y + 0.5) * stride

            all_boxes.append([cx-reg[0]*stride, cy-reg[1]*stride, cx+reg[2]*stride, cy+reg[3]*stride])

            all_scores.append(float(score))

            all_classes.append(int(cls_id))

    if len(all_boxes) == 0:

        return np.array([]), np.array([]), np.array([])

    return np.array(all_boxes), np.array(all_scores), np.array(all_classes)



def nms(boxes, scores, thresh):

    if len(boxes) == 0: return []

    x1, y1, x2, y2 = boxes.T

    areas = (x2-x1)*(y2-y1)

    order = scores.argsort()[::-1]

    keep = []

    while order.size > 0:

        i = order[0]; keep.append(i)

        xx1, yy1 = np.maximum(x1[i], x1[order[1:]]), np.maximum(y1[i], y1[order[1:]])

        xx2, yy2 = np.minimum(x2[i], x2[order[1:]]), np.minimum(y2[i], y2[order[1:]])

        w, h = np.maximum(0, xx2-xx1), np.maximum(0, yy2-yy1)

        ovr = (w*h)/(areas[i]+areas[order[1:]]-(w*h)+1e-6)

        order = order[1:][ovr < thresh]

    return keep



def send_frame_to_backend(frame, detections):
    """Push annotated frame as JPEG to backend"""
    try:
        _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
        payload = {
            "camera_id": CAMERA_ID,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "has_detection": len(detections) > 0,
            "detections": detections
        }
        requests.post(
            f"{BACKEND_URL}/api/stream/frame",
            files={"frame": ("frame.jpg", buf.tobytes(), "image/jpeg")},
            data={"metadata": json.dumps(payload)},
            timeout=2
        )
    except Exception:
        pass  # Don't block inference on network errors


def send_smoke_detection(timestamp, confidence, smoke_type, bounding_box, inference_time_ms):

    """Send smoke detection metadata to backend"""

    try:

        payload = {

            "timestamp": timestamp,

            "confidence": float(confidence),

            "smoke_type": smoke_type,

            "bounding_box": bounding_box,

            "camera_id": CAMERA_ID,

            "location": CAMERA_LOCATION,

            "metadata": {

                "inference_time_ms": inference_time_ms,

                "model": "smoki_model_v1",

                "confidence_threshold": CONF_THRESH

            }

        }

        response = requests.post(

            f"{BACKEND_URL}/api/detections/smoke",

            json=payload,

            timeout=5

        )

        if response.status_code == 200:

            print(f"✓ Smoke detection recorded: {smoke_type} ({confidence:.2f})")

        else:

            print(f"✗ Failed to record detection: {response.status_code}")

    except Exception as e:

        print(f"✗ Error sending detection: {e}")


def send_vehicle_detection(timestamp, frame_data, detections, inference_time_ms):
    """Send vehicle detection with frame and metadata to backend"""
    try:
        # Encode frame to JPEG
        _, frame_jpg = cv2.imencode('.jpg', frame_data)
        frame_bytes = frame_jpg.tobytes()
        
        payload = {
            "timestamp": timestamp,
            "camera_id": CAMERA_ID,
            "location": CAMERA_LOCATION,
            "detections": detections,
            "metadata": {
                "inference_time_ms": inference_time_ms,
                "frame_size": len(frame_bytes),
                "detection_count": len(detections)
            }
        }
        
        files = {
            'frame': ('frame.jpg', frame_bytes, 'image/jpeg'),
            'data': (None, json.dumps(payload), 'application/json')
        }
        
        response = requests.post(
            f"{BACKEND_URL}/api/detections/vehicle",
            files=files,
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"✓ Vehicle detection recorded: {len(detections)} objects")
        else:
            print(f"✗ Failed to record vehicle detection: {response.status_code}")
    except Exception as e:
        print(f"✗ Error sending vehicle detection: {e}")



# LOW-LATENCY FFmpeg ENCODER

def start_ffmpeg(w, h, fps=15):

    cmd = ['ffmpeg', '-y',

        '-f', 'rawvideo', '-vcodec', 'rawvideo',

        '-pix_fmt', 'bgr24', '-s', f'{w}x{h}', '-r', str(fps),

        '-i', '-', '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',

        '-b:v', '800k',

        '-g', str(fps * 2),     # Keyframe every 2 seconds

        '-hls_time', '2',       # 2-second segments

        '-hls_list_size', '4',  # Keep 4 segments for stability

        '-hls_segment_type', 'fmp4',

        '-hls_flags', 'delete_segments+append_list+independent_segments',

        '-f', 'hls', os.path.join(HLS_DIR, 'stream.m3u8')]

    return subprocess.Popen(cmd, stdin=subprocess.PIPE)



# MAIN PIPELINE

def run_inference():
    from rpi_hailo_inference import decode_seg, decode_detect, COLORS
    import queue as q

    print("[INFO] run_inference() called")
    
    try:
        print("[INFO] Initializing Picamera2...")
        picam2 = Picamera2()
        config = picam2.create_video_configuration(main={"format": "BGR888", "size": (640, 480)})
        picam2.configure(config)
        picam2.start()
        print("[OK] Camera started")
    except Exception as e:
        print(f"[ERROR] Camera init failed: {e}")
        import traceback
        traceback.print_exc()
        raise
    
    try:
        print("[INFO] Starting FFmpeg encoder...")
        ffmpeg_proc = start_ffmpeg(640, 480, fps=15)
        print("[OK] FFmpeg started")
    except Exception as e:
        print(f"[ERROR] FFmpeg init failed: {e}")
        import traceback
        traceback.print_exc()
        raise

    # Frame push queue (non-blocking)
    push_queue = q.Queue(maxsize=2)

    def frame_pusher():
        while True:
            try:
                frame, dets = push_queue.get(timeout=1)
                send_frame_to_backend(frame, dets)
            except Exception:
                pass

    threading.Thread(target=frame_pusher, daemon=True).start()

    # Load all models
    print("[INFO] Loading HEF models...")
    loaded_models = []
    for m in ALL_MODELS:
        try:
            hef = hp.HEF(m["hef"])
            loaded_models.append({"cfg": m, "hef": hef})
            print(f"[OK] Loaded: {m['hef'].split('/')[-1]}")
        except Exception as e:
            print(f"[ERROR] Failed to load {m['hef']}: {e}")
            import traceback
            traceback.print_exc()
            raise

    print(f"[INFO] All {len(loaded_models)} models loaded")

    try:
        with hp.VDevice() as target:
            print("[INFO] Configuring network groups...")
            # Configure all network groups
            configured = []
            for lm in loaded_models:
                try:
                    cp = hp.ConfigureParams.create_from_hef(lm["hef"], hp.HailoStreamInterface.PCIe)
                    ng = target.configure(lm["hef"], cp)[0]
                    ngp = ng.create_params()
                    in_p = hp.InputVStreamParams.make(ng, hp.FormatType.UINT8)
                    out_p = hp.OutputVStreamParams.make(ng, hp.FormatType.UINT8)
                    iname = lm["hef"].get_input_vstream_infos()[0].name
                    configured.append({
                        "cfg": lm["cfg"], "ng": ng, "ngp": ngp,
                        "in_p": in_p, "out_p": out_p, "iname": iname
                    })
                    print(f"[OK] Configured: {lm['cfg']['hef'].split('/')[-1]}")
                except Exception as e:
                    print(f"[ERROR] Failed to configure model: {e}")
                    import traceback
                    traceback.print_exc()
                    raise

            print(f"--- Low-Latency HLS Active (Sequential Multi-Model) ---")
            print(f"URL: http://localhost:8000/stream.m3u8")

            frame_count = 0
            while True:
                try:
                    start_time = time.time()

                    # 1. Capture
                    frame_bgr = picam2.capture_array()
                    resized = cv2.resize(frame_bgr, (640, 640))
                    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                    orig_size = (frame_bgr.shape[0], frame_bgr.shape[1])

                    vis_frame = frame_bgr.copy()
                    all_dets = []

                    # 2. Run each model consecutively
                    for model_idx, cm in enumerate(configured):
                        cfg = cm["cfg"]
                        input_data = {cm["iname"]: np.expand_dims(rgb.astype(np.uint8), 0)}

                        with hp.InferVStreams(cm["ng"], cm["in_p"], cm["out_p"]) as vstreams:
                            with cm["ng"].activate(cm["ngp"]):
                                raw_outputs = vstreams.infer(input_data)

                        # Debug: print output keys and shapes
                        if frame_count % 50 == 0:
                            print(f"\n[DEBUG] Model {model_idx} ({cfg['hef'].split('/')[-1]}) outputs:")
                            for key, val in raw_outputs.items():
                                print(f"  {key}: shape={val.shape}, dtype={val.dtype}, min={val.min():.3f}, max={val.max():.3f}")

                        if cfg["type"] == "seg":
                            dets = decode_seg(raw_outputs, orig_size, (640, 640), cfg["classes"], cfg["conf"])
                        else:
                            dets = decode_detect(raw_outputs, orig_size, (640, 640), cfg["classes"], cfg["conf"])

                        # Draw detections
                        for det in dets:
                            x1, y1, x2, y2 = det["bbox"]
                            color = COLORS[det["class_id"] % len(COLORS)]
                            label = f"{det['class_name']} {det['conf']:.2f}"
                            cv2.rectangle(vis_frame, (x1, y1), (x2, y2), color, 2)
                            cv2.putText(vis_frame, label, (x1, y1-10),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

                            # Send smoke detections to backend
                            if det["class_name"] in SMOKE_CLASSES:
                                timestamp = datetime.now(timezone.utc).isoformat()
                                bounding_box = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
                                inference_time_ms = (time.time() - start_time) * 1000
                                threading.Thread(
                                    target=send_smoke_detection,
                                    args=(timestamp, det["conf"], det["class_name"],
                                          bounding_box, int(inference_time_ms)),
                                    daemon=True
                                ).start()

                            all_dets.append({
                                "class": det["class_name"],
                                "conf": round(det["conf"], 3),
                                "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
                            })

                    # 3. Send vehicle detections to backend
                    if all_dets:
                        timestamp = datetime.now(timezone.utc).isoformat()
                        inference_time_ms = (time.time() - start_time) * 1000
                        threading.Thread(
                            target=send_vehicle_detection,
                            args=(timestamp, vis_frame.copy(), all_dets, int(inference_time_ms)),
                            daemon=True
                        ).start()
                    
                    # 4. Push frame to backend
                    if not push_queue.full():
                        push_queue.put_nowait((vis_frame.copy(), all_dets))

                    # 4. Push to HLS stream
                    try:
                        ffmpeg_proc.stdin.write(vis_frame.tobytes())
                        ffmpeg_proc.stdin.flush()
                    except (BrokenPipeError, OSError):
                        print("\n[WARNING] FFmpeg pipe broken, restarting...")
                        ffmpeg_proc = start_ffmpeg(640, 480, fps=15)

                    elapsed = time.time() - start_time
                    frame_count += 1
                    if frame_count % 10 == 0:
                        print(f"FPS: {1.0/elapsed:.2f} | Dets: {len(all_dets)} | Frame: {frame_count}")
                except Exception as e:
                    print(f"[ERROR] Frame processing failed: {e}")
                    import traceback
                    traceback.print_exc()
                    raise
    except Exception as e:
        print(f"[ERROR] VDevice context failed: {e}")
        import traceback
        traceback.print_exc()
        raise



if __name__ == '__main__':
    print("[START] rpi_stream.py initializing...")
    
    try:
        # Start HLS File Server
        print("[OK] Starting HLS server on port 8000...")
        threading.Thread(target=lambda: ThreadedHTTPServer(('', 8000), HLSHandler).serve_forever(), daemon=True).start()
        print("[OK] HLS server started")

        while True:
            try:
                print("[INFO] Starting inference loop...")
                run_inference()
            except KeyboardInterrupt:
                print("\nStopping...")
                break
            except Exception as e:
                import traceback
                print(f"\n[ERROR] {e}")
                traceback.print_exc()
                print(f"[INFO] Restarting in 3s...")
                time.sleep(3)
    except Exception as e:
        import traceback
        print(f"[FATAL] {e}")
        traceback.print_exc()
