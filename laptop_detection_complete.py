#!/usr/bin/env python3
"""
laptop_detection_complete.py - Complete laptop detection system for SMOKi
Replaces Raspberry Pi with laptop-based detection using:
- rotonda_trim.mp4 (video file)
- yolov8n-smoke-seg.pt (smoke detection)
- vehicle-class.pt (vehicle classification)  
- license-plate.pt (license plate detection)
- EasyOCR for license plate text recognition
- HTTP POST to backend API for data submission
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
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import easyocr
from ultralytics import YOLO

VIDEO_FILE = r'D:\embed\SMOKI\esp32\rotonda_trim.mp4'
BACKEND_URL = 'https://smoki-backend-rpi.onrender.com'
CAMERA_ID = 'laptop_camera_01'
LOCATION = 'Main Street Intersection'
SAVE_DIR = 'detection_frames'  # Directory to save detection frames

WIDTH, HEIGHT, FPS = 1280, 720, 24
INFER_EVERY = 8

SMOKE_CONF = 0.25
PLATE_CONF = 0.15
VEHICLE_CONF = 0.30

MODELS = {
    'smoke': r'D:\embed\SMOKI\esp32\yolov8n-smoke-seg.pt',
    'plate': r'D:\embed\SMOKI\esp32\license-plate.pt', 
    'vehicle': r'D:\embed\SMOKI\esp32\vehicle-class.pt'
}

_smoke = []
_vehicle = []
_plates = []
_all = []
_dlock = threading.Lock()
_iqueue = queue.Queue(maxsize=2)
_ocr_queue = queue.Queue(maxsize=10)
_ocr_results = {}
_ocr_lock = threading.Lock()

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"[INFO] Using device: {device}")

def load_models():
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

def load_ocr():
    try:
        import easyocr
        reader = easyocr.Reader(['en'], gpu=torch.cuda.is_available(), verbose=False)
        print("[OK] EasyOCR initialized")
        return reader, 'easyocr'
    except Exception as e:
        print(f"[ERROR] OCR initialization failed: {e}")
        return None, None

def read_plate_easyocr(reader, crop):
    if not reader or crop is None or crop.size == 0:
        return "", 0.0
        
    try:
        h, w = crop.shape[:2]
        if h < 10 or w < 20:
            return "", 0.0
        
        scale_factor = max(3, 200 // max(w, h))
        new_w = w * scale_factor
        new_h = h * scale_factor
        enlarged = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
        
        processed_images = []
        processed_images.append(enlarged)
        
        gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
        
        kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]], dtype=np.float32)
        sharpened = cv2.filter2D(gray, -1, kernel)
        processed_images.append(cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR))
        
        bilateral = cv2.bilateralFilter(gray, 11, 75, 75)
        processed_images.append(cv2.cvtColor(bilateral, cv2.COLOR_GRAY2BGR))
        
        thresh = cv2.adaptiveThreshold(bilateral, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 15, 8)
        processed_images.append(cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR))
        
        thresh_inv = cv2.bitwise_not(thresh)
        processed_images.append(cv2.cvtColor(thresh_inv, cv2.COLOR_GRAY2BGR))
        
        kernel_morph = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        morph = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_morph)
        processed_images.append(cv2.cvtColor(morph, cv2.COLOR_GRAY2BGR))
        
        best_text = ""
        best_confidence = 0.0
        
        for i, img in enumerate(processed_images):
            try:
                results = reader.readtext(
                    img,
                    allowlist='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ',
                    detail=1,
                    paragraph=False,
                    width_ths=0.7,
                    height_ths=0.7,
                    decoder='greedy'
                )
                
                if not results:
                    continue
                
                results = sorted(results, key=lambda r: r[2], reverse=True)
                
                combined_text = ""
                total_confidence = 0.0
                
                for bbox, text, conf in results:
                    clean_text = ''.join(c for c in text if c.isalnum()).upper()
                    if clean_text and len(clean_text) >= 2:
                        combined_text += clean_text
                        total_confidence += conf
                
                avg_confidence = total_confidence / len(results) if results else 0.0
                
                if avg_confidence > best_confidence and len(combined_text) >= 3:
                    best_text = combined_text
                    best_confidence = avg_confidence
                    
            except Exception as e:
                continue
        
        if best_text:
            if len(best_text) < 3:
                best_text = ""
                best_confidence = 0.0
            elif len(best_text) > 10:
                best_text = best_text[:8]
        
        return best_text, best_confidence
        
    except Exception as e:
        return "", 0.0

def ocr_worker(ocr_reader, ocr_type):
    global _ocr_results
    
    while True:
        try:
            task = _ocr_queue.get(timeout=1.0)
            if task is None:
                break
                
            plate_id, crop_image, bbox = task
            
            text, confidence = read_plate_easyocr(ocr_reader, crop_image)
            
            with _ocr_lock:
                _ocr_results[plate_id] = {
                    'text': text,
                    'confidence': confidence,
                    'bbox': bbox,
                    'timestamp': time.time()
                }
            
            with _ocr_lock:
                if len(_ocr_results) > 100:
                    sorted_items = sorted(_ocr_results.items(), key=lambda x: x[1]['timestamp'])
                    for old_id, _ in sorted_items[:-50]:
                        del _ocr_results[old_id]
                        
        except queue.Empty:
            continue
        except Exception as e:
            continue

def get_ocr_result(plate_id):
    with _ocr_lock:
        return _ocr_results.get(plate_id, None)

def submit_ocr_task(plate_id, crop_image, bbox):
    try:
        _ocr_queue.put_nowait((plate_id, crop_image.copy(), bbox))
        return True
    except queue.Full:
        return False

def process_detections(results, img_shape, conf_threshold, class_names=None):
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
    bbox = detection["bbox"]
    x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]
    conf = detection["confidence"]
    
    area_factor = min(1.0, ((x2-x1) * (y2-y1) / (WIDTH * HEIGHT)) / 0.5)
    
    darkness_factor = 0.0
    try:
        roi = frame[max(0, y1):min(frame.shape[0], y2), max(0, x1):min(frame.shape[1], x2)]
        if roi.size > 0:
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            darkness_factor = max(float(np.mean(gray < 80)), float(np.mean(gray > 200)) * 0.7)
    except:
        pass
    
    smoke_score = 0.5 * conf + 0.3 * area_factor + 0.2 * darkness_factor if darkness_factor > 0 else 0.6 * conf + 0.4 * area_factor
    
    if smoke_score >= 0.70:
        opacity_level = "dense"
    elif smoke_score >= 0.45:
        opacity_level = "moderate"
    else:
        opacity_level = "thin"
    
    return opacity_level, round(smoke_score, 3)

def save_detection_frame(frame, smoke_dets, vehicle_dets, plate_dets, timestamp):
    """
    Save detection frame with annotations (RPi style)
    """
    try:
        os.makedirs(SAVE_DIR, exist_ok=True)
        
        # Create filename with timestamp and detection counts
        fname = timestamp.replace(':', '-').replace('+', '').replace('.', '-')[:23]
        tags = []
        if smoke_dets: 
            tags.append(f"S{len(smoke_dets)}")
        if vehicle_dets: 
            tags.append(f"V{len(vehicle_dets)}")
        if plate_dets: 
            tags.append(f"P{len(plate_dets)}")
        
        filename = f"{fname}_{'_'.join(tags)}.jpg" if tags else f"{fname}_NODET.jpg"
        filepath = os.path.join(SAVE_DIR, filename)
        
        # Save frame with high quality
        cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        print(f"  [SAVED] {filepath}")
        
        return filepath
    except Exception as e:
        print(f"  [SAVE ERR] {e}")
        return None

def send_individual_detections(smoke_dets, vehicle_dets, plate_dets, timestamp):
    """
    Send individual detection events like RPi script does
    """
    # Send individual smoke detections
    for det in smoke_dets:
        try:
            smoke_data = {
                "timestamp": timestamp,
                "camera_id": CAMERA_ID,
                "location": LOCATION,
                "smoke_type": det.get("class_name", "smoke"),
                "opacity_level": det.get("opacity_level", "unknown"),
                "opacity_score": det.get("opacity_score", 0.0),
                "confidence": det.get("confidence", 0.0),
                "bbox": det.get("bbox", {}),
                "inference_ms": det.get("inference_ms", 0)
            }
            
            response = requests.post(f"{BACKEND_URL}/api/detections/smoke", 
                                   json=smoke_data, timeout=15)
            if response.status_code not in (200, 201):
                print(f"[API] Smoke detection failed: {response.status_code}")
        except Exception as e:
            print(f"[API] Smoke detection error: {e}")
    
    # Send individual plate detections
    for det in plate_dets:
        if det.get('text'):  # Only send plates with OCR text
            try:
                plate_data = {
                    "timestamp": timestamp,
                    "camera_id": CAMERA_ID,
                    "location": LOCATION,
                    "plate_text": det.get("text", ""),
                    "ocr_confidence": det.get("ocr_confidence", 0.0),
                    "bbox": det.get("bbox", {}),
                    "inference_ms": det.get("inference_ms", 0)
                }
                
                response = requests.post(f"{BACKEND_URL}/api/detections/plate", 
                                       json=plate_data, timeout=15)
                if response.status_code not in (200, 201):
                    print(f"[API] Plate detection failed: {response.status_code}")
            except Exception as e:
                print(f"[API] Plate detection error: {e}")
    
    # Send vehicle detections to vehicles endpoint
    for det in vehicle_dets:
        # Find associated plate text
        plate_text = ""
        for plate in plate_dets:
            if plate.get('text'):
                plate_text = plate['text']
                break
        
        if plate_text:  # Only send if we have a plate
            try:
                vehicle_data = {
                    "license_plate": plate_text,
                    "vehicle_type": det.get("class_name", "unknown"),
                    "location": LOCATION,
                    "confidence": det.get("confidence", 0.0),
                    "smoke_detected": len(smoke_dets) > 0,
                    "emission_level": "high" if smoke_dets else "normal"
                }
                
                response = requests.post(f"{BACKEND_URL}/api/vehicles/detect", 
                                       json=vehicle_data, timeout=15)
                if response.status_code not in (200, 201):
                    print(f"[API] Vehicle detection failed: {response.status_code}")
            except Exception as e:
                print(f"[API] Vehicle detection error: {e}")

def send_periodic_snapshot(smoke_dets, vehicle_dets, plate_dets, timestamp):
    """
    Send periodic detection snapshot (every few seconds like RPi)
    """
    try:
        snapshot_data = {
            "timestamp": timestamp,
            "camera_id": CAMERA_ID,
            "location": LOCATION,
            "smoke_count": len(smoke_dets),
            "vehicle_count": len(vehicle_dets),
            "plate_count": len(plate_dets),
            "detection_summary": {
                "smoke_detections": smoke_dets,
                "vehicle_detections": vehicle_dets,
                "plate_detections": plate_dets
            }
        }
        
        response = requests.post(f"{BACKEND_URL}/api/detections/snapshot", 
                               json=snapshot_data, timeout=15)
        if response.status_code not in (200, 201):
            print(f"[API] Snapshot failed: {response.status_code}")
    except Exception as e:
        print(f"[API] Snapshot error: {e}")

def send_to_backend(smoke_dets, vehicle_dets, plate_dets, frame_number):
    """
    Send detection data to backend with enhanced error handling and multiple endpoints
    Based on RPi stream implementation
    """
    try:
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Send violation data if both smoke and vehicles detected
        if smoke_dets and vehicle_dets:
            license_plates = [det.get('text', '') for det in plate_dets if det.get('text')]
            opacity_levels = [det.get('opacity_level', 'unknown') for det in smoke_dets]
            
            violation_data = {
                "timestamp": timestamp,
                "camera_id": CAMERA_ID,
                "location": LOCATION,
                "smoke_count": len(smoke_dets),
                "vehicle_count": len(vehicle_dets),
                "plate_texts": license_plates,
                "opacity_levels": opacity_levels,
                "detections_json": {
                    "smoke": smoke_dets,
                    "vehicles": vehicle_dets,
                    "plates": plate_dets,
                    "frame_number": frame_number
                }
            }
            
            # Send to detections/violation endpoint
            try:
                response = requests.post(f"{BACKEND_URL}/api/detections/violation", 
                                       json=violation_data, timeout=15)
                if response.status_code in (200, 201):
                    print(f"[API] Violation data sent successfully")
                else:
                    print(f"[API] Failed to send violation data: {response.status_code}")
            except Exception as e:
                print(f"[API] Failed violation endpoint: {e}")
            
            # Send individual vehicle violations (RPi style)
            if license_plates and smoke_dets:
                worst_smoke = max(smoke_dets, key=lambda d: d.get("opacity_score", 0), default=None)
                if worst_smoke:
                    smoke_type = worst_smoke.get("class_name", "smoke")
                    opacity = worst_smoke.get("opacity_level", "unknown")
                    conf_val = worst_smoke.get("confidence", 0.0)
                    
                    # Map opacity to severity
                    severity_map = {"dense": "critical", "moderate": "warning", "thin": "low"}
                    severity = severity_map.get(opacity, "warning")
                    
                    for plate in license_plates:
                        if plate.strip():  # Only send non-empty plates
                            vehicle_violation_data = {
                                "license_plate": plate,
                                "violation_type": smoke_type,
                                "severity": severity,
                                "description": f"Smoke ({smoke_type},{opacity}) at {LOCATION}. Confidence:{conf_val:.2f}."
                            }
                            
                            try:
                                response = requests.post(f"{BACKEND_URL}/api/vehicles/violation", 
                                                       json=vehicle_violation_data, timeout=15)
                                if response.status_code in (200, 201):
                                    print(f"[API] Vehicle violation sent for plate {plate}")
                                else:
                                    print(f"[API] Failed vehicle violation for {plate}: {response.status_code}")
                            except Exception as e:
                                print(f"[API] Failed vehicle violation for {plate}: {e}")
        
        # Always send detection summary
        detection_summary = {
            "timestamp": timestamp,
            "camera_id": CAMERA_ID,
            "location": LOCATION,
            "detection_count": len(smoke_dets) + len(vehicle_dets) + len(plate_dets),
            "smoke_count": len(smoke_dets),
            "vehicle_count": len(vehicle_dets),
            "mode": "laptop_detection",
            "metadata": {
                "frame_number": frame_number,
                "smoke_detections": smoke_dets,
                "vehicle_detections": vehicle_dets,
                "plate_detections": plate_dets
            }
        }
        
        try:
            response = requests.post(f"{BACKEND_URL}/api/detections/summary", 
                                   json=detection_summary, timeout=15)
            if response.status_code in (200, 201):
                print(f"[API] Detection summary sent successfully")
            else:
                print(f"[API] Failed to send detection summary: {response.status_code}")
        except Exception as e:
            print(f"[API] Failed summary endpoint: {e}")
            
    except Exception as e:
        print(f"[API ERROR] {e}")

def draw_boxes(frame, smoke_dets, vehicle_dets, plate_dets):
    for det in smoke_dets:
        bbox = det["bbox"]
        x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]
        
        opacity_level = det.get('opacity_level', 'unknown')
        opacity_score = det.get('opacity_score', 0.0)
        
        if opacity_level == 'dense':
            box_color = (0, 0, 255)
            text_color = (0, 0, 255)
        elif opacity_level == 'moderate':
            box_color = (0, 100, 255)
            text_color = (0, 100, 255)
        else:
            box_color = (0, 150, 255)
            text_color = (0, 150, 255)
        
        thickness = 4 if opacity_level == 'dense' else 3 if opacity_level == 'moderate' else 2
        cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, thickness)
        
        text1 = f"{det['class']} {det['confidence']:.2f}"
        text_size1 = cv2.getTextSize(text1, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)[0]
        cv2.rectangle(frame, (x1, max(0, y1-30)), (x1 + text_size1[0] + 5, max(0, y1-5)), (0, 0, 0), -1)
        cv2.putText(frame, text1, (x1, max(0, y1-10)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, text_color, 2)
        
        text2 = f"{opacity_level.upper()} ({opacity_score:.2f})"
        text_size2 = cv2.getTextSize(text2, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
        cv2.rectangle(frame, (x1, max(0, y1-5)), (x1 + text_size2[0] + 5, max(0, y1+15)), (0, 0, 0), -1)
        cv2.putText(frame, text2, (x1, max(0, y1+10)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, text_color, 2)
    
    for det in vehicle_dets:
        bbox = det["bbox"]
        x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        
        text = f"{det['class']} {det['confidence']:.2f}"
        text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)[0]
        cv2.rectangle(frame, (x1, max(0, y1-25)), (x1 + text_size[0] + 5, max(0, y1-5)), (0, 0, 0), -1)
        cv2.putText(frame, text, (x1, max(0, y1-10)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    
    for det in plate_dets:
        bbox = det["bbox"]
        x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
        
        text = det.get("text", "plate")
        if not text:
            text = "processing..."
        
        text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)[0]
        cv2.rectangle(frame, (x1, max(0, y1-25)), (x1 + text_size[0] + 5, max(0, y1-5)), (0, 0, 0), -1)
        cv2.putText(frame, text, (x1, max(0, y1-10)), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
    
    if smoke_dets and vehicle_dets:
        cv2.rectangle(frame, (0, 0), (WIDTH-1, HEIGHT-1), (0, 0, 255), 8)
        cv2.putText(frame, "VIOLATION DETECTED", (WIDTH//2-180, HEIGHT-20),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
    
    timestamp = datetime.now().strftime("%H:%M:%S")
    cv2.rectangle(frame, (5, 5), (200, 35), (0, 0, 0), -1)
    cv2.putText(frame, timestamp, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    
    counts = f"S:{len(smoke_dets)} V:{len(vehicle_dets)} P:{len(plate_dets)}"
    cv2.rectangle(frame, (5, 35), (250, 65), (0, 0, 0), -1)
    cv2.putText(frame, counts, (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    
    return frame

def infer_worker(models, ocr_reader, ocr_type):
    global _smoke, _vehicle, _plates, _all
    
    while True:
        frame, oh, ow, frame_number = _iqueue.get()
        
        smoke_dets = []
        vehicle_dets = []
        plate_dets = []
        all_dets = []
        
        t0 = time.time()
        
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
        
        if 'vehicle' in models:
            try:
                results = models['vehicle'](frame, conf=VEHICLE_CONF)
                vehicle_dets = process_detections(results, frame.shape, VEHICLE_CONF,
                                                ['passenger', 'puv', 'services', 'two_wheel'])
                all_dets.extend(vehicle_dets)
            except Exception as e:
                print(f"[ERROR] Vehicle detection: {e}")
        
        if 'plate' in models:
            try:
                results = models['plate'](frame, conf=PLATE_CONF)
                plate_raw = process_detections(results, frame.shape, PLATE_CONF, ['license_plate'])
                
                for i, det in enumerate(plate_raw):
                    bbox = det["bbox"]
                    x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]
                    
                    plate_id = f"plate_{int(time.time()*1000)}_{i}_{x1}_{y1}"
                    
                    crop = frame[max(0, y1):min(oh, y2), max(0, x1):min(ow, x2)].copy()
                    
                    if crop.size > 0:
                        ocr_submitted = submit_ocr_task(plate_id, crop, bbox)
                    
                    ocr_result = None
                    with _ocr_lock:
                        current_time = time.time()
                        for result_id, result_data in _ocr_results.items():
                            if current_time - result_data['timestamp'] < 2.0:
                                result_bbox = result_data['bbox']
                                if (abs(result_bbox['x1'] - x1) < 50 and 
                                    abs(result_bbox['y1'] - y1) < 50):
                                    ocr_result = result_data
                                    break
                    
                    if ocr_result:
                        det['text'] = ocr_result['text']
                        det['ocr_confidence'] = ocr_result['confidence']
                    else:
                        det['text'] = ""
                        det['ocr_confidence'] = 0.0
                    
                    det['plate_id'] = plate_id
                    plate_dets.append(det)
                    all_dets.append(det)
                    
            except Exception as e:
                print(f"[ERROR] Plate detection: {e}")
        
        with _dlock:
            _smoke = smoke_dets
            _vehicle = vehicle_dets
            _plates = plate_dets
            _all = all_dets
        
        inference_time = int((time.time() - t0) * 1000)
        
        if smoke_dets or vehicle_dets or plate_dets:
            print(f"  [DETECT] Frame {frame_number}: S:{len(smoke_dets)} V:{len(vehicle_dets)} P:{len(plate_dets)} {inference_time}ms")
            
            if smoke_dets and vehicle_dets:
                print(f"  [VIOLATION] Smoke + Vehicle detected - sending to backend")
                
                # Save detection frame with annotations (RPi style)
                timestamp = datetime.now(timezone.utc).isoformat()
                annotated_frame = draw_boxes(frame.copy(), smoke_dets, vehicle_dets, plate_dets)
                threading.Thread(target=save_detection_frame, 
                               args=(annotated_frame, smoke_dets, vehicle_dets, plate_dets, timestamp), 
                               daemon=True).start()
                
                # Send violation data
                threading.Thread(target=send_to_backend, 
                               args=(smoke_dets, vehicle_dets, plate_dets, frame_number), 
                               daemon=True).start()
                
                # Send individual detection events (RPi style)
                threading.Thread(target=send_individual_detections, 
                               args=(smoke_dets, vehicle_dets, plate_dets, timestamp), 
                               daemon=True).start()

def main():
    print("[INFO] Starting laptop detection system for SMOKi...")
    
    if not os.path.exists(VIDEO_FILE):
        print(f"[ERROR] Video file not found: {VIDEO_FILE}")
        return
    
    models = load_models()
    if not models:
        print("[ERROR] No models loaded successfully!")
        return
    
    ocr_reader, ocr_type = load_ocr()
    
    cap = cv2.VideoCapture(VIDEO_FILE)
    if not cap.isOpened():
        print(f"[ERROR] Could not open video file: {VIDEO_FILE}")
        return
    
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_fps = cap.get(cv2.CAP_PROP_FPS)
    video_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    video_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = total_frames / video_fps if video_fps > 0 else 0
    
    print(f"[OK] Video loaded: {video_width}x{video_height} @ {video_fps:.1f}fps")
    print(f"[OK] Total frames: {total_frames}, Duration: {duration:.1f}s")
    print(f"[OK] Backend URL: {BACKEND_URL}")
    print(f"[OK] Camera ID: {CAMERA_ID}")
    print(f"[OK] Location: {LOCATION}")
    
    threading.Thread(target=infer_worker, args=(models, ocr_reader, ocr_type), daemon=True).start()
    threading.Thread(target=ocr_worker, args=(ocr_reader, ocr_type), daemon=True).start()
    
    print("\n[READY] Processing video - Press 'q' to quit, SPACE to pause/resume\n")
    
    frame_count = 0
    paused = False
    last_snapshot_time = time.time()
    SNAPSHOT_INTERVAL = 3.0  # Send snapshot every 3 seconds like RPi
    
    try:
        while True:
            if not paused:
                ret, frame = cap.read()
                if not ret:
                    print("[INFO] End of video reached")
                    break
                
                if frame.shape[:2] != (HEIGHT, WIDTH):
                    frame = cv2.resize(frame, (WIDTH, HEIGHT))
                
                if frame_count % INFER_EVERY == 0:
                    try:
                        _iqueue.put_nowait((frame.copy(), HEIGHT, WIDTH, frame_count))
                    except queue.Full:
                        pass
                
                frame_count += 1
            
            with _dlock:
                smoke_dets = list(_smoke)
                vehicle_dets = list(_vehicle)
                plate_dets = list(_plates)
            
            # Send periodic snapshots like RPi script
            current_time = time.time()
            if current_time - last_snapshot_time >= SNAPSHOT_INTERVAL:
                timestamp = datetime.now(timezone.utc).isoformat()
                threading.Thread(target=send_periodic_snapshot, 
                               args=(smoke_dets, vehicle_dets, plate_dets, timestamp), 
                               daemon=True).start()
                last_snapshot_time = current_time
            
            if not paused:
                display_frame = draw_boxes(frame.copy(), smoke_dets, vehicle_dets, plate_dets)
                
                progress = (frame_count / total_frames) * 100 if total_frames > 0 else 0
                current_time = frame_count / video_fps if video_fps > 0 else 0
                cv2.putText(display_frame, f"Progress: {progress:.1f}% ({current_time:.1f}s/{duration:.1f}s)", 
                           (10, HEIGHT - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                
                if paused:
                    cv2.putText(display_frame, "PAUSED - Press SPACE to resume", 
                               (WIDTH//2 - 150, HEIGHT//2), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            
            cv2.imshow('SMOKi Laptop Detection System', display_frame)
            
            key = cv2.waitKey(30) & 0xFF
            if key == ord('q'):
                break
            elif key == ord(' '):
                paused = not paused
                print(f"[INFO] Video {'paused' if paused else 'resumed'}")
            elif key == ord('r'):
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                frame_count = 0
                print("[INFO] Video restarted")
            
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user")
    
    finally:
        print("[INFO] Cleaning up...")
        
        try:
            _ocr_queue.put_nowait(None)
        except:
            pass
            
        cap.release()
        cv2.destroyAllWindows()
        
        print(f"\n[STATS] Processed {frame_count} frames")
        with _dlock:
            print(f"[STATS] Final detections - S:{len(_smoke)} V:{len(_vehicle)} P:{len(_plates)}")
        with _ocr_lock:
            print(f"[STATS] OCR results processed: {len(_ocr_results)}")

if __name__ == '__main__':
    main()