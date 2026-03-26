#!/usr/bin/env python3
"""
Show exactly where the simple detection system sends data
"""

import os
import requests
from datetime import datetime

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv('.env.rpi')
except ImportError:
    pass

# Configuration
BACKEND_URL = os.getenv('API_URL', 'https://smoki-backend-rpi.onrender.com')
CAMERA_ID = os.getenv('DEVICE_ID', 'rpi_camera_01')
CAMERA_LOCATION = os.getenv('CAMERA_LOCATION', 'Main_Entrance')

def show_data_endpoints():
    """Show all the places where data goes and how to view it"""
    
    print("🎯 RPi Simple Detection - Data Flow Map")
    print("=" * 50)
    print(f"📍 Camera: {CAMERA_ID} at {CAMERA_LOCATION}")
    print(f"🔗 Backend: {BACKEND_URL}")
    print()
    
    print("📤 WHERE DATA IS SENT:")
    print(f"   Endpoint: {BACKEND_URL}/api/stream/frame")
    print("   Method: POST")
    print("   Data: Frame image + Detection metadata")
    print("   Frequency: Every 5 seconds")
    print()
    
    print("👀 WHERE YOU CAN VIEW DATA:")
    print()
    
    # 1. Latest frame
    print("1️⃣  LATEST FRAME (with detection boxes):")
    print(f"   🖼️  {BACKEND_URL}/api/stream/latest.jpg")
    print("   Shows: Most recent frame with AI detections drawn")
    print()
    
    # 2. Stream status
    print("2️⃣  STREAM STATUS:")
    print(f"   📊 {BACKEND_URL}/api/stream/status")
    print("   Shows: FPS, buffer info, frame count")
    print()
    
    # 3. Live MJPEG stream
    print("3️⃣  LIVE MJPEG STREAM:")
    print(f"   🎥 {BACKEND_URL}/api/stream/stream.mjpeg")
    print("   Shows: Continuous video stream of detection frames")
    print()
    
    # 4. Backend health
    print("4️⃣  BACKEND HEALTH:")
    print(f"   ❤️  {BACKEND_URL}/api/health")
    print("   Shows: Backend status and database connection")
    print()
    
    print("🌐 FRONTEND DASHBOARD:")
    print(f"   📱 {BACKEND_URL.replace('-rpi', '')}")
    print("   Note: Frontend may need updates to show the new stream format")
    print()

def test_endpoints():
    """Test each endpoint to see if data is flowing"""
    
    print("🧪 TESTING DATA ENDPOINTS:")
    print("-" * 30)
    
    endpoints = [
        ("/api/health", "Backend Health"),
        ("/api/stream/status", "Stream Status"),
        ("/api/stream/latest.jpg", "Latest Frame"),
    ]
    
    for endpoint, name in endpoints:
        try:
            url = f"{BACKEND_URL}{endpoint}"
            print(f"Testing {name}...")
            
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                print(f"   ✅ {name}: WORKING")
                
                if endpoint == "/api/stream/status":
                    data = response.json()
                    print(f"      Status: {data.get('status', 'unknown')}")
                    print(f"      FPS: {data.get('fps', 0)}")
                    print(f"      Frames: {data.get('buffered_frames', 0)}")
                    
                elif endpoint == "/api/stream/latest.jpg":
                    print(f"      Frame size: {len(response.content)} bytes")
                    if len(response.content) > 0:
                        print(f"      ✅ Frame data available!")
                    else:
                        print(f"      ⚠️  No frame data yet")
                        
            else:
                print(f"   ❌ {name}: HTTP {response.status_code}")
                
        except Exception as e:
            print(f"   ❌ {name}: {e}")
        
        print()

def show_detection_data_format():
    """Show what detection data looks like"""
    
    print("📊 DETECTION DATA FORMAT:")
    print("-" * 25)
    
    sample_data = {
        "camera_id": CAMERA_ID,
        "location": CAMERA_LOCATION,
        "timestamp": datetime.now().isoformat(),
        "has_detection": True,
        "detections": [
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
        ],
        "summary": {
            "total_detections": 2,
            "smoke_detections": 1,
            "vehicle_detections": 1,
            "plate_detections": 0,
            "inference_time_ms": 850,
            "frame_size_bytes": 45123
        }
    }
    
    import json
    print(json.dumps(sample_data, indent=2))
    print()

def main():
    show_data_endpoints()
    test_endpoints()
    show_detection_data_format()
    
    print("💡 QUICK COMMANDS TO VIEW YOUR DATA:")
    print("-" * 35)
    print(f"# View latest frame in browser:")
    print(f"open {BACKEND_URL}/api/stream/latest.jpg")
    print()
    print(f"# Check stream status:")
    print(f"curl {BACKEND_URL}/api/stream/status")
    print()
    print(f"# Download latest frame:")
    print(f"curl -o latest_frame.jpg {BACKEND_URL}/api/stream/latest.jpg")
    print()
    
    print("🚀 TO START SENDING DATA:")
    print("python3 rpi_simple_detect.py")

if __name__ == '__main__':
    main()