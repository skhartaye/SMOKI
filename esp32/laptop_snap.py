#!/usr/bin/env python3
"""
laptop_snap.py — Laptop version of rpi_snap.py
Uses webcam + PyTorch models + EasyOCR for license plate detection
Press 'q' to quit, 's' to save current frame
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
import sys
import os
# Basic EasyOCR import (enhanced_plate_ocr not available)
import easyocr
from ultralytics import YOLO


# Video file path
VIDEO_FILE  = 'rotonda_trim.mp4'

# API Configuration
API_URL = 'https://smoki-backend-rpi.onrender.com'
DEVICE_ID = 'SMOKi_Camera_01'
CAMERA_LOCATION = 'Main Camera Station'
SEND_TO_API = True  # Set to False to disable API sending

# Save directory for manual frame saves
SAVE_DIR = './saved_frames'

WIDTH, HEIGHT, FPS = 1280, 720, 24
INFER_EVERY = 15  # Increased from 8 to process fewer frames (slower processing)

# Model confidence thresholds
SMOKE_CONF   = 0.15  # Lowered to test spatial matching with detected smoke
PLATE_CONF   = 0.15
VEHICLE_CONF = 0.30

# Model paths (relative to esp32 directory when running from esp32)
MODELS = {
    'smoke': 'yolov8n-smoke-seg.pt',
    'plate': 'license-plate.pt', 
    'vehicle': 'vehicle-class.pt'
}

# Global variables
_smoke = []
_vehicle = []
_plates = []
_all = []
_dlock = threading.Lock()
_iqueue = queue.Queue(maxsize=2)
_ocr_queue = queue.Queue(maxsize=20)  # Larger queue for OCR processing
_ocr_results = {}  # Store OCR results by plate ID
_ocr_lock = threading.Lock()
_api_queue = queue.Queue(maxsize=10)  # Increased queue size for faster updates

# Device selection
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"[INFO] Using device: {device}")



# ── Model loading ─────────────────────────────────────────────────────────────
def load_models():
    """Load all PyTorch models"""
    models = {}
    for name, path in MODELS.items():
        if os.path.exists(path):
            try:
                # Load local YOLO model directly
                from ultralytics import YOLO
                model = YOLO(path)
                model.to(device)
                
                # Print model info
                print(f"[OK] Loaded {name} model: {path}")
                if hasattr(model, 'names'):
                    print(f"  Classes: {model.names}")
                
                models[name] = model
            except Exception as e:
                print(f"[WARN] Failed to load {name} model: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"[WARN] Model file not found: {path}")
    return models
def api_worker():
    """Background worker for sending API data"""
    print("[INFO] API worker started")
    
    while True:
        try:
            # Get API task from queue
            task = _api_queue.get(timeout=1.0)
            if task is None:  # Shutdown signal
                break
                
            frame, smoke_dets, vehicle_dets, plate_dets, frame_number = task
            
            # Send data to API
            send_detection_data(frame, smoke_dets, vehicle_dets, plate_dets, frame_number)
                        
        except queue.Empty:
            continue
        except Exception as e:
            print(f"[API WORKER ERROR] {e}")
            continue

def submit_api_task(frame, smoke_dets, vehicle_dets, plate_dets, frame_number):
    """Submit API task to background worker"""
    if not SEND_TO_API:
        return True
        
    try:
        _api_queue.put_nowait((frame.copy(), smoke_dets.copy(), vehicle_dets.copy(), plate_dets.copy(), frame_number))
        return True
    except queue.Full:
        print("[API] Queue full, skipping frame")
        return False

# ── OCR Background Worker ────────────────────────────────────────────────────
def ocr_worker(ocr_reader, ocr_type):
    """Background worker for OCR processing"""
    global _ocr_results
    
    print(f"[INFO] OCR background worker started with {ocr_type} OCR")
    
    while True:
        try:
            # Get OCR task from queue
            task = _ocr_queue.get(timeout=1.0)
            if task is None:  # Shutdown signal
                break
                
            plate_id, crop_image, bbox = task
            print(f"[OCR] Processing plate {plate_id} - crop size: {crop_image.shape}")
            
            # Process OCR based on type
            if ocr_type == 'enhanced' or ocr_type == 'easyocr':
                print(f"[OCR] Starting OCR for {plate_id}")
                text, confidence, ocr_metadata = read_plate_enhanced(ocr_reader, crop_image, bbox)
                print(f"[OCR] OCR result for {plate_id}: '{text}' conf={confidence:.3f}")
            else:
                print(f"[OCR] Starting basic OCR for {plate_id}")
                text, confidence = read_plate_easyocr(ocr_reader, crop_image)
                ocr_metadata = {}
                print(f"[OCR] Basic OCR result for {plate_id}: '{text}' conf={confidence:.3f}")
            
            # Store result
            with _ocr_lock:
                _ocr_results[plate_id] = {
                    'text': text,
                    'confidence': confidence,
                    'bbox': bbox,
                    'ocr_metadata': ocr_metadata,
                    'timestamp': time.time()
                }
                print(f"[OCR] Stored result for {plate_id} in cache")
            
            # Clean up old results (keep only last 50)
            with _ocr_lock:
                if len(_ocr_results) > 50:
                    # Remove oldest entries more frequently
                    sorted_items = sorted(_ocr_results.items(), key=lambda x: x[1]['timestamp'])
                    for old_id, _ in sorted_items[:-25]:  # Keep only 25 most recent
                        del _ocr_results[old_id]
                        
        except queue.Empty:
            continue
        except Exception as e:
            print(f"[OCR WORKER ERROR] {e}")
            import traceback
            traceback.print_exc()
            continue

def get_ocr_result(plate_id):
    """Get OCR result for a plate ID"""
    with _ocr_lock:
        return _ocr_results.get(plate_id, None)

def submit_ocr_task(plate_id, crop_image, bbox):
    """Submit OCR task to background worker"""
    try:
        print(f"[OCR] Submitting task for {plate_id} - crop shape: {crop_image.shape}")
        _ocr_queue.put_nowait((plate_id, crop_image.copy(), bbox))
        print(f"[OCR] Task submitted successfully for {plate_id}")
        return True
    except queue.Full:
        print(f"[OCR] Queue full, cannot submit task for {plate_id}")
        return False
# ── OCR Functions ─────────────────────────────────────────────────────────────
def load_ocr():
    """Initialize EasyOCR reader for license plate recognition"""
    try:
        import easyocr
        reader = easyocr.Reader(['en'], gpu=torch.cuda.is_available(), verbose=False)
        print("[OK] Basic EasyOCR initialized for license plate recognition")
        return reader, 'easyocr'
    except Exception as e:
        print(f"[ERROR] OCR initialization failed: {e}")
        return None, None

def read_plate_enhanced(reader, crop, bbox):
    """Extract text using EasyOCR (fallback from enhanced OCR)"""
    if not reader or crop is None or crop.size == 0:
        return "", 0.0, {}
        
    try:
        # Use basic EasyOCR
        results = reader.readtext(crop)
        
        if results:
            # Get the result with highest confidence
            best_result = max(results, key=lambda x: x[2])
            text = best_result[1].strip()
            confidence = best_result[2]
            
            # Create basic metadata
            ocr_metadata = {
                'processing_method': 'basic_easyocr',
                'image_quality_score': confidence * 100,  # Use confidence as quality proxy
                'blur_score': 50.0,  # Default value
                'contrast_score': 50.0,  # Default value
                'brightness_score': 50.0,  # Default value
                'plate_angle': 0.0,  # Default value
                'processing_time_ms': 0,  # Not measured in basic version
                'preprocessing_steps': ['resize', 'basic_cleanup']
            }
            
            if text and confidence > 0.1:
                print(f"  [EasyOCR] '{text}' conf: {confidence:.2f}")
            
            return text, confidence, ocr_metadata
        else:
            return "", 0.0, {}
        
    except Exception as e:
        print(f"[EasyOCR ERROR] {e}")
        return "", 0.0, {}

def read_plate_easyocr(reader, crop):
    """Extract text using EasyOCR with enhanced preprocessing for license plates"""
    if not reader or crop is None or crop.size == 0:
        return "", 0.0
        
    try:
        # Get original dimensions
        h, w = crop.shape[:2]
        
        # Skip very small crops
        if h < 10 or w < 20:
            return "", 0.0
        
        # Resize for better OCR (make it larger)
        scale_factor = max(3, 200 // max(w, h))  # Scale up small images more
        new_w = w * scale_factor
        new_h = h * scale_factor
        enlarged = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
        
        # Apply multiple preprocessing techniques
        processed_images = []
        
        # Original enlarged image
        processed_images.append(enlarged)
        
        # Convert to grayscale and enhance
        gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
        
        # Apply sharpening kernel
        kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]], dtype=np.float32)
        sharpened = cv2.filter2D(gray, -1, kernel)
        processed_images.append(cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR))
        
        # Apply bilateral filter to reduce noise while keeping edges
        bilateral = cv2.bilateralFilter(gray, 11, 75, 75)
        processed_images.append(cv2.cvtColor(bilateral, cv2.COLOR_GRAY2BGR))
        
        # Apply adaptive threshold
        thresh = cv2.adaptiveThreshold(bilateral, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 15, 8)
        processed_images.append(cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR))
        
        # Apply inverted threshold
        thresh_inv = cv2.bitwise_not(thresh)
        processed_images.append(cv2.cvtColor(thresh_inv, cv2.COLOR_GRAY2BGR))
        
        # Apply morphological operations to clean up
        kernel_morph = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        morph = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_morph)
        processed_images.append(cv2.cvtColor(morph, cv2.COLOR_GRAY2BGR))
        
        best_text = ""
        best_confidence = 0.0
        
        # Try OCR on all processed versions
        for i, img in enumerate(processed_images):
            try:
                # Use EasyOCR with license plate specific settings
                results = reader.readtext(
                    img,
                    allowlist='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ',  # Only alphanumeric
                    detail=1,
                    paragraph=False,
                    width_ths=0.7,  # Adjust for license plate text spacing
                    height_ths=0.7,
                    decoder='greedy'  # Use greedy decoder for better speed
                )
                
                if not results:
                    continue
                
                # Sort results by confidence
                results = sorted(results, key=lambda r: r[2], reverse=True)
                
                # Combine all detected text
                combined_text = ""
                total_confidence = 0.0
                
                for bbox, text, conf in results:
                    # Clean text (remove spaces and special characters)
                    clean_text = ''.join(c for c in text if c.isalnum()).upper()
                    if clean_text and len(clean_text) >= 2:  # Minimum 2 characters
                        combined_text += clean_text
                        total_confidence += conf
                
                # Calculate average confidence
                avg_confidence = total_confidence / len(results) if results else 0.0
                
                # Update best result if this is better
                if avg_confidence > best_confidence and len(combined_text) >= 3:
                    best_text = combined_text
                    best_confidence = avg_confidence
                    
            except Exception as e:
                continue
        
        # Additional filtering for license plate patterns
        if best_text:
            # Remove very short results
            if len(best_text) < 3:
                best_text = ""
                best_confidence = 0.0
            # Remove results that are too long (most license plates are 6-8 characters)
            elif len(best_text) > 10:
                best_text = best_text[:8]  # Truncate to reasonable length
        
        if best_text:
            print(f"  [EasyOCR] '{best_text}' confidence: {best_confidence:.2f}")
        
        return best_text, best_confidence
        
    except Exception as e:
        print(f"[EasyOCR ERROR] {e}")
        return "", 0.0

# ── API Functions ────────────────────────────────────────────────────────────
def send_detection_data(frame, smoke_dets, vehicle_dets, plate_dets, frame_number):
    """Send detection data to backend API"""
    if not SEND_TO_API:
        return True
        
    try:
        # Encode frame as JPEG
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        
        # Prepare all detections in the format expected by the API
        all_detections = []
        
        # Add smoke detections
        for det in smoke_dets:
            all_detections.append({
                "model_name": "smoke_detection",
                "class_name": det["class"],
                "class": det["class"],
                "conf": det["confidence"],
                "confidence": det["confidence"],
                "bounding_box": det["bbox"],
                "bbox": det["bbox"],
                "opacity_level": det.get("opacity_level", "unknown"),
                "opacity_score": det.get("opacity_score", 0.0)
            })
        
        # Add vehicle detections
        for det in vehicle_dets:
            all_detections.append({
                "model_name": "vehicle_detection",
                "class_name": det["class"],
                "class": det["class"],
                "conf": det["confidence"],
                "confidence": det["confidence"],
                "bounding_box": det["bbox"],
                "bbox": det["bbox"]
            })
        
        # Add plate detections
        for det in plate_dets:
            plate_detection = {
                "model_name": "license_plate",
                "class_name": "license_plate",
                "class": "license_plate",
                "conf": det["confidence"],
                "confidence": det["confidence"],
                "bounding_box": det["bbox"],
                "bbox": det["bbox"],
                "plate_text": det.get("text", ""),
                "ocr_confidence": det.get("ocr_confidence", 0.0)
            }
            
            # Add enhanced OCR metadata if available
            ocr_metadata = det.get("ocr_metadata", {})
            if ocr_metadata:
                plate_detection["ocr_metadata"] = ocr_metadata
                plate_detection["image_quality_score"] = ocr_metadata.get("image_quality_score", 0.0)
                plate_detection["blur_score"] = ocr_metadata.get("blur_score", 0.0)
                plate_detection["contrast_score"] = ocr_metadata.get("contrast_score", 0.0)
                plate_detection["plate_angle"] = ocr_metadata.get("plate_angle", 0.0)
                plate_detection["processing_time_ms"] = ocr_metadata.get("processing_time_ms", 0)
            
            all_detections.append(plate_detection)
        
        # Count detections by type
        smoke_count = len(smoke_dets)
        vehicle_count = len(vehicle_dets)
        plate_count = len(plate_dets)
        
        # Prepare metadata
        timestamp = datetime.now(timezone.utc).isoformat()
        metadata = {
            "timestamp": timestamp,
            "camera_id": DEVICE_ID,
            "location": CAMERA_LOCATION,
            "frame_number": frame_number,
            "detections": all_detections,
            "smoke_count": smoke_count,
            "vehicle_count": vehicle_count,
            "plate_count": plate_count,
            "detection_counts": {
                "smoke": smoke_count,
                "vehicle": vehicle_count,
                "plate": plate_count
            },
            "is_violation": smoke_count > 0 and vehicle_count > 0,
            "source": "laptop_snap_video_processing"
        }
        
        # Send as multipart form data (file upload)
        files = {
            'frame': ('frame.jpg', buffer.tobytes(), 'image/jpeg')
        }
        data = {
            'metadata': json.dumps(metadata)
        }
        
        response = requests.post(
            f"{API_URL}/api/stream/frame",
            files=files,
            data=data,
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"[API] ✓ Sent frame {frame_number} - S:{smoke_count} V:{vehicle_count} P:{plate_count}")
            return True
        else:
            print(f"[API] ✗ Failed to send frame {frame_number}: {response.status_code}")
            if response.text:
                print(f"[API] Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"[API ERROR] {e}")
        return False

# ── Frame Saving ──────────────────────────────────────────────────────────────
def save_current_frame(frame, smoke_dets, vehicle_dets, plate_dets, frame_number):
    """Save current frame with all detection overlays"""
    try:
        os.makedirs(SAVE_DIR, exist_ok=True)
        
        # Create filename with timestamp and detection counts
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        tags = []
        if smoke_dets: tags.append(f"S{len(smoke_dets)}")
        if vehicle_dets: tags.append(f"V{len(vehicle_dets)}")
        if plate_dets: tags.append(f"P{len(plate_dets)}")
        
        tag_str = "_".join(tags) if tags else "NoDetections"
        filename = f"frame_{timestamp}_F{frame_number}_{tag_str}.jpg"
        filepath = os.path.join(SAVE_DIR, filename)
        
        # Save frame with all overlays
        cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
        
        print(f"[SAVED] {filepath}")
        
        # Also save detection info as text file
        info_file = filepath.replace('.jpg', '_info.txt')
        with open(info_file, 'w') as f:
            f.write(f"Frame: {frame_number}\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Detections: S:{len(smoke_dets)} V:{len(vehicle_dets)} P:{len(plate_dets)}\n\n")
            
            if smoke_dets:
                f.write("SMOKE DETECTIONS:\n")
                for i, det in enumerate(smoke_dets):
                    opacity_level = det.get('opacity_level', 'unknown')
                    opacity_score = det.get('opacity_score', 0.0)
                    f.write(f"  Smoke {i+1}: {det['class']} | Confidence: {det['confidence']:.3f} | Opacity: {opacity_level} ({opacity_score:.3f})\n")
                f.write("\n")
            
            if vehicle_dets:
                f.write("VEHICLE DETECTIONS:\n")
                for i, det in enumerate(vehicle_dets):
                    f.write(f"  Vehicle {i+1}: {det['class']} | Confidence: {det['confidence']:.3f}\n")
                f.write("\n")
            
            if plate_dets:
                f.write("LICENSE PLATE DETECTIONS:\n")
                for i, det in enumerate(plate_dets):
                    text = det.get('text', '')
                    ocr_conf = det.get('ocr_confidence', 0.0)
                    ocr_metadata = det.get('ocr_metadata', {})
                    
                    f.write(f"  Plate {i+1}: '{text}' | OCR Confidence: {ocr_conf:.3f}\n")
                    
                    # Add enhanced OCR metadata if available
                    if ocr_metadata:
                        f.write(f"    Quality Score: {ocr_metadata.get('image_quality_score', 0):.1f}\n")
                        f.write(f"    Blur Score: {ocr_metadata.get('blur_score', 0):.1f}\n")
                        f.write(f"    Contrast Score: {ocr_metadata.get('contrast_score', 0):.1f}\n")
                        f.write(f"    Brightness Score: {ocr_metadata.get('brightness_score', 0):.1f}\n")
                        f.write(f"    Aspect Ratio: {ocr_metadata.get('aspect_ratio', 0):.2f}\n")
                        f.write(f"    Plate Angle: {ocr_metadata.get('plate_angle', 0):.1f}°\n")
                        f.write(f"    Processing Time: {ocr_metadata.get('processing_time_ms', 0)}ms\n")
                        f.write(f"    Preprocessing Steps: {len(ocr_metadata.get('preprocessing_steps', []))}\n")
                        if ocr_metadata.get('character_confidences'):
                            char_confs = ocr_metadata['character_confidences']
                            f.write(f"    Character Confidences: {[f'{c:.2f}' for c in char_confs]}\n")
                f.write("\n")
        
        return True
        
    except Exception as e:
        print(f"[SAVE ERROR] {e}")
        return False
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
                    # Get box coordinates (xyxy format)
                    x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy()
                    cls_id = int(boxes.cls[i])
                    
                    # Ensure coordinates are within image bounds
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

# ── Drawing functions ─────────────────────────────────────────────────────────
def draw_boxes(frame, smoke_dets, vehicle_dets, plate_dets):
    """Draw detection boxes on frame"""
    # Draw smoke detections (red) with enhanced opacity info
    for det in smoke_dets:
        bbox = det["bbox"]
        x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]
        
        # Get opacity info
        opacity_level = det.get('opacity_level', 'unknown')
        opacity_score = det.get('opacity_score', 0.0)
        
        # Choose color based on opacity level
        if opacity_level == 'dense':
            box_color = (0, 0, 255)  # Bright red for dense
            text_color = (0, 0, 255)
        elif opacity_level == 'moderate':
            box_color = (0, 100, 255)  # Orange-red for moderate
            text_color = (0, 100, 255)
        else:  # thin
            box_color = (0, 150, 255)  # Light red for thin
            text_color = (0, 150, 255)
        
        # Draw thicker box for higher opacity
        thickness = 4 if opacity_level == 'dense' else 3 if opacity_level == 'moderate' else 2
        cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, thickness)
        
        # Multi-line text for better readability with background
        # Line 1: Class and confidence
        text1 = f"{det['class']} {det['confidence']:.2f}"
        text_size1 = cv2.getTextSize(text1, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)[0]
        cv2.rectangle(frame, (x1, max(0, y1-30)), (x1 + text_size1[0] + 5, max(0, y1-5)), (0, 0, 0), -1)
        cv2.putText(frame, text1, (x1, max(0, y1-10)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, text_color, 2)
        
        # Line 2: Opacity level and score
        text2 = f"{opacity_level.upper()} ({opacity_score:.2f})"
        text_size2 = cv2.getTextSize(text2, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
        cv2.rectangle(frame, (x1, max(0, y1-5)), (x1 + text_size2[0] + 5, max(0, y1+15)), (0, 0, 0), -1)
        cv2.putText(frame, text2, (x1, max(0, y1+10)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, text_color, 2)
    
    # Draw vehicle detections (green)
    for det in vehicle_dets:
        bbox = det["bbox"]
        x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        
        # Add background for text
        text = f"{det['class']} {det['confidence']:.2f}"
        text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)[0]
        cv2.rectangle(frame, (x1, max(0, y1-25)), (x1 + text_size[0] + 5, max(0, y1-5)), (0, 0, 0), -1)
        cv2.putText(frame, text, (x1, max(0, y1-10)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    
    # Draw plate detections (yellow) with OCR status
    for det in plate_dets:
        bbox = det["bbox"]
        x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
        
        text = det.get("text", "")
        ocr_source = det.get("ocr_source", "unknown")
        
        # Show different text based on OCR status
        if text and text != "too_small":
            display_text = text
        elif text == "too_small":
            display_text = "too small"
        elif ocr_source == "processing":
            display_text = "processing..."
        elif ocr_source == "cached":
            display_text = f"{text}" if text else "cached"
        elif ocr_source == "queue_full":
            display_text = "queue full"
        elif ocr_source == "skipped":
            display_text = "skipped"
        else:
            display_text = "waiting..."
        
        # Add background for text
        text_size = cv2.getTextSize(display_text, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)[0]
        cv2.rectangle(frame, (x1, max(0, y1-25)), (x1 + text_size[0] + 5, max(0, y1-5)), (0, 0, 0), -1)
        cv2.putText(frame, display_text, (x1, max(0, y1-10)), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
    
    # Draw violation indicator
    if smoke_dets and vehicle_dets:
        cv2.rectangle(frame, (0, 0), (WIDTH-1, HEIGHT-1), (0, 0, 255), 8)
        cv2.putText(frame, "VIOLATION DETECTED", (WIDTH//2-180, HEIGHT-20),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
    
    # Draw timestamp and counts with background
    timestamp = datetime.now().strftime("%H:%M:%S")
    cv2.rectangle(frame, (5, 5), (200, 35), (0, 0, 0), -1)
    cv2.putText(frame, timestamp, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    
    counts = f"S:{len(smoke_dets)} V:{len(vehicle_dets)} P:{len(plate_dets)}"
    cv2.rectangle(frame, (5, 35), (250, 65), (0, 0, 0), -1)
    cv2.putText(frame, counts, (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    
    # Add opacity legend if there are smoke detections
    if smoke_dets:
        legend_y = 70
        cv2.rectangle(frame, (5, legend_y), (200, legend_y + 60), (0, 0, 0), -1)
        cv2.putText(frame, "OPACITY LEVELS:", (10, legend_y + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        cv2.putText(frame, "DENSE (>0.70)", (10, legend_y + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
        cv2.putText(frame, "MODERATE (0.45-0.70)", (10, legend_y + 45), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 100, 255), 1)
        cv2.putText(frame, "THIN (<0.45)", (10, legend_y + 60), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 150, 255), 1)
    
    return frame



# ── Inference worker ──────────────────────────────────────────────────────────
def infer_worker(models, ocr_reader, ocr_type):
    """Main inference worker thread"""
    global _smoke, _vehicle, _plates, _all
    
    while True:
        frame, oh, ow = _iqueue.get()
        
        smoke_dets = []
        vehicle_dets = []
        plate_dets = []
        all_dets = []
        
        t0 = time.time()
        
        # Run smoke detection with multiple thresholds for testing
        if 'smoke' in models:
            try:
                # Try with very low threshold first to see if model detects anything
                results_low = models['smoke'](frame, conf=0.1)  # Very low threshold
                results_normal = models['smoke'](frame, conf=SMOKE_CONF)
                
                # Debug: Print raw detection info
                if results_low and len(results_low) > 0 and results_low[0].boxes is not None:
                    raw_detections_low = len(results_low[0].boxes)
                    print(f"  [DEBUG] Raw smoke detections (conf=0.1): {raw_detections_low}")
                else:
                    print(f"  [DEBUG] No smoke detections even at conf=0.1")
                
                if results_normal and len(results_normal) > 0 and results_normal[0].boxes is not None:
                    raw_detections_normal = len(results_normal[0].boxes)
                    print(f"  [DEBUG] Raw smoke detections (conf={SMOKE_CONF}): {raw_detections_normal}")
                else:
                    print(f"  [DEBUG] No smoke detections at conf={SMOKE_CONF}")
                
                # Use normal threshold for actual processing
                smoke_raw = process_detections(results_normal, frame.shape, SMOKE_CONF, 
                                             ['smoke_black', 'smoke_white'])
                
                print(f"  [DEBUG] Smoke detections after processing: {len(smoke_raw)}")
                
                for det in smoke_raw:
                    opacity_level, opacity_score = smoke_opacity(det, frame)
                    det['opacity_level'] = opacity_level
                    det['opacity_score'] = opacity_score
                    smoke_dets.append(det)
                    all_dets.append(det)
                    print(f"  [DEBUG] Added smoke: {det['class']} conf={det['confidence']:.3f} opacity={opacity_level}")
                    
            except Exception as e:
                print(f"[ERROR] Smoke detection: {e}")
                import traceback
                traceback.print_exc()
        
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
        if 'plate' in models:
            try:
                results = models['plate'](frame, conf=PLATE_CONF)
                plate_raw = process_detections(results, frame.shape, PLATE_CONF, ['license_plate'])
                
                print(f"  [DEBUG] Raw plate detections: {len(plate_raw)}")
                
                # Process each detected plate with smart OCR strategy
                for i, det in enumerate(plate_raw):
                    bbox = det["bbox"]
                    x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]
                    
                    # Calculate plate size - only process OCR for reasonably sized plates
                    plate_width = x2 - x1
                    plate_height = y2 - y1
                    plate_area = plate_width * plate_height
                    
                    # Debug: Print plate size info
                    print(f"  [PLATE] Detected plate {i}: {plate_width}x{plate_height} = {plate_area} pixels")
                    
                    # Skip OCR for very small plates (less than 200 pixels)
                    if plate_area < 200:
                        det['text'] = "too_small"
                        det['ocr_confidence'] = 0.0
                        det['ocr_metadata'] = {}
                        det['plate_id'] = f"small_{int(time.time()*1000)}_{i}"
                        plate_dets.append(det)
                        all_dets.append(det)
                        continue
                    
                    # Create unique plate ID based on position and time
                    plate_id = f"plate_{int(time.time()*1000)}_{i}_{x1}_{y1}"
                    
                    # Check if we have a recent OCR result for a similar position first
                    ocr_result = None
                    with _ocr_lock:
                        current_time = time.time()
                        for result_id, result_data in _ocr_results.items():
                            # Check if result is recent (within 3 seconds for better caching)
                            if current_time - result_data['timestamp'] < 3.0:
                                # Check if position is similar (within 80 pixels for better matching)
                                result_bbox = result_data['bbox']
                                if (abs(result_bbox['x1'] - x1) < 80 and 
                                    abs(result_bbox['y1'] - y1) < 80 and
                                    result_data['text']):  # Only use results with actual text
                                    ocr_result = result_data
                                    break
                    
                    # If we have a cached result, use it
                    if ocr_result:
                        det['text'] = ocr_result['text']
                        det['ocr_confidence'] = ocr_result['confidence']
                        det['ocr_metadata'] = ocr_result.get('ocr_metadata', {})
                        det['plate_id'] = plate_id
                        det['ocr_source'] = 'cached'
                    else:
                        # Only submit new OCR tasks for larger plates and if queue isn't full
                        crop = frame[max(0, y1):min(oh, y2), max(0, x1):min(ow, x2)].copy()
                        
                        if crop.size > 0:
                            # Only process OCR every 3rd plate detection to reduce load
                            if i % 3 == 0:  # Process every 3rd plate
                                ocr_submitted = submit_ocr_task(plate_id, crop, bbox)
                                if ocr_submitted:
                                    det['ocr_source'] = 'processing'
                                else:
                                    det['ocr_source'] = 'queue_full'
                            else:
                                det['ocr_source'] = 'skipped'
                        else:
                            det['ocr_source'] = 'invalid_crop'
                        
                        # Set default values while OCR processes
                        det['text'] = ""
                        det['ocr_confidence'] = 0.0
                        det['ocr_metadata'] = {}
                        det['plate_id'] = plate_id
                    
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
        
        # Print detailed smoke opacity information
        if smoke_dets:
            print(f"  [SMOKE OPACITY]")
            for i, det in enumerate(smoke_dets):
                opacity_level = det.get('opacity_level', 'unknown')
                opacity_score = det.get('opacity_score', 0.0)
                print(f"    Smoke {i+1}: {det['class']} | Confidence: {det['confidence']:.3f} | Opacity: {opacity_level} ({opacity_score:.3f})")
        
        print(f"  [DETECT] S:{len(smoke_dets)} V:{len(vehicle_dets)} P:{len(plate_dets)} {inference_time}ms")



# ── Main function ─────────────────────────────────────────────────────────────
def main():
    """Main application entry point"""
    print("[INFO] Starting video file detection system...")
    
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
    ocr_reader, ocr_type = load_ocr()
    
    # Create save directory (removed - inference only)
    print(f"[OK] Running inference-only mode (no frame saving)")
    
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
    
    # Start inference, OCR, and API worker threads
    threading.Thread(target=infer_worker, args=(models, ocr_reader, ocr_type), daemon=True).start()
    threading.Thread(target=ocr_worker, args=(ocr_reader, ocr_type), daemon=True).start()
    threading.Thread(target=api_worker, daemon=True).start()
    
    print("\n[READY] Processing video - Press 'q' to quit, 's' to save frame, SPACE to pause/resume\n")
    
    # Create the display window
    cv2.namedWindow('Video Detection System', cv2.WINDOW_AUTOSIZE)
    print("[INFO] Display window created")
    
    frame_count = 0
    paused = False
    frame = None  # Initialize frame variable
    
    try:
        while True:
            # Always read the next frame (for smooth video playback)
            if not paused:
                ret, frame = cap.read()
                if not ret:
                    print("[INFO] End of video reached")
                    break
                
                # Resize frame if needed
                if frame.shape[:2] != (HEIGHT, WIDTH):
                    frame = cv2.resize(frame, (WIDTH, HEIGHT))
                
                # Queue frame for inference only every INFER_EVERY frames
                if frame_count % INFER_EVERY == 0:
                    try:
                        _iqueue.put_nowait((frame.copy(), HEIGHT, WIDTH))
                    except queue.Full:
                        pass
                
                frame_count += 1
            
            # Always update display if we have a frame (for smooth video)
            if frame is not None:
                # Get current detections for display and merge OCR results
                with _dlock:
                    smoke_dets = list(_smoke)
                    vehicle_dets = list(_vehicle)
                    raw_plate_dets = list(_plates)
                
                # Merge OCR results into plate detections for display
                plate_dets = []
                for plate in raw_plate_dets:
                    plate_copy = plate.copy()
                    plate_id = plate.get('plate_id')
                    
                    if plate_id:
                        # Try to get OCR result from cache
                        with _ocr_lock:
                            if plate_id in _ocr_results:
                                ocr_result = _ocr_results[plate_id]
                                plate_copy['text'] = ocr_result['text']
                                plate_copy['ocr_confidence'] = ocr_result['confidence']
                                plate_copy['ocr_metadata'] = ocr_result.get('ocr_metadata', {})
                                plate_copy['ocr_source'] = 'completed'
                            else:
                                # OCR still processing or not started
                                if not plate_copy.get('text'):
                                    plate_copy['ocr_source'] = 'processing'
                    
                    plate_dets.append(plate_copy)
                
                # Create display frame (always create it, whether paused or not)
                display_frame = draw_boxes(frame.copy(), smoke_dets, vehicle_dets, plate_dets)
                
                # Add video progress info
                progress = (frame_count / total_frames) * 100 if total_frames > 0 else 0
                current_time = frame_count / video_fps if video_fps > 0 else 0
                cv2.putText(display_frame, f"Progress: {progress:.1f}% ({frame_count}/{total_frames}) {current_time:.1f}s", 
                           (10, HEIGHT - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                
                # Add pause indicator if paused
                if paused:
                    cv2.putText(display_frame, "PAUSED - Press SPACE to resume", 
                               (WIDTH//2 - 150, HEIGHT//2), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
                
                # Show frame
                cv2.imshow('Video Detection System', display_frame)
                
                # Send data to API at a slower rate for better OCR processing (every 30 frames)
                if frame_count % 30 == 0:
                    # Get current detections and merge OCR results
                    api_smoke_dets = list(smoke_dets)
                    api_vehicle_dets = list(vehicle_dets)
                    api_plate_dets = []
                    
                    # Only send to API if we have meaningful OCR results or no plates detected
                    has_meaningful_ocr = False
                    
                    print(f"[API] Frame {frame_count}: Checking {len(plate_dets)} plates for OCR results")
                    
                    # Merge OCR results into plate detections before sending to API
                    for plate in plate_dets:
                        plate_copy = plate.copy()
                        plate_id = plate.get('plate_id')
                        
                        if plate_id:
                            # Try to get OCR result from cache
                            with _ocr_lock:
                                if plate_id in _ocr_results:
                                    ocr_result = _ocr_results[plate_id]
                                    plate_copy['text'] = ocr_result['text']
                                    plate_copy['ocr_confidence'] = ocr_result['confidence']
                                    plate_copy['ocr_metadata'] = ocr_result.get('ocr_metadata', {})
                                    
                                    # Check if we have meaningful OCR results
                                    if ocr_result['text'] and ocr_result['confidence'] > 0.2:
                                        has_meaningful_ocr = True
                                        print(f"[API] Merged OCR result for {plate_id}: '{ocr_result['text']}' conf={ocr_result['confidence']:.3f}")
                                    else:
                                        print(f"[API] Low confidence OCR for {plate_id}: '{ocr_result['text']}' conf={ocr_result['confidence']:.3f}")
                                else:
                                    # OCR still processing, don't send to API yet
                                    print(f"[API] OCR still processing for {plate_id}, skipping API send")
                                    continue
                        
                        api_plate_dets.append(plate_copy)
                    
                    print(f"[API] Frame {frame_count}: S:{len(api_smoke_dets)} V:{len(api_vehicle_dets)} P:{len(api_plate_dets)} (meaningful_ocr: {has_meaningful_ocr})")
                    
                    # Only send to API if we have no plates or have meaningful OCR results
                    if len(plate_dets) == 0 or has_meaningful_ocr or len(api_plate_dets) == len(plate_dets):
                        # Always send the frame with detection boxes drawn for dashboard display
                        print(f"[API] Sending frame {frame_count} to API with {len(api_smoke_dets)} smoke, {len(api_vehicle_dets)} vehicles, {len(api_plate_dets)} plates")
                        submit_api_task(display_frame, api_smoke_dets, api_vehicle_dets, api_plate_dets, frame_count)
                    else:
                        print(f"[API] Waiting for OCR results before sending to API ({len(api_plate_dets)}/{len(plate_dets)} plates ready)")
            
            # Handle key presses (shorter wait for responsive controls)
            key = cv2.waitKey(1) & 0xFF  # Faster response for smooth video
            if key == ord('q'):
                break
            elif key == ord('s') and frame is not None:  # 's' to save current frame (only if frame exists)
                # Get current detections for saving and merge OCR results
                with _dlock:
                    smoke_dets = list(_smoke)
                    vehicle_dets = list(_vehicle)
                    raw_plate_dets = list(_plates)
                
                # Merge OCR results into plate detections
                plate_dets = []
                for plate in raw_plate_dets:
                    plate_copy = plate.copy()
                    plate_id = plate.get('plate_id')
                    
                    if plate_id:
                        # Try to get OCR result from cache
                        with _ocr_lock:
                            if plate_id in _ocr_results:
                                ocr_result = _ocr_results[plate_id]
                                plate_copy['text'] = ocr_result['text']
                                plate_copy['ocr_confidence'] = ocr_result['confidence']
                                plate_copy['ocr_metadata'] = ocr_result.get('ocr_metadata', {})
                    
                    plate_dets.append(plate_copy)
                
                display_frame = draw_boxes(frame.copy(), smoke_dets, vehicle_dets, plate_dets)
                saved = save_current_frame(display_frame, smoke_dets, vehicle_dets, plate_dets, frame_count)
                if saved:
                    print(f"[INFO] Frame {frame_count} saved manually")
                else:
                    print(f"[ERROR] Failed to save frame {frame_count}")
            elif key == ord(' '):  # Space bar to pause/resume
                paused = not paused
                print(f"[INFO] Video {'paused' if paused else 'resumed'}")
            elif key == ord('r'):  # 'r' to restart video
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                frame_count = 0
                print("[INFO] Video restarted")
            
            # Control video playback speed (only when not paused)
            if not paused:
                time.sleep(1.0 / 20.0)  # ~20 FPS playback speed for better OCR processing
            
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user")
    
    finally:
        print("[INFO] Cleaning up...")
        
        # Signal workers to stop
        try:
            _ocr_queue.put_nowait(None)
        except:
            pass
        
        try:
            _api_queue.put_nowait(None)
        except:
            pass
            
        cap.release()
        cv2.destroyAllWindows()
        
        # Print final statistics
        print(f"\n[STATS] Processed {frame_count} frames")
        with _dlock:
            print(f"[STATS] Final detections - S:{len(_smoke)} V:{len(_vehicle)} P:{len(_plates)}")
        with _ocr_lock:
            print(f"[STATS] OCR results processed: {len(_ocr_results)}")

if __name__ == '__main__':
    main()