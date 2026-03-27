"""
Camera streaming module - serves HLS stream
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from fastapi.responses import StreamingResponse, FileResponse
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
from database import insert_vehicle_detection_from_rpi, register_vehicle, create_violation

router = APIRouter(prefix="/api/stream", tags=["stream"])

class StreamManager:
    def __init__(self):
        self.latest_frame = None
        self.frame_buffer = deque(maxlen=60)  # Increased from 30 to 60 frames
        self.latest_metadata = None  # Store latest detection metadata
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
        
        # Filter for vehicle and license plate detections
        vehicle_detections = []
        license_plates = []
        smoke_detected = False
        
        for detection in detections:
            class_name = detection.get('class_name', '').lower()
            confidence = detection.get('confidence', 0.0)
            
            # Check for smoke detection
            if 'smoke' in class_name:
                smoke_detected = True
            
            # Check for vehicle detection
            elif class_name in ['passenger', 'puv', 'services', 'two_wheel', 'vehicle']:
                vehicle_detections.append(detection)
            
            # Check for license plate detection
            elif 'license' in class_name or 'plate' in class_name:
                license_plates.append(detection)
        
        # Always save detection data to database (even if no detections for monitoring)
        print(f"[DETECTION] Processing {len(vehicle_detections)} vehicles, {len(license_plates)} plates, smoke: {smoke_detected}")
        
        # Save to database using the existing function
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
            
            # Create violations for vehicles with smoke
            if smoke_detected and vehicle_detections:
                await create_smoke_violations(vehicle_detections, location, timestamp_dt)
            
    except Exception as e:
        print(f"[ERROR] Processing detections: {e}")
        import traceback
        traceback.print_exc()

async def create_smoke_violations(vehicle_detections: list, location: str, timestamp: datetime):
    """Create violations for vehicles detected with smoke"""
    try:
        for vehicle in vehicle_detections:
            # Generate a mock license plate for now (in real system, this would come from OCR)
            vehicle_type = vehicle.get('class_name', 'unknown')
            confidence = vehicle.get('confidence', 0.0)
            
            # Generate mock license plate based on vehicle type and timestamp
            plate_suffix = str(timestamp.minute).zfill(2) + str(timestamp.second).zfill(2)
            if vehicle_type == 'passenger':
                license_plate = f"ABC-{plate_suffix}"
            elif vehicle_type == 'puv':
                license_plate = f"PUV-{plate_suffix}"
            elif vehicle_type == 'services':
                license_plate = f"SVC-{plate_suffix}"
            elif vehicle_type == 'two_wheel':
                license_plate = f"MC-{plate_suffix}"
            else:
                license_plate = f"VEH-{plate_suffix}"
            
            print(f"[VIOLATION] Creating smoke violation for {license_plate} ({vehicle_type})")
            
            # Register vehicle
            vehicle_record = register_vehicle(license_plate, vehicle_type)
            
            if vehicle_record:
                # Create violation
                violation = create_violation(
                    vehicle_id=vehicle_record['id'],
                    detection_id=None,
                    violation_type="smoke_emission",
                    severity="warning" if confidence < 0.7 else "critical",
                    description=f"Smoke detected from {vehicle_type} at {location} (confidence: {confidence:.2f})"
                )
                
                if violation:
                    print(f"[VIOLATION] Created violation ID={violation['id']} for {license_plate}")
                
    except Exception as e:
        print(f"[ERROR] Creating smoke violations: {e}")

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
            # Check if we have detection counts and create detection objects
            smoke_count = latest_metadata.get('smoke_count', 0)
            vehicle_count = latest_metadata.get('vehicle_count', 0) 
            plate_count = latest_metadata.get('plate_count', 0)
            
            # Create mock detection objects based on counts for compatibility
            detections = []
            for i in range(smoke_count):
                detections.append({"class": "smoke_black", "conf": 0.75})
            for i in range(vehicle_count):
                detections.append({"class": "passenger", "conf": 0.85})
            for i in range(plate_count):
                detections.append({"class": "license_plate", "conf": 0.90})
        
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


# ============ HLS PROXY ENDPOINTS ============

import requests

@router.get("/hls-proxy")
def hls_proxy():
    """Proxy HLS stream from RPi over HTTPS"""
    rpi_ip = os.getenv('RPI_IP', '192.168.1.35')
    hls_url = f"http://{rpi_ip}:8000/stream.m3u8"
    
    try:
        print(f"[HLS PROXY] Fetching from {hls_url}")
        response = requests.get(hls_url, timeout=5)
        response.raise_for_status()
        print(f"[HLS PROXY] Success: {len(response.content)} bytes")
        
        return StreamingResponse(
            iter([response.content]),
            media_type="application/vnd.apple.mpegurl",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-cache, no-store, must-revalidate"
            }
        )
    except requests.exceptions.Timeout:
        print(f"[HLS PROXY] Timeout connecting to {hls_url}")
        raise HTTPException(status_code=504, detail="RPi stream timeout")
    except requests.exceptions.ConnectionError as e:
        print(f"[HLS PROXY] Connection error: {e}")
        raise HTTPException(status_code=503, detail="Cannot reach RPi stream")
    except Exception as e:
        print(f"[HLS PROXY] Error: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to fetch HLS stream: {str(e)}")

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