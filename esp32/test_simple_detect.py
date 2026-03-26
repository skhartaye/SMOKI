#!/usr/bin/env python3
"""
Test script for simple detection system
Creates a mock frame and tests the backend upload
"""

import cv2
import numpy as np
import requests
import json
import os
from datetime import datetime, timezone

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv('.env.rpi')
except ImportError:
    pass

# Configuration
BACKEND_URL = os.getenv('API_URL', 'https://smoki-backend-rpi.onrender.com')
CAMERA_ID = os.getenv('DEVICE_ID', 'test_camera')
CAMERA_LOCATION = os.getenv('CAMERA_LOCATION', 'Test_Location')

def create_test_frame():
    """Create a test frame with some text"""
    # Create a 640x640 test image
    frame = np.zeros((640, 640, 3), dtype=np.uint8)
    
    # Add some color and text
    cv2.rectangle(frame, (50, 50), (590, 590), (64, 128, 255), 2)
    cv2.putText(frame, "TEST FRAME", (200, 300), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 3)
    cv2.putText(frame, f"Time: {datetime.now().strftime('%H:%M:%S')}", (150, 350), 
                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    cv2.putText(frame, f"Camera: {CAMERA_ID}", (150, 400), 
                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    
    # Add some mock detection boxes
    cv2.rectangle(frame, (100, 100), (200, 150), (0, 255, 0), 2)
    cv2.putText(frame, "smoke_black 0.85", (100, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    
    cv2.rectangle(frame, (300, 200), (450, 300), (255, 0, 0), 2)
    cv2.putText(frame, "passenger 0.92", (300, 195), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
    
    return frame

def create_test_metadata():
    """Create test detection metadata"""
    timestamp = datetime.now(timezone.utc).isoformat()
    
    # Mock detections
    detections = [
        {
            "class_name": "smoke_black",
            "confidence": 0.85,
            "bbox": {"x1": 100, "y1": 100, "x2": 200, "y2": 150},
            "model": "smoke-hailo8l.hef"
        },
        {
            "class_name": "passenger",
            "confidence": 0.92,
            "bbox": {"x1": 300, "y1": 200, "x2": 450, "y2": 300},
            "model": "vehicle-class-hailo8l.hef"
        }
    ]
    
    payload = {
        "camera_id": CAMERA_ID,
        "location": CAMERA_LOCATION,
        "timestamp": timestamp,
        "has_detection": True,
        "detections": detections,
        "summary": {
            "total_detections": len(detections),
            "smoke_detections": 1,
            "vehicle_detections": 1,
            "plate_detections": 0,
            "inference_time_ms": 850,
            "frame_size_bytes": 0  # Will be filled in
        }
    }
    
    return payload

def test_backend_upload():
    """Test uploading frame and metadata to backend"""
    print("🧪 Testing Simple Detection Backend Upload")
    print("=" * 45)
    
    # Create test frame
    print("📷 Creating test frame...")
    frame = create_test_frame()
    
    # Encode as JPEG
    _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(f"   Frame size: {len(buf)} bytes")
    
    # Create metadata
    print("📊 Creating test metadata...")
    metadata = create_test_metadata()
    metadata["summary"]["frame_size_bytes"] = len(buf)
    
    print(f"   Camera ID: {metadata['camera_id']}")
    print(f"   Location: {metadata['location']}")
    print(f"   Detections: {len(metadata['detections'])}")
    
    # Test backend connectivity first
    print(f"\n🌐 Testing backend connectivity...")
    print(f"   Backend URL: {BACKEND_URL}")
    
    try:
        health_response = requests.get(f"{BACKEND_URL}/api/health", timeout=5)
        if health_response.status_code == 200:
            print("   ✅ Backend is online")
        else:
            print(f"   ⚠️  Backend returned HTTP {health_response.status_code}")
    except Exception as e:
        print(f"   ❌ Backend connectivity error: {e}")
        return False
    
    # Upload frame and metadata
    print(f"\n📤 Uploading to {BACKEND_URL}/api/stream/frame...")
    
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/stream/frame",
            files={"frame": ("test_frame.jpg", buf.tobytes(), "image/jpeg")},
            data={"metadata": json.dumps(metadata)},
            timeout=10
        )
        
        if response.status_code == 200:
            print("   ✅ Upload successful!")
            result = response.json()
            print(f"   Response: {result}")
            return True
        else:
            print(f"   ❌ Upload failed: HTTP {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"   ❌ Upload error: {e}")
        return False

def test_stream_endpoints():
    """Test stream viewing endpoints"""
    print(f"\n🔍 Testing stream endpoints...")
    
    endpoints = [
        ("/api/stream/status", "Stream status"),
        ("/api/stream/latest.jpg", "Latest frame"),
    ]
    
    for endpoint, description in endpoints:
        try:
            url = f"{BACKEND_URL}{endpoint}"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                print(f"   ✅ {description}: {url}")
            else:
                print(f"   ⚠️  {description}: HTTP {response.status_code}")
                
        except Exception as e:
            print(f"   ❌ {description}: {e}")

def main():
    print("🎯 Simple Detection System Test")
    print("=" * 50)
    
    # Test upload
    upload_success = test_backend_upload()
    
    # Test viewing endpoints
    test_stream_endpoints()
    
    # Summary
    print(f"\n📋 Test Summary:")
    print(f"   Upload test: {'✅ PASS' if upload_success else '❌ FAIL'}")
    
    if upload_success:
        print(f"\n🎉 Test successful! You can view the frame at:")
        print(f"   {BACKEND_URL}/api/stream/latest.jpg")
        print(f"\n💡 To run the real detection system:")
        print(f"   python3 rpi_simple_detect.py")
    else:
        print(f"\n⚠️  Test failed. Check backend connectivity and configuration.")
    
    return 0 if upload_success else 1

if __name__ == '__main__':
    import sys
    sys.exit(main())