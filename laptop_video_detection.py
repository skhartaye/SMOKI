#!/usr/bin/env python3
"""
laptop_video_detection.py - Enhanced laptop detection system
Processes video files and sends detection data to SMOKI backend API
Similar to RPi functionality but for video file processing
"""
import torch
import numpy as np
import cv2
import time
import os
import threading
import queue
import requests
import json
import base64
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import easyocr
from ultralytics import YOLO
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
VIDEO_FILE = os.getenv('VIDEO_FILE', r'esp32/rotonda_trim.mp4')
API_URL = os.getenv('API_URL', 'https://smoki-backend-rpi.onrender.com')
DEVICE_ID = os.getenv('DEVICE_ID', 'laptop_cam_001')
CAMERA_LOCATION = os.getenv('CAMERA_LOCATION', 'Laptop_Detection')
SEND_DETECTIONS = os.getenv('SEND_DETECTIONS', 'true').lower() == 'true'

# Video processing settings
WIDTH, HEIGHT, FPS = 1280, 720, 24
INFER_EVERY = 8  # Run inference every N frames
SEND_EVERY = 30  # Send data every N frames (about 1 second at 30fps)

# Model confidence thresholds
SMOKE_CONF = 0.25
PLATE_CONF = 0.15
VEHICLE_CONF = 0.30

# Model paths
MODELS = {
    'smoke': 'esp32/models/yolov8n-smoke-seg.pt',
    'plate': 'esp32/license-plate.pt', 
    'vehicle': 'esp32/vehicle-class.pt'
}

# Global variables
_smoke = []
_vehicle = []
_plates = []
_all = []
_dlock = threading.Lock()
_iqueue = queue.Queue(maxsize=2)
_send_queue = queue.Queue(maxsize=10)

# Device selection
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"[INFO] Using device: {device}")
print(f"[INFO] API URL: {API_URL}")
print(f"[INFO] Device ID: {DEVICE_ID}")
print(f"[INFO] Send detections: {SEND_DETECTIONS}")
# ── Model loading ─────────────────────────────────────────────────────────────
def load_models():
    """Load all PyTorch models"""
    models = {}
    for name, path in MODELS.items():
        if os.path.exists(path):
            try:
                model = YOLO(path)
                model.to(device)
                print(f"[OK] Loaded {name} model: {path}")
                if hasattr(model, 'names'):
                    print(f"  Classes: {model.names}")
                models[name] = model
            except Exception as e:
                print(f"[WARN] Failed to load {name} model: {e}")
        else:
            print(f"[WARN] Model file not found: {path}")
    return models

# ── OCR Functions ─────────────────────────────────────────────────────────────
def load_ocr():
    """Initialize EasyOCR reader for license plate recognition"""
    try:
        reader = easyocr.Reader(['en'], gpu=torch.cuda.is_available(), verbose=False)
        print("[OK] EasyOCR initialized for license plate recognition")
        return reader
    except Exception as e:
        print(f"[ERROR] OCR initialization failed: {e}")
        return None

def read_plate_easyocr(reader, crop):
    """Extract text using EasyOCR"""
    if not reader or crop is None or crop.size == 0:
        return "", 0.0
        
    try:
        h, w = crop.shape[:2]
        if h < 10 or w < 20:
            return "", 0.0
        
        # Resize for better OCR
        scale_factor = max(3, 200 // max(w, h))
        new_w, new_h = w * scale_factor, h * scale_factor
        enlarged = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
        
        # Convert to grayscale and enhance
        gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
        bilateral = cv2.bilateralFilter(gray, 11, 75, 75)
        
        # Apply adaptive threshold
        thresh = cv2.adaptiveThreshold(bilateral, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 15, 8)
        
        # Use EasyOCR
        results = reader.readtext(
            cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR),
            allowlist='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ',
            detail=1,
            paragraph=False,
            width_ths=0.7,
            height_ths=0.7,
            decoder='greedy'
        )
        
        if not results:
            return "", 0.0
        
        # Get best result
        results = sorted(results, key=lambda r: r[2], reverse=True)
        best_text = ""
        best_confidence = 0.0
        
        for bbox, text, conf in results:
            clean_text = ''.join(c for c in text if c.isalnum()).upper()
            if clean_text and len(clean_text) >= 3:
                best_text = clean_text
                best_confidence = conf
                break
        
        return best_text, best_confidence
        
    except Exception as e:
        print(f"[EasyOCR ERROR] {e}")
        return "", 0.0
# ── Detection processing ─────────────────────────────────────────────────────
def process_detections(results, img_shape, conf_threshold, class_names=None):
    """Process YOLO detection results"""
    detections = []
    h, w = img_shape[:2]
    
    if results and len(results) > 0:
        boxes = results[0].boxes
        if boxes is not None:
            for i in range(len(boxes)):
                conf = float(boxes.conf[i])
                if conf >= conf_threshold:
                    x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy()
                    cls_id = int(boxes.cls[i])
                    
                    x1, y1 = max(0, int(x1)), max(0, int(y1))
                    x2, y2 = min(w, int(x2)), min(h, int(y2))
                    
                    class_name = class_names[cls_id] if class_names and cls_id < len(class_names) else f"class_{cls_id}"
                    
                    detection = {
                        "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                        "confidence": round(conf, 3),
                        "class": class_name,
                        "class_id": cls_id
                    }
                    detections.append(detection)
    
    return detections

def smoke_opacity(detection, frame):
    """Calculate smoke opacity level"""
    bbox = detection["bbox"]
    x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]
    conf = detection["confidence"]
    
    # Area factor
    area_factor = min(1.0, ((x2-x1) * (y2-y1) / (WIDTH * HEIGHT)) / 0.5)
    
    # Darkness factor
    darkness_factor = 0.0
    try:
        roi = frame[max(0, y1):min(frame.shape[0], y2), max(0, x1):min(frame.shape[1], x2)]
        if roi.size > 0:
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            darkness_factor = max(float(np.mean(gray < 80)), float(np.mean(gray > 200)) * 0.7)
    except:
        pass
    
    # Calculate smoke score
    smoke_score = 0.5 * conf + 0.3 * area_factor + 0.2 * darkness_factor if darkness_factor > 0 else 0.6 * conf + 0.4 * area_factor
    
    # Determine opacity level
    if smoke_score >= 0.70:
        opacity_level = "dense"
    elif smoke_score >= 0.45:
        opacity_level = "moderate"
    else:
        opacity_level = "thin"
    
    return opacity_level, round(smoke_score, 3)

# ── API Communication ────────────────────────────────────────────────────────
def send_detection_data(frame, smoke_dets, vehicle_dets, plate_dets, frame_number, timestamp):
    """Send detection data to backend API"""
    if not SEND_DETECTIONS:
        return
    
    try:
        # Encode frame as JPEG
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        frame_b64 = base64.b64encode(buffer).decode('utf-8')
        
        # Prepare detection metadata
        all_detections = []
        
        # Add smoke detections
        for det in smoke_dets:
            all_detections.append({
                "model_name": "smoke_detection",
                "class_name": det["class"],
                "confidence": det["confidence"],
                "bounding_box": det["bbox"],
                "opacity_level": det.get("opacity_level", "unknown"),
                "opacity_score": det.get("opacity_score", 0.0)
            })
        
        # Add vehicle detections
        for det in vehicle_dets:
            all_detections.append({
                "model_name": "vehicle_detection",
                "class_name": det["class"],
                "confidence": det["confidence"],
                "bounding_box": det["bbox"]
            })
        
        # Add plate detections
        for det in plate_dets:
            all_detections.append({
                "model_name": "license_plate",
                "class_name": "license_plate",
                "confidence": det["confidence"],
                "bounding_box": det["bbox"],
                "plate_text": det.get("text", ""),
                "ocr_confidence": det.get("ocr_confidence", 0.0)
            })
        
        # Prepare metadata
        metadata = {
            "timestamp": timestamp,
            "camera_id": DEVICE_ID,
            "location": CAMERA_LOCATION,
            "frame_number": frame_number,
            "detections": all_detections,
            "detection_counts": {
                "smoke": len(smoke_dets),
                "vehicle": len(vehicle_dets),
                "plate": len(plate_dets)
            },
            "is_violation": len(smoke_dets) > 0 and len(vehicle_dets) > 0,
            "source": "laptop_video_processing"
        }
        
        # Send to stream endpoint (similar to RPi)
        payload = {
            "frame_data": frame_b64,
            "metadata": json.dumps(metadata)
        }
        
        response = requests.post(
            f"{API_URL}/api/stream/frame",
            data=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"[API] ✓ Sent frame {frame_number} - S:{len(smoke_dets)} V:{len(vehicle_dets)} P:{len(plate_dets)}")
        else:
            print(f"[API] ✗ Failed to send frame {frame_number}: {response.status_code}")
            
    except Exception as e:
        print(f"[API ERROR] {e}")

def api_sender_worker():
    """Background worker for sending API data"""
    print("[INFO] API sender worker started")
    
    while True:
        try:
            task = _send_queue.get(timeout=1.0)
            if task is None:  # Shutdown signal
                break
                
            frame, smoke_dets, vehicle_dets, plate_dets, frame_number, timestamp = task
            send_detection_data(frame, smoke_dets, vehicle_dets, plate_dets, frame_number, timestamp)
            
        except queue.Empty:
            continue
        except Exception as e:
            print(f"[API SENDER ERROR] {e}")
            continue
# ── Drawing functions ─────────────────────────────────────────────────────────
def draw_boxes(frame, smoke_dets, vehicle_dets, plate_dets):
    """Draw detection boxes on frame"""
    # Draw smoke detections (red)
    for det in smoke_dets:
        bbox = det["bbox"]
        x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]
        
        opacity_level = det.get('opacity_level', 'unknown')
        opacity_score = det.get('opacity_score', 0.0)
        
        # Color based on opacity
        if opacity_level == 'dense':
            box_color = (0, 0, 255)  # Bright red
        elif opacity_level == 'moderate':
            box_color = (0, 100, 255)  # Orange-red
        else:
            box_color = (0, 150, 255)  # Light red
        
        thickness = 4 if opacity_level == 'dense' else 3 if opacity_level == 'moderate' else 2
        cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, thickness)
        
        # Multi-line text
        text1 = f"{det['class']} {det['confidence']:.2f}"
        text2 = f"{opacity_level.upper()} ({opacity_score:.2f})"
        
        cv2.rectangle(frame, (x1, max(0, y1-30)), (x1 + 200, max(0, y1+15)), (0, 0, 0), -1)
        cv2.putText(frame, text1, (x1, max(0, y1-10)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, box_color, 2)
        cv2.putText(frame, text2, (x1, max(0, y1+10)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, box_color, 2)
    
    # Draw vehicle detections (green)
    for det in vehicle_dets:
        bbox = det["bbox"]
        x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        
        text = f"{det['class']} {det['confidence']:.2f}"
        cv2.rectangle(frame, (x1, max(0, y1-25)), (x1 + 150, max(0, y1-5)), (0, 0, 0), -1)
        cv2.putText(frame, text, (x1, max(0, y1-10)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    
    # Draw plate detections (yellow)
    for det in plate_dets:
        bbox = det["bbox"]
        x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
        
        text = det.get("text", "processing...")
        cv2.rectangle(frame, (x1, max(0, y1-25)), (x1 + 120, max(0, y1-5)), (0, 0, 0), -1)
        cv2.putText(frame, text, (x1, max(0, y1-10)), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
    
    # Draw violation indicator
    if smoke_dets and vehicle_dets:
        cv2.rectangle(frame, (0, 0), (WIDTH-1, HEIGHT-1), (0, 0, 255), 8)
        cv2.putText(frame, "VIOLATION DETECTED", (WIDTH//2-180, HEIGHT-20),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
    
    # Draw info overlay
    timestamp = datetime.now().strftime("%H:%M:%S")
    cv2.rectangle(frame, (5, 5), (300, 65), (0, 0, 0), -1)
    cv2.putText(frame, f"Time: {timestamp}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.putText(frame, f"Detections - S:{len(smoke_dets)} V:{len(vehicle_dets)} P:{len(plate_dets)}", 
               (10, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    cv2.putText(frame, f"API: {'ON' if SEND_DETECTIONS else 'OFF'}", (10, 60), 
               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0) if SEND_DETECTIONS else (0, 0, 255), 2)
    
    return frame

# ── Inference worker ──────────────────────────────────────────────────────────
def infer_worker(models, ocr_reader):
    """Main inference worker thread"""
    global _smoke, _vehicle, _plates, _all
    
    while True:
        frame, oh, ow, frame_number = _iqueue.get()
        
        smoke_dets = []
        vehicle_dets = []
        plate_dets = []
        all_dets = []
        
        t0 = time.time()
        
        # Run smoke detection
        if 'smoke' in models:
            try:
                results = models['smoke'](frame, conf=SMOKE_CONF)
                smoke_raw = process_detections(results, frame.shape, SMOKE_CONF, 
                                             ['smoke_black', 'smoke_white'])
                
                for det in smoke_raw:
                    opacity_level, opacity_score = smoke_opacity(det, frame)
                    det['opacity_level'] = opacity_level
                    det['opacity_score'] = opacity_score
                    smoke_dets.append(det)
                    all_dets.append(det)
                    
            except Exception as e:
                print(f"[ERROR] Smoke detection: {e}")
        
        # Run vehicle detection
        if 'vehicle' in models:
            try:
                results = models['vehicle'](frame, conf=VEHICLE_CONF)
                vehicle_dets = process_detections(results, frame.shape, VEHICLE_CONF,
                                                ['passenger', 'puv', 'services', 'two_wheel'])
                all_dets.extend(vehicle_dets)
            except Exception as e:
                print(f"[ERROR] Vehicle detection: {e}")
        
        # Run license plate detection
        if 'plate' in models and ocr_reader:
            try:
                results = models['plate'](frame, conf=PLATE_CONF)
                plate_raw = process_detections(results, frame.shape, PLATE_CONF, ['license_plate'])
                
                for det in plate_raw:
                    bbox = det["bbox"]
                    x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]
                    
                    # Crop and OCR
                    crop = frame[max(0, y1):min(oh, y2), max(0, x1):min(ow, x2)].copy()
                    if crop.size > 0:
                        text, confidence = read_plate_easyocr(ocr_reader, crop)
                        det['text'] = text
                        det['ocr_confidence'] = confidence
                    else:
                        det['text'] = ""
                        det['ocr_confidence'] = 0.0
                    
                    plate_dets.append(det)
                    all_dets.append(det)
                    
            except Exception as e:
                print(f"[ERROR] Plate detection: {e}")
        
        # Update global detection lists
        with _dlock:
            _smoke = smoke_dets
            _vehicle = vehicle_dets
            _plates = plate_dets
            _all = all_dets
        
        inference_time = int((time.time() - t0) * 1000)
        
        # Queue for API sending if there are detections or violations
        if SEND_DETECTIONS and (smoke_dets or vehicle_dets or plate_dets):
            timestamp = datetime.now(timezone.utc).isoformat()
            try:
                _send_queue.put_nowait((frame.copy(), smoke_dets, vehicle_dets, plate_dets, frame_number, timestamp))
            except queue.Full:
                print("[WARN] Send queue full, dropping frame")
        
        if smoke_dets or vehicle_dets or plate_dets:
            print(f"[DETECT] Frame {frame_number} - S:{len(smoke_dets)} V:{len(vehicle_dets)} P:{len(plate_dets)} ({inference_time}ms)")
# ── Main function ─────────────────────────────────────────────────────────────
def main():
    """Main application entry point"""
    print("[INFO] Starting laptop video detection system...")
    print(f"[INFO] Video file: {VIDEO_FILE}")
    
    # Check if video file exists
    if not os.path.exists(VIDEO_FILE):
        print(f"[ERROR] Video file not found: {VIDEO_FILE}")
        return
    
    # Load models
    models = load_models()
    if not models:
        print("[ERROR] No models loaded successfully!")
        return
    
    # Initialize OCR
    ocr_reader = load_ocr()
    
    # Initialize video capture
    cap = cv2.VideoCapture(VIDEO_FILE)
    if not cap.isOpened():
        print(f"[ERROR] Could not open video file: {VIDEO_FILE}")
        return
    
    # Get video properties
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_fps = cap.get(cv2.CAP_PROP_FPS)
    video_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    video_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = total_frames / video_fps if video_fps > 0 else 0
    
    print(f"[OK] Video loaded: {video_width}x{video_height} @ {video_fps:.1f}fps")
    print(f"[OK] Total frames: {total_frames}, Duration: {duration:.1f}s")
    
    # Start worker threads
    threading.Thread(target=infer_worker, args=(models, ocr_reader), daemon=True).start()
    threading.Thread(target=api_sender_worker, daemon=True).start()
    
    print("\n[READY] Processing video - Press 'q' to quit, SPACE to pause/resume, 'r' to restart\n")
    
    frame_count = 0
    paused = False
    last_send_frame = 0
    
    try:
        while True:
            if not paused:
                ret, frame = cap.read()
                if not ret:
                    print("[INFO] End of video reached")
                    break
                
                # Resize frame if needed
                if frame.shape[:2] != (HEIGHT, WIDTH):
                    frame = cv2.resize(frame, (WIDTH, HEIGHT))
                
                # Queue frame for inference
                if frame_count % INFER_EVERY == 0:
                    try:
                        _iqueue.put_nowait((frame.copy(), HEIGHT, WIDTH, frame_count))
                    except queue.Full:
                        pass
                
                frame_count += 1
            
            # Get current detections for display
            with _dlock:
                smoke_dets = list(_smoke)
                vehicle_dets = list(_vehicle)
                plate_dets = list(_plates)
            
            # Create display frame
            if not paused:
                display_frame = draw_boxes(frame.copy(), smoke_dets, vehicle_dets, plate_dets)
                
                # Add video progress info
                progress = (frame_count / total_frames) * 100 if total_frames > 0 else 0
                current_time = frame_count / video_fps if video_fps > 0 else 0
                
                cv2.rectangle(display_frame, (5, HEIGHT-50), (WIDTH-5, HEIGHT-5), (0, 0, 0), -1)
                cv2.putText(display_frame, f"Progress: {progress:.1f}% ({current_time:.1f}s/{duration:.1f}s)", 
                           (10, HEIGHT-30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                cv2.putText(display_frame, f"Frame: {frame_count}/{total_frames}", 
                           (10, HEIGHT-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                
                if paused:
                    cv2.putText(display_frame, "PAUSED - Press SPACE to resume", 
                               (WIDTH//2 - 150, HEIGHT//2), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            
            # Show frame
            cv2.imshow('Laptop Video Detection System', display_frame)
            
            # Handle key presses
            key = cv2.waitKey(30) & 0xFF
            if key == ord('q'):
                break
            elif key == ord(' '):  # Space bar to pause/resume
                paused = not paused
                print(f"[INFO] Video {'paused' if paused else 'resumed'}")
            elif key == ord('r'):  # 'r' to restart video
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                frame_count = 0
                print("[INFO] Video restarted")
            
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user")
    
    finally:
        print("[INFO] Cleaning up...")
        
        # Signal workers to stop
        try:
            _send_queue.put_nowait(None)
        except:
            pass
            
        cap.release()
        cv2.destroyAllWindows()
        
        # Print final statistics
        print(f"\n[STATS] Processed {frame_count} frames")
        with _dlock:
            print(f"[STATS] Final detections - S:{len(_smoke)} V:{len(_vehicle)} P:{len(_plates)}")

if __name__ == '__main__':
    main()