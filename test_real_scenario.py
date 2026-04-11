#!/usr/bin/env python3
"""
Test the real scenario from the screenshot to debug spatial matching
"""

def test_real_scenario():
    print("🧪 Testing Real Scenario from Screenshot")
    print("=" * 50)
    
    # Simulate the exact detections from your screenshot
    # Based on the image: smoke at top, multiple vehicles below
    detections = [
        # Smoke detection (white smoke at top)
        {
            "class_name": "smoke_white",
            "confidence": 0.40,
            "bbox": {"x1": 400, "y1": 30, "x2": 500, "y2": 80}  # Top center
        },
        
        # Vehicle detections (from your screenshot)
        {
            "class_name": "two_wheel",  # Motorcycle top left
            "confidence": 0.83,
            "bbox": {"x1": 150, "y1": 120, "x2": 200, "y2": 180}
        },
        {
            "class_name": "passenger",  # Car top center (closest to smoke)
            "confidence": 0.69,
            "bbox": {"x1": 380, "y1": 140, "x2": 480, "y2": 200}
        },
        {
            "class_name": "puv",  # PUV right side
            "confidence": 0.68,
            "bbox": {"x1": 520, "y1": 160, "x2": 620, "y2": 220}
        },
        {
            "class_name": "two_wheel",  # Motorcycle bottom left
            "confidence": 0.83,
            "bbox": {"x1": 120, "y1": 250, "x2": 170, "y2": 310}
        },
        {
            "class_name": "two_wheel",  # Motorcycle bottom center
            "confidence": 0.97,
            "bbox": {"x1": 350, "y1": 280, "x2": 400, "y2": 340}
        },
        
        # License plate detections (assume OCR worked and read real plates)
        {
            "class_name": "license_plate",
            "confidence": 0.75,
            "bbox": {"x1": 410, "y1": 190, "x2": 450, "y2": 200},  # Plate on car near smoke
            "plate_text": "ABC123",  # Real plate text
            "ocr_confidence": 0.75
        },
        {
            "class_name": "license_plate", 
            "confidence": 0.68,
            "bbox": {"x1": 550, "y1": 210, "x2": 590, "y2": 220},  # Plate on PUV (far from smoke)
            "plate_text": "XYZ789",  # Real plate text
            "ocr_confidence": 0.68
        },
        {
            "class_name": "license_plate",
            "confidence": 0.72,
            "bbox": {"x1": 370, "y1": 330, "x2": 410, "y2": 340},  # Plate on bottom motorcycle (far from smoke)
            "plate_text": "DEF456",  # Real plate text
            "ocr_confidence": 0.72
        }
    ]
    
    print(f"📊 Scenario setup:")
    print(f"   Smoke: 1 (at top center)")
    print(f"   Vehicles: 5 (1 car, 1 PUV, 3 motorcycles)")
    print(f"   Plates: 3 (all readable)")
    print(f"   Expected result: Only ABC123 (car closest to smoke) should be flagged")
    
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
    
    # Filter readable plates
    readable_plates = []
    for plate in plate_detections:
        plate_text = plate.get('plate_text', '').strip()
        ocr_confidence = plate.get('ocr_confidence', 0.0)
        
        if plate_text and len(plate_text) >= 3 and ocr_confidence >= 0.3:
            if not plate_text.startswith('UNREAD') and not plate_text.startswith('UNKNOWN'):
                readable_plates.append({
                    'plate_text': plate_text,
                    'ocr_confidence': ocr_confidence,
                    'bbox': plate.get('bbox', []),
                    'ocr_metadata': plate.get('ocr_metadata', {})
                })
    
    print(f"\n🔍 Spatial matching analysis:")
    
    # Simulate the spatial matching logic
    violating_vehicles = []
    
    for i, smoke in enumerate(smoke_detections):
        smoke_bbox = smoke.get('bbox', {})
        smoke_center_x = (smoke_bbox.get('x1', 0) + smoke_bbox.get('x2', 0)) / 2
        smoke_center_y = (smoke_bbox.get('y1', 0) + smoke_bbox.get('y2', 0)) / 2
        
        print(f"  Smoke {i+1}: center=({smoke_center_x:.1f}, {smoke_center_y:.1f})")
        
        # Find the closest vehicle to this smoke detection
        closest_vehicle = None
        closest_distance = float('inf')
        
        for j, vehicle in enumerate(vehicle_detections):
            vehicle_bbox = vehicle.get('bbox', {})
            vehicle_center_x = (vehicle_bbox.get('x1', 0) + vehicle_bbox.get('x2', 0)) / 2
            vehicle_center_y = (vehicle_bbox.get('y1', 0) + vehicle_bbox.get('y2', 0)) / 2
            
            # Calculate distance between smoke and vehicle centers
            distance = ((smoke_center_x - vehicle_center_x) ** 2 + (smoke_center_y - vehicle_center_y) ** 2) ** 0.5
            
            print(f"    Vehicle {j+1} ({vehicle.get('class_name')}): center=({vehicle_center_x:.1f}, {vehicle_center_y:.1f}), distance={distance:.1f}px")
            
            if distance < closest_distance:
                closest_distance = distance
                closest_vehicle = vehicle
        
        print(f"  → Closest vehicle: {closest_vehicle.get('class_name')} at {closest_distance:.1f}px")
        
        # Only create violation if vehicle is reasonably close to smoke (within 200 pixels)
        if closest_vehicle and closest_distance < 200:
            print(f"  ✅ Vehicle is close enough ({closest_distance:.1f}px < 200px)")
            
            # Find a readable license plate near this vehicle
            closest_plate = None
            closest_plate_distance = float('inf')
            
            vehicle_bbox = closest_vehicle.get('bbox', {})
            vehicle_center_x = (vehicle_bbox.get('x1', 0) + vehicle_bbox.get('x2', 0)) / 2
            vehicle_center_y = (vehicle_bbox.get('y1', 0) + vehicle_bbox.get('y2', 0)) / 2
            
            for k, plate_info in enumerate(readable_plates):
                plate_bbox = plate_info.get('bbox', {})
                plate_center_x = (plate_bbox.get('x1', 0) + plate_bbox.get('x2', 0)) / 2
                plate_center_y = (plate_bbox.get('y1', 0) + plate_bbox.get('y2', 0)) / 2
                
                # Calculate distance between vehicle and plate
                plate_distance = ((vehicle_center_x - plate_center_x) ** 2 + (vehicle_center_y - plate_center_y) ** 2) ** 0.5
                
                print(f"    Plate {k+1} ({plate_info['plate_text']}): center=({plate_center_x:.1f}, {plate_center_y:.1f}), distance={plate_distance:.1f}px")
                
                if plate_distance < closest_plate_distance:
                    closest_plate_distance = plate_distance
                    closest_plate = plate_info
            
            print(f"  → Closest plate: {closest_plate['plate_text']} at {closest_plate_distance:.1f}px")
            
            # Only create violation if plate is close to the vehicle (within 150 pixels)
            if closest_plate and closest_plate_distance < 150:
                plate_text = closest_plate['plate_text']
                already_added = any(v['license_plate'] == plate_text for v in violating_vehicles)
                
                if not already_added:
                    violating_vehicles.append({
                        'license_plate': plate_text,
                        'vehicle_type': closest_vehicle.get('class_name'),
                        'smoke_vehicle_distance': closest_distance,
                        'vehicle_plate_distance': closest_plate_distance
                    })
                    
                    print(f"  ✅ VIOLATION CREATED: {plate_text} ({closest_vehicle.get('class_name')})")
                else:
                    print(f"  ❌ Duplicate avoided: {plate_text}")
            else:
                print(f"  ❌ Plate too far from vehicle ({closest_plate_distance:.1f}px > 150px)")
        else:
            print(f"  ❌ Vehicle too far from smoke ({closest_distance:.1f}px > 200px)")
    
    print(f"\n📊 Results:")
    print(f"   Violations created: {len(violating_vehicles)}")
    if violating_vehicles:
        for v in violating_vehicles:
            print(f"   - {v['license_plate']} ({v['vehicle_type']})")
    
    # Check if result is correct
    if len(violating_vehicles) == 1 and violating_vehicles[0]['license_plate'] == 'ABC123':
        print(f"\n✅ CORRECT: Only the vehicle closest to smoke was flagged!")
    else:
        print(f"\n❌ INCORRECT: Expected only ABC123, got {[v['license_plate'] for v in violating_vehicles]}")

if __name__ == "__main__":
    test_real_scenario()