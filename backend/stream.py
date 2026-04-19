"""
Camera streaming module - serves frame-based stream
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from fastapi.responses import StreamingResponse, FileResponse, Response
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
from database import insert_vehicle_detection_from_rpi, register_vehicle, create_violation, create_notification
from image_cropper import DetectionImageCropper
from frame_storage import frame_storage

# Import report generator
from report_generator import SMOKiReportGenerator

router = APIRouter(prefix="/api/stream", tags=["stream"])

class StreamManager:
    def __init__(self):
        self.latest_frame = None
        self.frame_buffer = deque(maxlen=30)  # Reduced buffer size for faster updates
        self.latest_metadata = None  # Store latest detection metadata
        self.latest_detections = []  # Store latest detections
        self.latest_violations = []  # Store latest violations
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
                    # Extract detections and violations from metadata
                    self.latest_detections = metadata.get('detections', [])
                    self.latest_violations = metadata.get('violations', [])
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
    
    def get_latest_violations(self):
        """Get latest violations"""
        with self.lock:
            return self.latest_violations.copy() if self.latest_violations else []
    
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
        
        # Count detection types for logging
        vehicle_count = sum(1 for d in detections if d.get('class_name', '').lower() in ['passenger', 'puv', 'services', 'two_wheel', 'vehicle'])
        plate_count = sum(1 for d in detections if 'license' in d.get('class_name', '').lower() or 'plate' in d.get('class_name', '').lower())
        smoke_count = sum(1 for d in detections if 'smoke' in d.get('class_name', '').lower())
        
        print(f"[DETECTION] Processing {vehicle_count} vehicles, {plate_count} plates, {smoke_count} smoke detections")
        
        # Save frame locally for later retrieval
        frame_path = frame_storage.save_detection_frame(
            frame_data=frame_data,
            timestamp=timestamp_dt,
            detections=detections,
            metadata=metadata
        )
        
        if frame_path:
            print(f"[FRAME_STORAGE] Saved detection frame: {os.path.basename(frame_path)}")
        
        # Always save detection data to database (even if no detections for monitoring)
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
            detection_id = result['id']  # Store detection ID for linking violations
            
            # Check if violations are already provided by laptop_snap.py
            provided_violations = metadata.get('violations', [])
            
            if provided_violations:
                print(f"[VIOLATION] Found {len(provided_violations)} pre-detected violations from laptop_snap.py")
                # Process violations that were already detected by laptop_snap.py
                await process_laptop_snap_violations(provided_violations, location, timestamp_dt, frame_data, detection_id)
            elif smoke_count > 0:
                print(f"[VIOLATION] No pre-detected violations, using backend detection logic")
                # Fall back to backend violation detection (creates PENDING violations)
                await create_targeted_violations(detections, location, timestamp_dt, frame_data, detection_id)
            
    except Exception as e:
        print(f"[ERROR] Processing detections: {e}")
        import traceback
        traceback.print_exc()

async def process_laptop_snap_violations(violations: list, location: str, timestamp: datetime, frame_data: bytes, detection_id: int):
    """Process violations that were already detected by laptop_snap.py - create as APPROVED"""
    try:
        print(f"[LAPTOP_SNAP] Processing {len(violations)} pre-detected violations")
        
        for i, violation in enumerate(violations):
            license_plate = violation.get('license_plate', 'UNKNOWN')
            vehicle_type = violation.get('vehicle_type', 'unknown')
            smoke_type = violation.get('smoke_type', 'smoke')
            distance = violation.get('distance', 0)
            has_readable_plate = violation.get('has_readable_plate', False)
            vehicle_confidence = violation.get('vehicle_confidence', 0.0)
            smoke_confidence = violation.get('smoke_confidence', 0.0)
            ocr_confidence = violation.get('ocr_confidence', 0.0)
            
            print(f"[LAPTOP_SNAP] Violation {i+1}: {license_plate} ({vehicle_type}) - {distance:.1f}px from {smoke_type}")
            
            # Register vehicle in database
            vehicle_record = register_vehicle(license_plate, vehicle_type)
            
            if vehicle_record:
                # Create PENDING violation (auto_approve=False for user approval)
                violation_record = create_violation(
                    vehicle_id=vehicle_record['id'],
                    detection_id=detection_id,
                    violation_type="smoke_emission",
                    severity="warning" if smoke_confidence < 0.7 else "critical",
                    description=f"Smoke emission violation detected by laptop_snap.py: {vehicle_type} {license_plate} at {location}. Smoke detected {distance:.1f}px from vehicle (confidence: {smoke_confidence:.2f}). {'License plate readable' if has_readable_plate else 'License plate unreadable'} (OCR confidence: {ocr_confidence:.2f}).",
                    auto_approve=False  # Require user approval for laptop_snap violations
                )
                
                if violation_record:
                    print(f"[LAPTOP_SNAP] ✅ Created PENDING violation ID={violation_record['id']} for {license_plate} - requires user approval")
                    
                    # Check if evidence file exists and copy it to backend
                    evidence_path = violation.get('evidence_path')
                    if evidence_path and os.path.exists(evidence_path):
                        try:
                            # Copy evidence file to backend detection_frames directory
                            import shutil
                            backend_evidence_dir = "backend/detection_frames"
                            os.makedirs(backend_evidence_dir, exist_ok=True)
                            
                            evidence_filename = os.path.basename(evidence_path)
                            backend_evidence_path = os.path.join(backend_evidence_dir, evidence_filename)
                            
                            shutil.copy2(evidence_path, backend_evidence_path)
                            print(f"[LAPTOP_SNAP] 📸 Copied evidence: {evidence_path} → {backend_evidence_path}")
                            
                        except Exception as copy_error:
                            print(f"[LAPTOP_SNAP] ⚠️ Could not copy evidence file: {copy_error}")
                    
                    # Create approval notification for pending violation - skip for test plates
                    if license_plate not in ['ABC123', 'TEST123', 'DEMO123', 'SAMPLE123']:
                        notification = create_notification(
                            violation_id=violation_record['id'],
                            title=f"Violation Detected: {license_plate}",
                            message=f"Smoke emission detected from {vehicle_type} {license_plate} at {location}. Distance: {distance:.1f}px. Evidence available for review. Please approve/reject this violation.",
                            notification_type="violation_approval"
                        )
                        
                        if notification:
                            print(f"[LAPTOP_SNAP] 📢 Created approval notification ID={notification['id']} for {license_plate}")
                    else:
                        print(f"[LAPTOP_SNAP] Skipped notification for test plate: {license_plate}")
                else:
                    print(f"[LAPTOP_SNAP] ❌ Failed to create violation for {license_plate}")
            else:
                print(f"[LAPTOP_SNAP] ❌ Failed to register vehicle {license_plate}")
        
        print(f"[LAPTOP_SNAP] ✅ Processed {len(violations)} violations from laptop_snap.py")
        
    except Exception as e:
        print(f"[ERROR] Processing laptop_snap violations: {e}")
        import traceback
        traceback.print_exc()


async def create_targeted_violations(detections: list, location: str, timestamp: datetime, frame_data: bytes, detection_id: int):
    """Create violations only for vehicles that have both smoke detection and readable license plates"""
    try:
        # Initialize image cropper
        cropper = DetectionImageCropper(padding_pixels=50)
        
        # Group detections by type
        smoke_detections = []
        vehicle_detections = []
        plate_detections = []
        
        for detection in detections:
            class_name = detection.get('class_name', '').lower()
            
            if 'smoke' in class_name:
                smoke_detections.append(detection)
            elif class_name in ['passenger', 'puv', 'services', 'two_wheel', 'vehicle']:
                vehicle_detections.append(detection)
            elif 'license' in class_name or 'plate' in class_name:
                plate_detections.append(detection)
        
        print(f"[VIOLATION] Found {len(smoke_detections)} smoke, {len(vehicle_detections)} vehicles, {len(plate_detections)} plates")
        
        # Only create violations if we have smoke detections
        if not smoke_detections:
            print(f"[VIOLATION] No smoke detected - no violations created")
            return
        
        # Only create violations if we have readable license plates
        if not plate_detections:
            print(f"[VIOLATION] No license plates detected - no violations created")
            return
        
        # Find readable license plates with good OCR confidence
        readable_plates = []
        
        for plate in plate_detections:
            plate_text = plate.get('plate_text', '').strip()
            ocr_confidence = plate.get('ocr_confidence', 0.0)
            
            print(f"[VIOLATION] Processing plate: '{plate_text}' (confidence: {ocr_confidence:.2f})")
            
            # Only consider plates with meaningful text and reasonable OCR confidence
            if (plate_text and 
                len(plate_text) >= 2 and  # Reduced from 3 to 2 characters
                ocr_confidence >= 0.05 and  # Reduced from 0.5 to 0.05 for more realistic threshold
                any(c.isalnum() for c in plate_text) and  # Contains alphanumeric characters
                not plate_text.startswith('UNREAD') and 
                not plate_text.startswith('UNKNOWN') and 
                not plate_text.startswith('PLACEHOLDER') and
                not all(c in '?-_. ' for c in plate_text)):  # Not all special chars
                
                readable_plates.append({
                    'plate_text': plate_text,
                    'ocr_confidence': ocr_confidence,
                    'bbox': plate.get('bbox', []),
                    'ocr_metadata': plate.get('ocr_metadata', {}),
                    'plate_detection': plate
                })
                print(f"[VIOLATION] ✅ Found readable plate: {plate_text} (confidence: {ocr_confidence:.2f})")
            else:
                print(f"[VIOLATION] ❌ Skipping plate: '{plate_text}' (confidence: {ocr_confidence:.2f}) - not readable enough")
        
        # If no readable plates found, create OCR failure notification for manual review
        if not readable_plates:
            print(f"[VIOLATION] No readable license plates found - creating OCR failure notification")
            
            # Count vehicles detected
            vehicle_count = len([d for d in detections if d.get('class_name', '').lower() in ['passenger', 'puv', 'service', 'two_wheel']])
            
            # Create OCR failure notification for manual review
            if vehicle_count > 0:
                ocr_notification = create_notification(
                    violation_id=None,  # No violation created yet
                    title="OCR Detection Issue",
                    message=f"Smoke emission detected with {vehicle_count} vehicle(s) at {location}, but no license plates could be read clearly. This may indicate OCR failure or poor image quality. Manual review recommended.",
                    notification_type="ocr_failure"
                )
                
                if ocr_notification:
                    print(f"[VIOLATION] 📢 Created OCR failure notification ID={ocr_notification['id']} for manual review")
            
            return
        
        # Create violations only for readable license plates
        # Match each smoke detection to the closest vehicle with a readable plate
        violating_vehicles = []
        
        print(f"[VIOLATION] Starting spatial matching for {len(smoke_detections)} smoke detection(s)")
        
        for i, smoke in enumerate(smoke_detections):
            smoke_bbox = smoke.get('bbox', {})
            smoke_center_x = (smoke_bbox.get('x1', 0) + smoke_bbox.get('x2', 0)) / 2
            smoke_center_y = (smoke_bbox.get('y1', 0) + smoke_bbox.get('y2', 0)) / 2
            
            print(f"[VIOLATION] Smoke {i+1}: center=({smoke_center_x:.1f}, {smoke_center_y:.1f}), confidence={smoke.get('confidence', 0):.2f}")
            
            # Find the closest vehicle to this smoke detection
            closest_vehicle = None
            closest_distance = float('inf')
            
            print(f"[VIOLATION] Checking {len(vehicle_detections)} vehicles for proximity to smoke {i+1}:")
            
            for j, vehicle in enumerate(vehicle_detections):
                vehicle_bbox = vehicle.get('bbox', {})
                vehicle_center_x = (vehicle_bbox.get('x1', 0) + vehicle_bbox.get('x2', 0)) / 2
                vehicle_center_y = (vehicle_bbox.get('y1', 0) + vehicle_bbox.get('y2', 0)) / 2
                
                # Calculate distance between smoke and vehicle centers
                distance = ((smoke_center_x - vehicle_center_x) ** 2 + (smoke_center_y - vehicle_center_y) ** 2) ** 0.5
                
                print(f"[VIOLATION]   Vehicle {j+1} ({vehicle.get('class_name', 'unknown')}): center=({vehicle_center_x:.1f}, {vehicle_center_y:.1f}), distance={distance:.1f}px")
                
                if distance < closest_distance:
                    closest_distance = distance
                    closest_vehicle = vehicle
            
            print(f"[VIOLATION] → Closest vehicle to smoke {i+1}: {closest_vehicle.get('class_name', 'unknown') if closest_vehicle else 'none'} at {closest_distance:.1f}px")
            
            # Only create violation if vehicle is reasonably close to smoke (within 200 pixels)
            if closest_vehicle and closest_distance < 200:
                print(f"[VIOLATION] ✅ Vehicle is close enough ({closest_distance:.1f}px < 200px), looking for license plate...")
                
                # Find a readable license plate near this vehicle
                closest_plate = None
                closest_plate_distance = float('inf')
                
                vehicle_bbox = closest_vehicle.get('bbox', {})
                vehicle_center_x = (vehicle_bbox.get('x1', 0) + vehicle_bbox.get('x2', 0)) / 2
                vehicle_center_y = (vehicle_bbox.get('y1', 0) + vehicle_bbox.get('y2', 0)) / 2
                
                print(f"[VIOLATION] Checking {len(readable_plates)} readable plates for proximity to vehicle:")
                
                for k, plate_info in enumerate(readable_plates):
                    plate_bbox = plate_info.get('bbox', {})
                    plate_center_x = (plate_bbox.get('x1', 0) + plate_bbox.get('x2', 0)) / 2
                    plate_center_y = (plate_bbox.get('y1', 0) + plate_bbox.get('y2', 0)) / 2
                    
                    # Calculate distance between vehicle and plate
                    plate_distance = ((vehicle_center_x - plate_center_x) ** 2 + (vehicle_center_y - plate_center_y) ** 2) ** 0.5
                    
                    print(f"[VIOLATION]   Plate {k+1} ({plate_info['plate_text']}): center=({plate_center_x:.1f}, {plate_center_y:.1f}), distance={plate_distance:.1f}px")
                    
                    if plate_distance < closest_plate_distance:
                        closest_plate_distance = plate_distance
                        closest_plate = plate_info
                
                print(f"[VIOLATION] → Closest plate to vehicle: {closest_plate['plate_text'] if closest_plate else 'none'} at {closest_plate_distance:.1f}px")
                
                # Only create violation if plate is close to the vehicle (within 150 pixels)
                if closest_plate and closest_plate_distance < 150:
                    # Check if we already have a violation for this plate (avoid duplicates)
                    plate_text = closest_plate['plate_text']
                    already_added = any(v['license_plate'] == plate_text for v in violating_vehicles)
                    
                    if not already_added:
                        vehicle_type = closest_vehicle.get('class_name', 'unknown')
                        vehicle_confidence = closest_vehicle.get('confidence', 0.0)
                        
                        violating_vehicles.append({
                            'license_plate': plate_text,
                            'vehicle_type': vehicle_type,
                            'confidence': vehicle_confidence,
                            'ocr_confidence': closest_plate['ocr_confidence'],
                            'smoke_confidence': smoke.get('confidence', 0.0),
                            'ocr_metadata': closest_plate['ocr_metadata'],
                            'vehicle_bbox': closest_vehicle.get('bbox', []),
                            'plate_bbox': closest_plate['bbox'],
                            'smoke_bbox': smoke.get('bbox', []),
                            'smoke_vehicle_distance': closest_distance,
                            'vehicle_plate_distance': closest_plate_distance
                        })
                        
                        print(f"[VIOLATION] ✅ VIOLATION CREATED: {plate_text} ({vehicle_type}) - Smoke→Vehicle: {closest_distance:.1f}px, Vehicle→Plate: {closest_plate_distance:.1f}px")
                    else:
                        print(f"[VIOLATION] ❌ Duplicate violation avoided for {plate_text}")
                else:
                    if closest_plate:
                        print(f"[VIOLATION] ❌ Plate too far from vehicle ({closest_plate_distance:.1f}px > 150px) - no violation for {closest_plate['plate_text']}")
                    else:
                        print(f"[VIOLATION] ❌ No readable plates found near vehicle - no violation created")
            else:
                if closest_vehicle:
                    print(f"[VIOLATION] ❌ Vehicle too far from smoke ({closest_distance:.1f}px > 200px) - no violation for {closest_vehicle.get('class_name', 'unknown')}")
                else:
                    print(f"[VIOLATION] ❌ No vehicles found - no violation created")
        
        print(f"[VIOLATION] Spatial matching complete. {len(violating_vehicles)} violation(s) will be created.")
        
        if not violating_vehicles:
            print(f"[VIOLATION] ❌ Smoke detected but no vehicles with readable plates found nearby - no violations created")
            return
        
        # Create PENDING violations for vehicles with readable license plates
        for violator in violating_vehicles:
            print(f"[VIOLATION] Creating PENDING smoke violation for {violator['license_plate']} ({violator['vehicle_type']})")
            
            # Register vehicle (but don't increment violation count yet)
            vehicle_record = register_vehicle(violator['license_plate'], violator['vehicle_type'])
            
            if vehicle_record:
                # Create PENDING violation (auto_approve=False)
                violation = create_violation(
                    vehicle_id=vehicle_record['id'],
                    detection_id=detection_id,
                    violation_type="smoke_emission",
                    severity="warning" if violator['smoke_confidence'] < 0.7 else "critical",
                    description=f"Smoke emission violation: {violator['vehicle_type']} {violator['license_plate']} at {location}. Smoke detected {violator.get('smoke_vehicle_distance', 0):.1f}px from vehicle (confidence: {violator['smoke_confidence']:.2f}), license plate read with {violator['ocr_confidence']:.2f} confidence.",
                    auto_approve=False  # Requires user approval
                )
                
                if violation:
                    print(f"[VIOLATION] Created PENDING violation ID={violation['id']} for {violator['license_plate']}")
                    
                    # Crop the vehicle image for evidence
                    try:
                        # Prepare detections for cropping (include the specific vehicle, its smoke, and plate)
                        crop_detections = []
                        
                        # Add the violating vehicle
                        if violator['vehicle_bbox']:
                            crop_detections.append({
                                'class_name': violator['vehicle_type'],
                                'confidence': violator['confidence'],
                                'bbox': violator['vehicle_bbox']
                            })
                        
                        # Add the specific smoke detection that caused this violation
                        if violator.get('smoke_bbox'):
                            crop_detections.append({
                                'class_name': 'smoke',
                                'confidence': violator['smoke_confidence'],
                                'bbox': violator['smoke_bbox']
                            })
                        
                        # Add the license plate
                        if violator['plate_bbox']:
                            crop_detections.append({
                                'class_name': 'license_plate',
                                'confidence': violator['ocr_confidence'],
                                'bbox': violator['plate_bbox']
                            })
                        
                        # Crop the violation evidence
                        crop_result = cropper.crop_detection_image(
                            image_data=frame_data,
                            detections=crop_detections,
                            timestamp=timestamp,
                            violation_id=str(violation['id'])
                        )
                        
                        if crop_result['success']:
                            print(f"[CROP] Successfully cropped violation evidence for {violator['license_plate']} (smoke-vehicle distance: {violator.get('smoke_vehicle_distance', 0):.1f}px)")
                            print(f"[CROP] Cropped image: {crop_result['cropped_frame_path']}")
                        else:
                            print(f"[CROP] Failed to crop violation evidence: {crop_result.get('error', 'Unknown error')}")
                    
                    except Exception as crop_error:
                        print(f"[CROP ERROR] Failed to crop vehicle image: {crop_error}")
                    
                    # Create notification for user approval (only for real violations)
                    # Skip notification for test plates
                    if violator['license_plate'] not in ['ABC123', 'TEST123', 'DEMO123', 'SAMPLE123']:
                        notification = create_notification(
                            violation_id=violation['id'],
                            title=f"Violation Detected: {violator['license_plate']}",
                            message=f"Smoke emission detected from {violator['vehicle_type']} {violator['license_plate']} at {location}. OCR confidence: {violator['ocr_confidence']:.2f}. Vehicle image cropped for review. Please approve/reject this violation.",
                            notification_type="violation_approval"
                        )
                        
                        if notification:
                            print(f"[NOTIFICATION] Created approval notification ID={notification['id']} for {violator['license_plate']}")
                    else:
                        print(f"[NOTIFICATION] Skipped notification for test plate: {violator['license_plate']}")
        
        if not violating_vehicles:
            print(f"[VIOLATION] Smoke detected but no vehicles with readable license plates - no violations created")
                
    except Exception as e:
        print(f"[ERROR] Creating targeted violations: {e}")
        import traceback
        traceback.print_exc()

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
                
                # Handle both old and new metadata formats
                # New format: nested under 'summary'
                summary = meta_data.get('summary', {})
                detections_count = summary.get('total_detections', 0)
                smoke_count = summary.get('smoke_detections', 0)
                vehicle_count = summary.get('vehicle_detections', 0)
                
                # Old format: direct keys (current RPi format)
                if detections_count == 0:
                    smoke_count = meta_data.get('smoke_count', 0)
                    vehicle_count = meta_data.get('vehicle_count', 0)
                    plate_count = meta_data.get('plate_count', 0)
                    detections_count = smoke_count + vehicle_count + plate_count
                
                print(f"[FRAME] Metadata: {meta_data.get('camera_id', 'unknown')} - {detections_count} total, {smoke_count} smoke, {vehicle_count} vehicles")
                
                # Log the actual detections array if present
                detections = meta_data.get('detections', [])
                if detections:
                    print(f"[FRAME] Detections array: {len(detections)} objects")
                    for i, det in enumerate(detections[:3]):  # Log first 3
                        print(f"  {i+1}. {det.get('class', 'unknown')} conf={det.get('conf', 0):.2f}")
                
                # Process detections and save to database
                await process_detections(frame_data, meta_data)
                
            except Exception as e:
                print(f"[FRAME] Metadata parse error: {e}")
                import traceback
                traceback.print_exc()
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
        # Handle both old and new metadata formats
        detections = latest_metadata.get("detections", [])
        
        # If no detections in new format, try to extract from old format
        if not detections:
            # Check if we have detection counts and create basic detection info
            smoke_count = latest_metadata.get('smoke_count', 0)
            vehicle_count = latest_metadata.get('vehicle_count', 0) 
            plate_count = latest_metadata.get('plate_count', 0)
            
            # Create basic detection info based on counts (no mock data)
            detections = []
            if smoke_count > 0:
                detections.append({"type": "smoke", "count": smoke_count})
            if vehicle_count > 0:
                detections.append({"type": "vehicle", "count": vehicle_count})
            if plate_count > 0:
                detections.append({"type": "plate", "count": plate_count})
        
        status_data["latest_detections"] = detections
        
        # Handle summary data
        summary = latest_metadata.get("summary", {})
        if not summary and latest_metadata:
            # Create summary from direct counts if new format not available
            summary = {
                "total_detections": latest_metadata.get('smoke_count', 0) + 
                                  latest_metadata.get('vehicle_count', 0) + 
                                  latest_metadata.get('plate_count', 0),
                "smoke_detections": latest_metadata.get('smoke_count', 0),
                "vehicle_detections": latest_metadata.get('vehicle_count', 0),
                "plate_detections": latest_metadata.get('plate_count', 0)
            }
        
        status_data["detection_summary"] = summary
        status_data["camera_info"] = {
            "camera_id": latest_metadata.get("camera_id"),
            "location": latest_metadata.get("location") or latest_metadata.get("camera_location"),
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


# ============ DEBUG ENDPOINTS ============

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

@router.get("/plate-events")
async def get_plate_events_endpoint(limit: int = 50):
    """Get recent license plate OCR events from database"""
    try:
        from database import get_plate_events
        events = get_plate_events(limit)
        return {
            "success": True,
            "data": events,
            "count": len(events)
        }
    except Exception as e:
        print(f"[PLATE] Error fetching plate events: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate-report")
async def generate_detection_report(request_data: dict):
    """Generate HTML report with current frame and detection data"""
    try:
        report_type = request_data.get("report_type", "general")
        violation_id = request_data.get("violation_id")
        vehicle_data = request_data.get("vehicle_data")
        detection_timestamp = request_data.get("detection_timestamp")
        detection_data = request_data.get("detection_data")
        
        print(f"[REPORT] Generating {report_type} report...")
        if violation_id:
            print(f"[REPORT] Violation ID: {violation_id}")
        if vehicle_data:
            print(f"[REPORT] Vehicle data: {vehicle_data.get('plate', 'Unknown')}")
        if detection_timestamp:
            print(f"[REPORT] Detection timestamp: {detection_timestamp}")
        
        # Initialize report generator
        generator = SMOKiReportGenerator()
        
        # Generate report
        result = generator.generate_report(report_type, violation_id, vehicle_data, detection_timestamp, detection_data)
        
        if result['success']:
            print(f"[REPORT] Report generated successfully: {result['report_id']}")
            return {
                "success": True,
                "report_id": result['report_id'],
                "report_path": result['report_path'],
                "timestamp": result['timestamp'],
                "detection_summary": result.get('detection_summary', {}),
                "violation_id": violation_id,
                "detection_timestamp": detection_timestamp,
                "message": "Report generated successfully"
            }
        else:
            print(f"[REPORT] Report generation failed: {result['error']}")
            raise HTTPException(status_code=500, detail=result['error'])
            
    except Exception as e:
        print(f"[REPORT] Error generating report: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/reports/{report_id}")
async def serve_report(report_id: str):
    """Serve generated HTML report for viewing"""
    try:
        reports_dir = Path("reports")
        report_path = reports_dir / f"{report_id}.html"
        
        if not report_path.exists():
            raise HTTPException(status_code=404, detail="Report not found")
        
        # Read and return HTML content for inline viewing
        with open(report_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        return Response(
            content=html_content,
            media_type="text/html",
            headers={
                "Content-Disposition": "inline",
                "Cache-Control": "no-cache"
            }
        )
    except Exception as e:
        print(f"[REPORT] Error serving report: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/reports/{report_id}/download")
async def download_report(report_id: str):
    """Download HTML report as file"""
    try:
        reports_dir = Path("reports")
        report_path = reports_dir / f"{report_id}.html"
        
        if not report_path.exists():
            raise HTTPException(status_code=404, detail="Report not found")
        
        return FileResponse(
            path=str(report_path),
            media_type="text/html",
            filename=f"{report_id}.html",
            headers={
                "Content-Disposition": f"attachment; filename={report_id}.html"
            }
        )
    except Exception as e:
        print(f"[REPORT] Error downloading report: {e}")
        raise HTTPException(status_code=500, detail=str(e))
@router.get("/violation-evidence/{violation_id}")
async def get_violation_evidence(violation_id: str):
    """
    Get cropped vehicle evidence for a specific violation
    """
    try:
        cropper = DetectionImageCropper()
        
        # Look for cropped image files for this violation
        cropped_frames_dir = cropper.cropped_frames_dir
        
        # Find files matching the violation ID
        violation_files = []
        if os.path.exists(cropped_frames_dir):
            for filename in os.listdir(cropped_frames_dir):
                if f"violation_{violation_id}_" in filename:
                    violation_files.append(filename)
        
        if not violation_files:
            raise HTTPException(status_code=404, detail="No evidence found for this violation")
        
        # Find the cropped image
        cropped_image = None
        metadata_file = None
        
        for filename in violation_files:
            if filename.endswith('_CROPPED.jpg'):
                cropped_image = filename
            elif filename.endswith('_METADATA.json'):
                metadata_file = filename
        
        if not cropped_image:
            raise HTTPException(status_code=404, detail="Cropped evidence image not found")
        
        cropped_path = os.path.join(cropped_frames_dir, cropped_image)
        
        if not os.path.exists(cropped_path):
            raise HTTPException(status_code=404, detail="Evidence image file not found")
        
        # Return the cropped image
        return FileResponse(
            path=cropped_path,
            media_type="image/jpeg",
            filename=f"violation_{violation_id}_evidence.jpg"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving violation evidence: {str(e)}")

@router.get("/violation-metadata/{violation_id}")
async def get_violation_metadata(violation_id: str):
    """
    Get metadata for violation evidence
    """
    try:
        cropper = DetectionImageCropper()
        cropped_frames_dir = cropper.cropped_frames_dir
        
        # Find metadata file
        metadata_file = None
        if os.path.exists(cropped_frames_dir):
            for filename in os.listdir(cropped_frames_dir):
                if f"violation_{violation_id}_" in filename and filename.endswith('_METADATA.json'):
                    metadata_file = filename
                    break
        
        if not metadata_file:
            raise HTTPException(status_code=404, detail="Metadata not found for this violation")
        
        metadata_path = os.path.join(cropped_frames_dir, metadata_file)
        
        if not os.path.exists(metadata_path):
            raise HTTPException(status_code=404, detail="Metadata file not found")
        
        # Read and return metadata
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        
        return {
            "success": True,
            "violation_id": violation_id,
            "metadata": metadata
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving violation metadata: {str(e)}")