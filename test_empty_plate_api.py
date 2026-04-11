#!/usr/bin/env python3
"""
Test what happens when we send empty plate data to the API
"""
import requests
import json
import cv2
import numpy as np
from datetime import datetime, timezone

API_URL = 'https://smoki-backend-rpi.onrender.com'

def test_empty_plate_data():
    """Test sending detection data with empty plate text to see if UNREAD plates are generated"""
    
    print("🧪 Testing Empty Plate Data API Behavior")
    print("=" * 50)
    
    # Create a dummy frame
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    
    # Simulate detections with smoke, vehicles, and empty plate text
    detections = [
        # Smoke detection
        {
            "model_name": "smoke_detection",
            "class_name": "smoke_white",
            "class": "smoke_white",
            "conf": 0.40,
            "confidence": 0.40,
            "bounding_box": {"x1": 400, "y1": 30, "x2": 500, "y2": 80},
            "bbox": {"x1": 400, "y1": 30, "x2": 500, "y2": 80}
        },
        
        # Vehicle detection
        {
            "model_name": "vehicle_detection",
            "class_name": "puv",
            "class": "puv",
            "conf": 0.75,
            "confidence": 0.75,
            "bounding_box": {"x1": 380, "y1": 140, "x2": 480, "y2": 200},
            "bbox": {"x1": 380, "y1": 140, "x2": 480, "y2": 200}
        },
        
        # License plate with EMPTY text (this might trigger UNREAD generation)
        {
            "model_name": "license_plate",
            "class_name": "license_plate",
            "class": "license_plate",
            "conf": 0.65,
            "confidence": 0.65,
            "bounding_box": {"x1": 410, "y1": 190, "x2": 450, "y2": 200},
            "bbox": {"x1": 410, "y1": 190, "x2": 450, "y2": 200},
            "plate_text": "",  # Empty plate text
            "ocr_confidence": 0.0
        }
    ]
    
    # Prepare metadata
    timestamp = datetime.now(timezone.utc).isoformat()
    metadata = {
        "timestamp": timestamp,
        "camera_id": "TEST_CAMERA_01",
        "location": "Test Location",
        "frame_number": 1,
        "detections": detections,
        "smoke_count": 1,
        "vehicle_count": 1,
        "plate_count": 1,
        "detection_counts": {
            "smoke": 1,
            "vehicle": 1,
            "plate": 1
        },
        "is_violation": True,
        "source": "test_empty_plate_api"
    }
    
    print(f"📤 Sending test data:")
    print(f"   Smoke: 1 (confidence: 0.40)")
    print(f"   Vehicles: 1 (PUV, confidence: 0.75)")
    print(f"   Plates: 1 (EMPTY text, confidence: 0.0)")
    
    try:
        # Send to API
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
        
        print(f"\n📥 API Response:")
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 200:
            print(f"   ✅ Success: Frame processed")
            
            # Check if violations were created
            import time
            time.sleep(2)  # Wait for processing
            
            # Check vehicle ranking to see if UNREAD plates were created
            ranking_response = requests.get(f"{API_URL}/api/vehicles/ranking", timeout=10)
            if ranking_response.status_code == 200:
                ranking_data = ranking_response.json()
                vehicles = ranking_data.get('vehicles', [])
                
                print(f"\n📊 Vehicle Ranking After Test:")
                print(f"   Total vehicles: {len(vehicles)}")
                
                for i, vehicle in enumerate(vehicles[:3]):  # Show first 3
                    license_plate = vehicle.get('license_plate', 'unknown')
                    vehicle_type = vehicle.get('vehicle_type', 'unknown')
                    total_violations = vehicle.get('total_violations', 0)
                    
                    print(f"   {i+1}. {license_plate} ({vehicle_type}) - {total_violations} violations")
                    
                    if license_plate.startswith('UNREAD'):
                        print(f"      ❌ UNREAD plate detected! This confirms the bug.")
                    else:
                        print(f"      ✅ Real plate text: {license_plate}")
            else:
                print(f"   ❌ Failed to get ranking: {ranking_response.status_code}")
        else:
            print(f"   ❌ Failed: {response.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_empty_plate_data()