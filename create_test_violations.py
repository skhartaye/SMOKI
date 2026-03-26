#!/usr/bin/env python3
"""
Create test violation data for dashboard testing
"""

import sys
sys.path.insert(0, 'postgre')

from database import register_vehicle, create_violation, insert_vehicle_detection_from_rpi
from datetime import datetime, timezone
import json

def create_test_data():
    print("🧪 Creating Test Violation Data")
    print("=" * 40)
    
    # Create some test vehicles with violations
    test_vehicles = [
        {"plate": "ABC-1234", "type": "passenger", "violations": 5},
        {"plate": "PUV-5678", "type": "puv", "violations": 12},
        {"plate": "SVC-9012", "type": "services", "violations": 3},
        {"plate": "MC-3456", "type": "two_wheel", "violations": 8},
    ]
    
    for vehicle_data in test_vehicles:
        print(f"\n📋 Creating vehicle: {vehicle_data['plate']}")
        
        # Register vehicle
        vehicle = register_vehicle(vehicle_data["plate"], vehicle_data["type"])
        if vehicle:
            print(f"   ✓ Registered: ID={vehicle['id']}")
            
            # Create violations
            for i in range(vehicle_data["violations"]):
                violation = create_violation(
                    vehicle_id=vehicle['id'],
                    detection_id=None,
                    violation_type="smoke_emission",
                    severity="warning" if i % 2 == 0 else "critical",
                    description=f"Smoke detected from {vehicle_data['type']} (test violation {i+1})"
                )
                if violation:
                    print(f"   ✓ Created violation {i+1}: ID={violation['id']}")
        else:
            print(f"   ✗ Failed to register vehicle")
    
    # Create some test detection data
    print(f"\n📸 Creating test detection data...")
    
    test_detections = [
        {
            "class_name": "passenger",
            "confidence": 0.85,
            "bbox": {"x1": 100, "y1": 100, "x2": 200, "y2": 200},
            "model": "vehicle-class-hailo8l.hef"
        },
        {
            "class_name": "smoke_black",
            "confidence": 0.72,
            "bbox": {"x1": 150, "y1": 50, "x2": 250, "y2": 150},
            "model": "smoke-hailo8l.hef"
        }
    ]
    
    # Create fake frame data
    fake_frame = b"fake_jpeg_data_for_testing" * 100
    
    metadata = {
        "camera_id": "test_camera",
        "location": "Test_Location",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_detections": 2,
            "smoke_detections": 1,
            "vehicle_detections": 1,
            "inference_time_ms": 450
        }
    }
    
    result = insert_vehicle_detection_from_rpi(
        timestamp=datetime.now(timezone.utc),
        camera_id="test_camera",
        location="Test_Location",
        detections=test_detections,
        frame_data=fake_frame,
        metadata=metadata
    )
    
    if result:
        print(f"   ✓ Created detection: ID={result['id']}, detections={result['detections_count']}")
    else:
        print(f"   ✗ Failed to create detection")
    
    print(f"\n✅ Test data creation complete!")

if __name__ == '__main__':
    create_test_data()