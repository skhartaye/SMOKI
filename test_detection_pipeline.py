#!/usr/bin/env python3
"""
Test the complete detection pipeline to identify where the issue is
"""

import requests
import json
import time

BACKEND_URL = "https://smoki-backend-rpi.onrender.com"

def test_stream_status():
    """Test the stream status endpoint"""
    print("=== Testing Stream Status ===")
    try:
        response = requests.get(f"{BACKEND_URL}/api/stream/status")
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            return data
        else:
            print(f"Error: {response.text}")
            return None
    except Exception as e:
        print(f"Exception: {e}")
        return None

def test_send_mock_frame():
    """Send a mock frame with detection metadata"""
    print("\n=== Testing Mock Frame Upload ===")
    
    # Create a small test image (1x1 pixel JPEG)
    test_image = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x01\x01\x11\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00\xaa\xff\xd9'
    
    # Mock detection metadata
    metadata = {
        "camera_id": "test_camera",
        "location": "Test Location",
        "timestamp": "2026-03-27T04:50:00+00:00",
        "is_violation": True,
        "smoke_count": 2,
        "vehicle_count": 1,
        "plate_count": 1,
        "detections": [
            {"class": "smoke_black", "conf": 0.85, "bbox": {"x1": 100, "y1": 100, "x2": 200, "y2": 200}},
            {"class": "smoke_white", "conf": 0.75, "bbox": {"x1": 300, "y1": 150, "x2": 400, "y2": 250}},
            {"class": "passenger", "conf": 0.90, "bbox": {"x1": 500, "y1": 200, "x2": 600, "y2": 350}},
            {"class": "license_plate", "conf": 0.95, "bbox": {"x1": 520, "y1": 320, "x2": 580, "y2": 340}}
        ]
    }
    
    try:
        files = {"frame": ("test_frame.jpg", test_image, "image/jpeg")}
        data = {"metadata": json.dumps(metadata)}
        
        response = requests.post(f"{BACKEND_URL}/api/stream/frame", files=files, data=data)
        print(f"Upload Status Code: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"Upload Response: {json.dumps(result, indent=2)}")
            return True
        else:
            print(f"Upload Error: {response.text}")
            return False
    except Exception as e:
        print(f"Upload Exception: {e}")
        return False

def test_detection_snapshot():
    """Send a mock detection snapshot"""
    print("\n=== Testing Detection Snapshot ===")
    
    snapshot_data = {
        "timestamp": "2026-03-27T04:50:00+00:00",
        "camera_id": "test_camera",
        "location": "Test Location",
        "smoke_count": 2,
        "vehicle_count": 1,
        "plate_count": 1,
        "is_violation": True,
        "inference_ms": 150,
        "detections_json": {
            "detections": [
                {"class": "smoke_black", "conf": 0.85},
                {"class": "smoke_white", "conf": 0.75},
                {"class": "passenger", "conf": 0.90},
                {"class": "license_plate", "conf": 0.95}
            ]
        }
    }
    
    try:
        response = requests.post(f"{BACKEND_URL}/api/detections/snapshot", json=snapshot_data)
        print(f"Snapshot Status Code: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"Snapshot Response: {json.dumps(result, indent=2)}")
            return True
        else:
            print(f"Snapshot Error: {response.text}")
            return False
    except Exception as e:
        print(f"Snapshot Exception: {e}")
        return False

def main():
    print("🧪 Testing Detection Pipeline")
    print("=" * 50)
    
    # Test 1: Check initial stream status
    initial_status = test_stream_status()
    
    # Test 2: Send mock frame with detections
    frame_success = test_send_mock_frame()
    
    # Test 3: Send detection snapshot
    snapshot_success = test_detection_snapshot()
    
    # Test 4: Check stream status after sending data
    print("\n=== Testing Stream Status After Mock Data ===")
    time.sleep(2)  # Wait a bit for processing
    final_status = test_stream_status()
    
    # Summary
    print("\n" + "=" * 50)
    print("🔍 PIPELINE TEST SUMMARY")
    print("=" * 50)
    print(f"Initial Status: {'✅' if initial_status else '❌'}")
    print(f"Frame Upload: {'✅' if frame_success else '❌'}")
    print(f"Snapshot Upload: {'✅' if snapshot_success else '❌'}")
    print(f"Final Status: {'✅' if final_status else '❌'}")
    
    if final_status:
        detections = final_status.get('latest_detections', [])
        print(f"Detections Found: {len(detections)}")
        if detections:
            print("Detection Details:")
            for i, det in enumerate(detections):
                print(f"  {i+1}. {det.get('class', 'unknown')} - {det.get('conf', 0):.2f}")
        else:
            print("❌ No detections in final status - pipeline issue confirmed")
    
    print("\n🎯 Next Steps:")
    if not frame_success:
        print("- Fix frame upload endpoint")
    if not snapshot_success:
        print("- Fix snapshot endpoint")
    if final_status and not final_status.get('latest_detections'):
        print("- Fix detection metadata processing in backend")
    if not final_status:
        print("- Fix stream status endpoint")

if __name__ == "__main__":
    main()