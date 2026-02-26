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

# ─── CONFIGURATION ─────────────────────────────────────────────────────────
HEF_PATH    = r'/home/sevi/smoki_project/models/smoki_model_v1.hef'
HLS_DIR     = '/dev/shm/hls'  # RAM disk to prevent SD card lag
CONF_THRESH = 0.25
IOU_THRESH  = 0.45
CLASS_NAMES = ['passenger', 'puv', 'service', 'two_wheel', 'license_plate', 'exhaust_pipe', 'smoke_black', 'smoke_white']
SMOKE_CLASSES = {'smoke_black', 'smoke_white'}

# Backend API configuration
BACKEND_URL = os.getenv('BACKEND_URL', 'http://localhost:8000')
CAMERA_ID = os.getenv('CAMERA_ID', 'rpi_camera_01')
CAMERA_LOCATION = os.getenv('CAMERA_LOCATION', 'unknown')

# Clean up and prepare RAM disk directory
if os.path.exists(HLS_DIR): shutil.rmtree(HLS_DIR)
os.makedirs(HLS_DIR, exist_ok=True)

# ─── HLS SERVER ────────────────────────────────────────────────────────────
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

# ─── HELPERS ───────────────────────────────────────────────────────────────
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
    for feat, stride in zip(outputs, strides):
        C, H, W = feat.shape
        box_feat, cls_feat = feat[:4*reg_max], feat[4*reg_max:]
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

# ─── LOW-LATENCY FFmpeg ENCODER ────────────────────────────────────────────
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

# ─── MAIN PIPELINE ─────────────────────────────────────────────────────────
def run_inference():
    picam2 = Picamera2()
    config = picam2.create_video_configuration(main={"format": "BGR888", "size": (640, 480)})
    picam2.configure(config)
    picam2.start()
    ffmpeg_proc = start_ffmpeg(640, 480, fps=15)
    
    with hp.VDevice() as target:
        hef = hp.HEF(HEF_PATH)
        network_group = target.configure(hef, hp.ConfigureParams.create_from_hef(hef, hp.HailoStreamInterface.PCIe))[0]
        input_w = network_group.get_input_vstream_infos()[0].shape[1]
        output_v_infos = network_group.get_output_vstream_infos()
        in_params = hp.InputVStreamParams.make_from_network_group(network_group, hp.FormatType.UINT8)
        out_params = hp.OutputVStreamParams.make_from_network_group(network_group, hp.FormatType.UINT8)
        
        with network_group.activate(), hp.InferVStreams(network_group, in_params, out_params) as vstreams:
            print(f"--- Low-Latency HLS Active ---")
            print(f"URL: http://localhost:8000/stream.m3u8")
            
            while True:
                start_time = time.time()
                
                # 1. Capture
                frame_rgb = picam2.capture_array()
                
                # 2. Pre-process
                input_frame, ratio, pad_left, pad_top = letterbox(frame_rgb, input_w)
                input_data = np.expand_dims(input_frame, axis=0).astype(np.uint8)
                
                # 3. Inference
                raw_outputs = vstreams.infer(input_data)
                
                # 4. Post-process
                final_feats = []
                sorted_names = sorted(raw_outputs.keys(), key=lambda n: raw_outputs[n].shape[1], reverse=True)
                for name in sorted_names:
                    v_info = [v for v in output_v_infos if v.name == name][0]
                    zp, scale = v_info.quant_info.qp_zp, v_info.quant_info.qp_scale
                    dequantized = (raw_outputs[name].astype(np.float32) - zp) * scale
                    final_feats.append(np.squeeze(dequantized).transpose(2, 0, 1))
                
                boxes, scores, classes = decode(final_feats, conf_thresh=CONF_THRESH)
                
                # 5. Drawing and Detection Recording
                vis_frame = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
                inference_time_ms = (time.time() - start_time) * 1000
                
                if len(boxes) > 0:
                    keep = nms(boxes, scores, IOU_THRESH)
                    for b, s, c in zip(boxes[keep], scores[keep], classes[keep]):
                        x1, y1, x2, y2 = map(int, (b - [pad_left, pad_top, pad_left, pad_top]) / ratio)
                        class_name = CLASS_NAMES[c]
                        color = (0, 0, 255) if 'smoke' in class_name else (0, 255, 0)
                        cv2.rectangle(vis_frame, (x1, y1), (x2, y2), color, 2)
                        label = f"{class_name} {s:.2f}"
                        cv2.putText(vis_frame, label, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                        
                        # Send smoke detection to backend
                        if class_name in SMOKE_CLASSES:
                            timestamp = datetime.now(timezone.utc).isoformat()
                            bounding_box = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
                            send_smoke_detection(timestamp, float(s), class_name, bounding_box, int(inference_time_ms))
                
                # 6. Push to Stream
                try:
                    ffmpeg_proc.stdin.write(vis_frame.tobytes())
                except BrokenPipeError:
                    break
                
                # Performance Monitor
                elapsed = time.time() - start_time
                print(f"Inference FPS: {1.0/elapsed:.2f} ", end='\r')

if __name__ == '__main__':
    # Start HLS File Server
    threading.Thread(target=lambda: ThreadedHTTPServer(('', 8000), HLSHandler).serve_forever(), daemon=True).start()
    try:
        run_inference()
    except KeyboardInterrupt:
        print("\nStopping...")
