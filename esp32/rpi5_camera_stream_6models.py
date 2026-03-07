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
from pathlib import Path

# ─── CONFIGURATION ─────────────────────────────────────────────────────────
# 6 Separate HEF Models
MODELS = {
    'vehicle_detection': {
        'path': r'/home/sevi/smoki_project/models/vehicle_detection.hef',
        'classes': ['passenger', 'puv', 'service', 'two_wheel', 'exhaust_pipe']
    },
    'smoke_detection': {
        'path': r'/home/sevi/smoki_project/models/smoke_detection.hef',
        'classes': ['smoke_black', 'smoke_white']
    },
    'license_plate_detection': {
        'path': r'/home/sevi/smoki_project/models/license_plate_detection.hef',
        'classes': ['license_plate']
    },
    'license_plate_recognition': {
        'path': r'/home/sevi/smoki_project/models/license_plate_recognition.hef',
        'classes': ['text']
    },
    'face_detection': {
        'path': r'/home/sevi/smoki_project/models/face_detection.hef',
        'classes': ['face']
    },
    'face_blur': {
        'path': r'/home/sevi/smoki_project/models/face_blur.hef',
        'classes': ['blurred_face']
    }
}

HLS_DIR     = '/dev/shm/hls'
SCREENSHOTS_DIR = '/home/sevi/smoki_project/detections'
CONF_THRESH = 0.25
IOU_THRESH  = 0.45
SMOKE_CLASSES = {'smoke_black', 'smoke_white'}

# Backend API configuration
BACKEND_URL = os.getenv('BACKEND_URL', 'http://localhost:8000')
CAMERA_ID = os.getenv('CAMERA_ID', 'rpi_camera_01')
CAMERA_LOCATION = os.getenv('CAMERA_LOCATION', 'unknown')

# Clean up and prepare directories
if os.path.exists(HLS_DIR): shutil.rmtree(HLS_DIR)
os.makedirs(HLS_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

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

def blur_faces(frame, faces):
    """Blur detected faces for privacy"""
    for x1, y1, x2, y2 in faces:
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
        face_roi = frame[y1:y2, x1:x2]
        blurred = cv2.GaussianBlur(face_roi, (51, 51), 0)
        frame[y1:y2, x1:x2] = blurred
    return frame

def save_detection_screenshots(frame, detections, timestamp_str):
    """Save full frame and cropped detections"""
    detection_id = timestamp_str.replace(':', '-').replace('.', '-')
    detection_dir = os.path.join(SCREENSHOTS_DIR, detection_id)
    os.makedirs(detection_dir, exist_ok=True)
    
    full_frame_path = os.path.join(detection_dir, 'full_frame.jpg')
    cv2.imwrite(full_frame_path, frame)
    
    screenshots_info = {
        'full_frame': full_frame_path,
        'crops': []
    }
    
    for idx, det in enumerate(detections):
        x1, y1, x2, y2, class_name, confidence = det
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
        
        crop = frame[y1:y2, x1:x2]
        crop_path = os.path.join(detection_dir, f'{idx:02d}_{class_name}_{confidence:.2f}.jpg')
        cv2.imwrite(crop_path, crop)
        
        screenshots_info['crops'].append({
            'path': crop_path,
            'class': class_name,
            'confidence': confidence,
            'bbox': {'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2}
        })
    
    return detection_dir, screenshots_info

def send_smoke_detection(timestamp, confidence, smoke_type, bounding_box, inference_time_ms, 
                        screenshots_info=None, plate_text=None, all_detections=None):
    """Send smoke detection metadata to backend with all model detections"""
    try:
        # Build detections list from all models
        detections_list = []
        if all_detections:
            for model_name, dets in all_detections.items():
                for det in dets:
                    x1, y1, x2, y2, class_name, conf = det
                    detections_list.append({
                        "model_name": model_name,
                        "class_name": class_name,
                        "confidence": float(conf),
                        "bounding_box": {"x1": int(x1), "y1": int(y1), "x2": int(x2), "y2": int(y2)}
                    })
        
        payload = {
            "timestamp": timestamp,
            "confidence": float(confidence),
            "smoke_type": smoke_type,
            "bounding_box": bounding_box,
            "camera_id": CAMERA_ID,
            "location": CAMERA_LOCATION,
            "metadata": {
                "inference_time_ms": inference_time_ms,
                "models": list(MODELS.keys()),
                "confidence_threshold": CONF_THRESH
            },
            "detections": detections_list
        }
        
        if screenshots_info:
            payload["screenshots"] = screenshots_info
        
        if plate_text:
            payload["license_plate"] = plate_text
        
        response = requests.post(
            f"{BACKEND_URL}/api/detections/smoke",
            json=payload,
            timeout=5
        )
        if response.status_code == 200:
            print(f"✓ Smoke detection recorded: {smoke_type} ({confidence:.2f}) with {len(detections_list)} detections")
        else:
            print(f"✗ Failed to record detection: {response.status_code}")
    except Exception as e:
        print(f"✗ Error sending detection: {e}")

def start_ffmpeg(w, h, fps=15):
    cmd = ['ffmpeg', '-y',
        '-f', 'rawvideo', '-vcodec', 'rawvideo',
        '-pix_fmt', 'bgr24', '-s', f'{w}x{h}', '-r', str(fps),
        '-i', '-', '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
        '-b:v', '800k',
        '-g', str(fps * 2),
        '-hls_time', '2',
        '-hls_list_size', '4',
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
    
    # Load all 6 models
    vstreams_dict = {}
    network_groups = {}
    
    with hp.VDevice() as target:
        print("Loading 6 models...")
        for model_name, model_config in MODELS.items():
            try:
                hef = hp.HEF(model_config['path'])
                network_group = target.configure(hef, hp.ConfigureParams.create_from_hef(hef, hp.HailoStreamInterface.PCIe))[0]
                in_params = hp.InputVStreamParams.make_from_network_group(network_group, hp.FormatType.UINT8)
                out_params = hp.OutputVStreamParams.make_from_network_group(network_group, hp.FormatType.UINT8)
                
                network_groups[model_name] = network_group
                vstreams_dict[model_name] = (network_group, in_params, out_params)
                print(f"✓ Loaded {model_name}")
            except Exception as e:
                print(f"✗ Failed to load {model_name}: {e}")
        
        print(f"\n--- 6-Model Multi-Task Inference Active ---")
        print(f"Models: {', '.join(MODELS.keys())}")
        print(f"URL: http://localhost:8000/stream.m3u8")
        print(f"Screenshots: {SCREENSHOTS_DIR}\n")
        
        # Activate all networks
        for model_name, network_group in network_groups.items():
            network_group.activate()
        
        try:
            while True:
                start_time = time.time()
                frame_rgb = picam2.capture_array()
                vis_frame = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
                
                timestamp = datetime.now(timezone.utc).isoformat()
                timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:-3]
                
                all_detections = []
                vehicle_detections = []
                smoke_detections = []
                faces = []
                plate_text = None
                smoke_detected = False
                
                # 1. Vehicle Detection
                if 'vehicle_detection' in vstreams_dict:
                    network_group, in_params, out_params = vstreams_dict['vehicle_detection']
                    input_frame, ratio, pad_left, pad_top = letterbox(frame_rgb, 640)
                    input_data = np.expand_dims(input_frame, axis=0).astype(np.uint8)
                    
                    with hp.InferVStreams(network_group, in_params, out_params) as vstreams:
                        raw_outputs = vstreams.infer(input_data)
                        final_feats = []
                        output_v_infos = network_group.get_output_vstream_infos()
                        sorted_names = sorted(raw_outputs.keys(), key=lambda n: raw_outputs[n].shape[1], reverse=True)
                        
                        for name in sorted_names:
                            v_info = [v for v in output_v_infos if v.name == name][0]
                            zp, scale = v_info.quant_info.qp_zp, v_info.quant_info.qp_scale
                            dequantized = (raw_outputs[name].astype(np.float32) - zp) * scale
                            final_feats.append(np.squeeze(dequantized).transpose(2, 0, 1))
                        
                        boxes, scores, classes = decode(final_feats, conf_thresh=CONF_THRESH)
                        
                        if len(boxes) > 0:
                            keep = nms(boxes, scores, IOU_THRESH)
                            for b, s, c in zip(boxes[keep], scores[keep], classes[keep]):
                                x1, y1, x2, y2 = map(int, (b - [pad_left, pad_top, pad_left, pad_top]) / ratio)
                                class_name = MODELS['vehicle_detection']['classes'][c]
                                color = (0, 255, 0)
                                cv2.rectangle(vis_frame, (x1, y1), (x2, y2), color, 2)
                                label = f"{class_name} {s:.2f}"
                                cv2.putText(vis_frame, label, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                                
                                vehicle_detections.append((x1, y1, x2, y2, class_name, float(s)))
                                all_detections.append((x1, y1, x2, y2, class_name, float(s)))
                
                # 2. Smoke Detection (separate model)
                if 'smoke_detection' in vstreams_dict:
                    network_group, in_params, out_params = vstreams_dict['smoke_detection']
                    input_frame, ratio, pad_left, pad_top = letterbox(frame_rgb, 640)
                    input_data = np.expand_dims(input_frame, axis=0).astype(np.uint8)
                    
                    with hp.InferVStreams(network_group, in_params, out_params) as vstreams:
                        raw_outputs = vstreams.infer(input_data)
                        final_feats = []
                        output_v_infos = network_group.get_output_vstream_infos()
                        sorted_names = sorted(raw_outputs.keys(), key=lambda n: raw_outputs[n].shape[1], reverse=True)
                        
                        for name in sorted_names:
                            v_info = [v for v in output_v_infos if v.name == name][0]
                            zp, scale = v_info.quant_info.qp_zp, v_info.quant_info.qp_scale
                            dequantized = (raw_outputs[name].astype(np.float32) - zp) * scale
                            final_feats.append(np.squeeze(dequantized).transpose(2, 0, 1))
                        
                        boxes, scores, classes = decode(final_feats, conf_thresh=CONF_THRESH)
                        
                        if len(boxes) > 0:
                            keep = nms(boxes, scores, IOU_THRESH)
                            for b, s, c in zip(boxes[keep], scores[keep], classes[keep]):
                                x1, y1, x2, y2 = map(int, (b - [pad_left, pad_top, pad_left, pad_top]) / ratio)
                                class_name = MODELS['smoke_detection']['classes'][c]
                                color = (0, 0, 255)  # Red for smoke
                                cv2.rectangle(vis_frame, (x1, y1), (x2, y2), color, 2)
                                label = f"{class_name} {s:.2f}"
                                cv2.putText(vis_frame, label, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                                
                                smoke_detections.append((x1, y1, x2, y2, class_name, float(s)))
                                all_detections.append((x1, y1, x2, y2, class_name, float(s)))
                                smoke_detected = True
                
                # 3. License Plate Detection (on vehicle ROI)
                if 'license_plate_detection' in vstreams_dict and len(vehicle_detections) > 0:
                    for det in vehicle_detections:
                        x1, y1, x2, y2, class_name, conf = det
                        if 'passenger' in class_name or 'puv' in class_name or 'service' in class_name:
                            roi = frame_rgb[y1:y2, x1:x2]
                            if roi.size > 0:
                                network_group, in_params, out_params = vstreams_dict['license_plate_detection']
                                input_frame, ratio, pad_left, pad_top = letterbox(roi, 640)
                                input_data = np.expand_dims(input_frame, axis=0).astype(np.uint8)
                                
                                with hp.InferVStreams(network_group, in_params, out_params) as vstreams:
                                    raw_outputs = vstreams.infer(input_data)
                                    # Process license plate detections
                
                # 4. License Plate Recognition (OCR on detected plates)
                if 'license_plate_recognition' in vstreams_dict:
                    # Run OCR on detected license plates
                    pass
                
                # 5. Face Detection
                if 'face_detection' in vstreams_dict:
                    network_group, in_params, out_params = vstreams_dict['face_detection']
                    input_frame, ratio, pad_left, pad_top = letterbox(frame_rgb, 640)
                    input_data = np.expand_dims(input_frame, axis=0).astype(np.uint8)
                    
                    with hp.InferVStreams(network_group, in_params, out_params) as vstreams:
                        raw_outputs = vstreams.infer(input_data)
                        final_feats = []
                        output_v_infos = network_group.get_output_vstream_infos()
                        sorted_names = sorted(raw_outputs.keys(), key=lambda n: raw_outputs[n].shape[1], reverse=True)
                        
                        for name in sorted_names:
                            v_info = [v for v in output_v_infos if v.name == name][0]
                            zp, scale = v_info.quant_info.qp_zp, v_info.quant_info.qp_scale
                            dequantized = (raw_outputs[name].astype(np.float32) - zp) * scale
                            final_feats.append(np.squeeze(dequantized).transpose(2, 0, 1))
                        
                        boxes, scores, classes = decode(final_feats, conf_thresh=CONF_THRESH)
                        
                        if len(boxes) > 0:
                            keep = nms(boxes, scores, IOU_THRESH)
                            for b, s, c in zip(boxes[keep], scores[keep], classes[keep]):
                                x1, y1, x2, y2 = map(int, (b - [pad_left, pad_top, pad_left, pad_top]) / ratio)
                                faces.append((x1, y1, x2, y2))
                
                # 6. Face Blur (privacy protection)
                if 'face_blur' in vstreams_dict and len(faces) > 0:
                    vis_frame = blur_faces(vis_frame, faces)
                
                # Save screenshots when smoke detected
                if smoke_detected and len(all_detections) > 0:
                    detection_dir, screenshots_info = save_detection_screenshots(vis_frame, all_detections, timestamp_str)
                    
                    # Organize detections by model
                    detections_by_model = {
                        'vehicle_detection': vehicle_detections,
                        'smoke_detection': smoke_detections,
                        'face_detection': [(x1, y1, x2, y2, 'face', 1.0) for x1, y1, x2, y2 in faces]
                    }
                    
                    for det in smoke_detections:
                        x1, y1, x2, y2, class_name, conf = det
                        bounding_box = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
                        send_smoke_detection(timestamp, conf, class_name, bounding_box, 
                                           int((time.time() - start_time) * 1000), 
                                           screenshots_info, plate_text, detections_by_model)
                    print(f"📸 Screenshots saved to: {detection_dir}")
                
                # Push to Stream
                try:
                    ffmpeg_proc.stdin.write(vis_frame.tobytes())
                except BrokenPipeError:
                    break
                
                elapsed = time.time() - start_time
                print(f"FPS: {1.0/elapsed:.2f} | Vehicles: {len(vehicle_detections)} | Smoke: {'YES' if smoke_detected else 'NO'} | Faces: {len(faces)}", end='\r')
        
        finally:
            for network_group in network_groups.values():
                network_group.deactivate()

if __name__ == '__main__':
    threading.Thread(target=lambda: ThreadedHTTPServer(('', 8000), HLSHandler).serve_forever(), daemon=True).start()
    try:
        run_inference()
    except KeyboardInterrupt:
        print("\nStopping...")
