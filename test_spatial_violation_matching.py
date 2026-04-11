#!/usr/bin/env python3
"""
Test script to verify spatial violation matching logic
"""

def test_spatial_matching():
    print("🧪 Testing Spatial Violation Matching")
    print("=" * 50)
    
    # Test case: Multiple vehicles, but only one near smoke
    print("\n📋 Test Case: Multiple vehicles, smoke near one specific vehicle")
    
    # Simulate detections from the screenshot
    smoke_detections = [
        {
            "class_name": "smoke_black",
            "confidence": 0.52,
            "bbox": {"x1": 570, "y1": 50, "x2": 620, "y2": 100}  # Smoke above one vehicle
        }
    ]
    
    vehicle_detections = [
        {
            "class_name": "passenger",
            "confidence": 0.81,
            "bbox": {"x1": 550, "y1": 120, "x2": 650, "y2": 200}  # Vehicle directly below smoke
        },
        {
            "class_name": "puv", 
            "confidence": 0.73,
            "bbox": {"x1": 300, "y1": 150, "x2": 400, "y2": 230}  # Vehicle far from smoke
        },
        {
            "class_name": "puv",
            "confidence": 0.71,
            "bbox": {"x1": 700, "y1": 180, "x2": 800, "y2": 260}  # Another vehicle far from smoke
        },
        {
            "class_name": "two_wheel",
            "confidence": 0.68,
            "bbox": {"x1": 200, "y1": 250, "x2": 250, "y2": 300}  # Motorcycle far from smoke
        }
    ]
    
    readable_plates = [
        {
            "plate_text": "ABC123",
            "ocr_confidence": 0.65,
            "bbox": {"x1": 580, "y1": 190, "x2": 620, "y2": 200},  # Plate on vehicle near smoke
            "ocr_metadata": {}
        },
        {
            "plate_text": "XYZ789", 
            "ocr_confidence": 0.72,
            "bbox": {"x1": 330, "y1": 220, "x2": 370, "y2": 230},  # Plate on vehicle far from smoke
            "ocr_metadata": {}
        },
        {
            "plate_text": "DEF456",
            "ocr_confidence": 0.58,
            "bbox": {"x1": 730, "y1": 250, "x2": 770, "y2": 260},  # Another plate far from smoke
            "ocr_metadata": {}
        }
    ]
    
    # Simulate the spatial matching logic
    violating_vehicles = []
    
    for smoke in smoke_detections:
        smoke_bbox = smoke.get('bbox', {})
        smoke_center_x = (smoke_bbox.get('x1', 0) + smoke_bbox.get('x2', 0)) / 2
        smoke_center_y = (smoke_bbox.get('y1', 0) + smoke_bbox.get('y2', 0)) / 2
        
        print(f"  Smoke center: ({smoke_center_x}, {smoke_center_y})")
        
        # Find the closest vehicle to this smoke detection
        closest_vehicle = None
        closest_distance = float('inf')
        
        for i, vehicle in enumerate(vehicle_detections):
            vehicle_bbox = vehicle.get('bbox', {})
            vehicle_center_x = (vehicle_bbox.get('x1', 0) + vehicle_bbox.get('x2', 0)) / 2
            vehicle_center_y = (vehicle_bbox.get('y1', 0) + vehicle_bbox.get('y2', 0)) / 2
            
            # Calculate distance between smoke and vehicle centers
            distance = ((smoke_center_x - vehicle_center_x) ** 2 + (smoke_center_y - vehicle_center_y) ** 2) ** 0.5
            
            print(f"    Vehicle {i+1} ({vehicle['class_name']}): center ({vehicle_center_x}, {vehicle_center_y}), distance: {distance:.1f}px")
            
            if distance < closest_distance:
                closest_distance = distance
                closest_vehicle = vehicle
        
        print(f"  → Closest vehicle: {closest_vehicle['class_name']} at {closest_distance:.1f}px")
        
        # Only create violation if vehicle is reasonably close to smoke (within 200 pixels)
        if closest_vehicle and closest_distance < 200:
            # Find a readable license plate near this vehicle
            closest_plate = None
            closest_plate_distance = float('inf')
            
            vehicle_bbox = closest_vehicle.get('bbox', {})
            vehicle_center_x = (vehicle_bbox.get('x1', 0) + vehicle_bbox.get('x2', 0)) / 2
            vehicle_center_y = (vehicle_bbox.get('y1', 0) + vehicle_bbox.get('y2', 0)) / 2
            
            for j, plate_info in enumerate(readable_plates):
                plate_bbox = plate_info.get('bbox', {})
                plate_center_x = (plate_bbox.get('x1', 0) + plate_bbox.get('x2', 0)) / 2
                plate_center_y = (plate_bbox.get('y1', 0) + plate_bbox.get('y2', 0)) / 2
                
                # Calculate distance between vehicle and plate
                plate_distance = ((vehicle_center_x - plate_center_x) ** 2 + (vehicle_center_y - plate_center_y) ** 2) ** 0.5
                
                print(f"    Plate {j+1} ({plate_info['plate_text']}): center ({plate_center_x}, {plate_center_y}), distance from vehicle: {plate_distance:.1f}px")
                
                if plate_distance < closest_plate_distance:
                    closest_plate_distance = plate_distance
                    closest_plate = plate_info
            
            print(f"  → Closest plate: {closest_plate['plate_text']} at {closest_plate_distance:.1f}px from vehicle")
            
            # Only create violation if plate is close to the vehicle (within 150 pixels)
            if closest_plate and closest_plate_distance < 150:
                violating_vehicles.append({
                    'license_plate': closest_plate['plate_text'],
                    'vehicle_type': closest_vehicle['class_name'],
                    'smoke_vehicle_distance': closest_distance,
                    'vehicle_plate_distance': closest_plate_distance
                })
                
                print(f"  ✅ VIOLATION CREATED: {closest_plate['plate_text']} ({closest_vehicle['class_name']})")
                print(f"     Smoke→Vehicle: {closest_distance:.1f}px, Vehicle→Plate: {closest_plate_distance:.1f}px")
            else:
                print(f"  ❌ NO VIOLATION: Plate too far from vehicle ({closest_plate_distance:.1f}px > 150px)")
        else:
            print(f"  ❌ NO VIOLATION: Vehicle too far from smoke ({closest_distance:.1f}px > 200px)")
    
    print(f"\n📊 Result Summary:")
    print(f"  Total vehicles detected: {len(vehicle_detections)}")
    print(f"  Total readable plates: {len(readable_plates)}")
    print(f"  Violations created: {len(violating_vehicles)}")
    
    if violating_vehicles:
        print(f"  Violating vehicles:")
        for v in violating_vehicles:
            print(f"    - {v['license_plate']} ({v['vehicle_type']})")
    else:
        print(f"  No violations created")

if __name__ == "__main__":
    test_spatial_matching()