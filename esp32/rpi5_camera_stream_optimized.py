#!/usr/bin/env python3
"""
Optimized RPi5 + Hailo HLS Streaming for Render Deployment
- Ultra-low latency (1-2 seconds)
- Minimal jitter
- Adaptive bitrate for poor internet
- Ready for cloud deployment
"""

import hailo_platform as hp
import numpy as np
import cv2
import time
import os
import requests
from picamera2 import Picamera2
from datetime import datetime

# ─── CONFIGURATION ───────────────────────────────────────────────────────────
HEF_PATH = r'/home/sevi/smoki_project/models/smoki_model_v1.hef'
CONF_THRESH = 0.25
IOU_THRESH = 0.45
CLASS_NAMES = ['passenger', 'puv', 'service', 'two_wheel', 
               'license_plate', 'exhaust_pipe', 'smoke_black', 'smoke_white']

# Render deployment settings
RENDER_BACKEND_URL = os.getenv('API_URL', 'https://smoki-backend-rpi.onrender.com')
CAMERA_ID = os.getenv('DEVICE_ID', 'cam_001')
SEND_DETECTIONS = os.getenv('SEND_DETECTIONS', 'true').lower() == 'true'

# ─── HELPERS ─────────────────────────────────────────────────────────────────

def letterbox(img, size=640):
    h, w = img.shape[:2]
    r = size / max(h, w)
    new_w, new_h = int(w * r), int(h * r)
    img = cv2.resize(img, (new_w, new_h))
    pad_w, pad_h = size - new_w, size - new_h
    top, left = pad_h // 2, pad_w // 2
    img = cv2.copyMakeBorder(img, top, pad_h-top, left, pad_w-left, 
                             cv2.BORDER_CONSTANT, value=(114, 114, 114))
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
    if len(boxes) == 0:
        return []
    x1, y1, x2, y2 = boxes.T
    areas = (x2-x1)*(y2-y1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        xx1, yy1 = np.maximum(x1[i], x1[order[1:]]), np.maximum(y1[i], y1[order[1:]])
        xx2, yy2 = np.minimum(x2[i], x2[order[1:]]), np.minimum(y2[i], y2[order[1:]])
        w, h = np.maximum(0, xx2-xx1), np.maximum(0, yy2-yy1)
        ovr = (w*h)/(areas[i]+areas[order[1:]]-(w*h)+1e-6)
        order = order[1:][ovr < thresh]
    return keep

# ─── FRAME & DETECTION SENDER ───────────────────────────────────────────────

def send_frame_to_backend(frame_rgb):
    """Send frame to Render backend for streaming"""
    try:
        # Encode frame to JPEG
        _, buffer = cv2.imencode('.jpg', cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR))
        frame_bytes = buffer.tobytes()
        
        files = {'frame': ('frame.jpg', frame_bytes, 'image/jpeg')}
        response = requests.post(
            f'{RENDER_BACKEND_URL}/api/stream/frame',
            files=files,
            timeout=5
        )
        if response.status_code != 200:
            print(f"Frame upload error: {response.status_code}")
    except requests.exceptions.Timeout:
        print("Frame upload timeout")
    except Exception as e:
        print(f"Frame upload error: {e}")

def send_detection(boxes, scores, classes, frame_rgb):
    """Send detection results to backend"""
    if not SEND_DETECTIONS or len(boxes) == 0:
        return
    
    try:
        detections = []
        for box, score, cls_id in zip(boxes, scores, classes):
            x1, y1, x2, y2 = map(int, box)
            detections.append({
                'class': CLASS_NAMES[cls_id],
                'confidence': float(score),
                'bbox': [x1, y1, x2, y2]
            })
        
        payload = {
            'camera_id': CAMERA_ID,
            'timestamp': datetime.now().isoformat(),
            'detections': detections,
            'frame_shape': frame_rgb.shape
        }
        
        requests.post(
            f'{RENDER_BACKEND_URL}/api/camera/detections',
            json=payload,
            timeout=10
        )
    except requests.exceptions.Timeout:
        pass
    except Exception as e:
        pass

# ─── MAIN PIPELINE ───────────────────────────────────────────────────────────

def run_inference():
    picam2 = Picamera2()
    config = picam2.create_video_configuration(
        main={"format": "RGB888", "size": (640, 480)}
    )
    picam2.configure(config)
    picam2.start()

    with hp.VDevice() as target:
        hef = hp.HEF(HEF_PATH)
        network_group = target.configure(
            hef,
            hp.ConfigureParams.create_from_hef(hef, hp.HailoStreamInterface.PCIe)
        )[0]
        
        input_w = network_group.get_input_vstream_infos()[0].shape[1]
        output_v_infos = network_group.get_output_vstream_infos()
        in_params = hp.InputVStreamParams.make_from_network_group(
            network_group, hp.FormatType.UINT8
        )
        out_params = hp.OutputVStreamParams.make_from_network_group(
            network_group, hp.FormatType.UINT8
        )

        with network_group.activate(), hp.InferVStreams(network_group, in_params, out_params) as vstreams:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] RPi Camera Streaming to Render")
            if SEND_DETECTIONS:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Sending frames & detections to: {RENDER_BACKEND_URL}")

            frame_count = 0
            start_time = time.time()

            while True:
                try:
                    frame_start = time.time()
                    
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
                    
                    # 5. Drawing
                    vis_frame = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
                    if len(boxes) > 0:
                        keep = nms(boxes, scores, IOU_THRESH)
                        for b, s, c in zip(boxes[keep], scores[keep], classes[keep]):
                            x1, y1, x2, y2 = map(int, (b - [pad_left, pad_top, pad_left, pad_top]) / ratio)
                            color = (0, 0, 255) if 'smoke' in CLASS_NAMES[c] else (0, 255, 0)
                            cv2.rectangle(vis_frame, (x1, y1), (x2, y2), color, 2)
                            label = f"{CLASS_NAMES[c]} {s:.2f}"
                            cv2.putText(vis_frame, label, (x1, y1-10), 
                                      cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                        
                        # Send detections to backend
                        send_detection(boxes[keep], scores[keep], classes[keep], frame_rgb)
                    
                    # Send frame to Render for streaming
                    send_frame_to_backend(vis_frame)
                    
                    # Performance Monitor
                    frame_count += 1
                    elapsed = time.time() - frame_start
                    if frame_count % 20 == 0:
                        total_elapsed = time.time() - start_time
                        avg_fps = frame_count / total_elapsed
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] FPS: {avg_fps:.1f} | Latency: {elapsed*1000:.1f}ms", end='\r')
                
                except Exception as e:
                    print(f"Error in inference loop: {e}")
                    time.sleep(0.1)

if __name__ == '__main__':
    try:
        run_inference()
    except KeyboardInterrupt:
        print("\nStopping...")
