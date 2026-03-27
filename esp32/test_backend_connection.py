#!/usr/bin/env python3
"""
Test script to verify backend connection and send test detection data
Usage: python test_backend_connection.py
"""

import requests
import json
import time
from datetime import datetime, timezone
import cv2
import numpy as np

BACKEND_URL = "https://smoki-backend-rpi.onrender.com"

def test_backend_status():
    """Test if backend is responding"""
    print("🔍 Testing backend status...")
    try:
        response = requests.get(f"{BACKEND_URL}/api/stream/status", timeout=10)
        print(f"✅ Backend status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Status: {data.get('status')}")
            print(f"   FPS: {data.get('fps')}")
            print(f"   Buffered frames: {data.get('buffered_frames')}")
            print(f"   Latest detections: {len(data.get('latest_detections', []))}")
            return True
    except Exception as e:
        print(f"❌ Backend connection failed: {e}")
        return False

def send_test_frame():
    """Send a test frame with mock detection data"""
    print("📤 Sending test frame with mock detections...")
    
    # Create a simple test image
    test_image = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(test_image, "TEST FRAME", (200, 240), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 3)
    
    # Encode as JPEG
    _, jpg_buffer = cv2.imencode('.jpg', test_image, [cv2.IMWRITE_JPEG_QUALITY, 85])
    
    # Create test detection metadata
    timestamp = datetime.now(timezone.utc).isoformat()
    
    test_detections = [
        {
            "class": "passenger",
            "conf": 0.85,
            "bbox": {"x1": 100, "y1": 100, "x2": 200, "y2": 200}
        },
        {
            "class": "smoke_black", 
            "conf": 0.75,
            "bbox": {"x1": 300, "y1": 150, "x2": 400, "y2": 250}
        }
    ]
    
    metadata = {
        "camera_id": "test_camera",
        "location": "Test Location",
        "timestamp": timestamp,
        "has_detection": True,
        "is_violation": True,
        "detections": test_detections,
        "plates": [],
        "summary": {
            "total_detections": 2,
            "smoke_detections": 1,
            "vehicle_detections": 1,
            "plate_detections": 0,
            "plates_with_text": 0,
            "face_count": 0,
            "inference_time_ms": 55,
            "frame_size_bytes": len(jpg_buffer),
            "violation_detected": True,
            "smoke_opacity_levels": {
                "thin": 0,
                "moderate": 1,
                "dense": 0
            }
        }
    }
    
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/stream/frame",
            files={"frame": ("test_frame.jpg", jpg_buffer.tobytes(), "image/jpeg")},
            data={"metadata": json.dumps(metadata)},
            timeout=15
        )
        
        if response.status_code in (200, 201):
            result = response.json()
            print(f"✅ Test frame sent successfully")
            print(f"   FPS: {result.get('fps')}")
            print(f"   Buffered frames: {result.get('buffered_frames')}")
            return True
        else:
            print(f"❌ Failed to send test frame: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error sending test frame: {e}")
        return False

def verify_detection_data():
    """Verify the test detection data appears in status"""
    print("🔍 Verifying detection data in backend...")
    time.sleep(2)  # Wait for backend to process
    
    try:
        response = requests.get(f"{BACKEND_URL}/api/stream/status", timeout=10)
        if response.status_code == 200:
            data = response.json()
            detections = data.get('latest_detections', [])
            
            if detections:
                print(f"✅ Found {len(detections)} detections in backend:")
                for i, det in enumerate(detections):
                    class_name = det.get('class', det.get('class_name', 'unknown'))
                    confidence = det.get('conf', det.get('confidence', 0))
                    print(f"   {i+1}. {class_name} (conf: {confidence})")
                return True
            else:
                print("❌ No detections found in backend status")
                return False
        else:
            print(f"❌ Failed to get status: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error verifying detection data: {e}")
        return False

def main():
    print("🧪 Backend Connection Test")
    print("=" * 50)
    
    # Test 1: Backend status
    if not test_backend_status():
        print("❌ Backend is not responding. Check your internet connection.")
        return
    
    print()
    
    # Test 2: Send test frame
    if not send_test_frame():
        print("❌ Failed to send test frame to backend.")
        return
    
    print()
    
    # Test 3: Verify detection data
    if verify_detection_data():
        print("\n🎉 All tests passed! Backend is working correctly.")
        print("\nNext steps:")
        print("1. Start the RPi detection script: ./restart_rpi_with_env.sh")
        print("2. Check frontend at: https://smoki.aeroband.org/dashboard")
    else:
        print("\n⚠️  Backend received frame but detection data not found.")
        print("Check backend logs for processing errors.")

if __name__ == "__main__":
    main()