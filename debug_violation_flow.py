#!/usr/bin/env python3
"""
Debug the exact violation creation flow to find where UNREAD plates are generated
"""

def debug_violation_flow():
    """Simulate the exact violation creation flow with debugging"""
    
    print("🔍 Debugging Violation Creation Flow")
    print("=" * 50)
    
    # Simulate the exact scenario that might be creating UNREAD plates
    # This could be happening when OCR returns some text but it's not meaningful
    
    detections = [
        # Smoke detection
        {
            "class_name": "smoke_white",
            "confidence": 0.40,
            "bbox": {"x1": 400, "y1": 30, "x2": 500, "y2": 80}
        },
        
        # Vehicle detection
        {
            "class_name": "puv",
            "confidence": 0.75,
            "bbox": {"x1": 380, "y1": 140, "x2": 480, "y2": 200}
        },
        
        # License plate with various problematic texts
        {
            "class_name": "license_plate",
            "confidence": 0.65,
            "bbox": {"x1": 410, "y1": 190, "x2": 450, "y2": 200},
            "plate_text": "",  # Empty
            "ocr_confidence": 0.0
        },
        {
            "class_name": "license_plate", 
            "confidence": 0.60,
            "bbox": {"x1": 420, "y1": 200, "x2": 460, "y2": 210},
            "plate_text": "   ",  # Whitespace only
            "ocr_confidence": 0.1
        },
        {
            "class_name": "license_plate",
            "confidence": 0.55,
            "bbox": {"x1": 430, "y1": 210, "x2": 470, "y2": 220},
            "plate_text": "???",  # Invalid characters
            "ocr_confidence": 0.2
        },
        {
            "class_name": "license_plate",
            "confidence": 0.70,
            "bbox": {"x1": 440, "y1": 220, "x2": 480, "y2": 230},
            "plate_text": "ABC",  # Too short but might pass length check
            "ocr_confidence": 0.4
        }
    ]
    
    print("📊 Input detections:")
    for i, det in enumerate(detections):
        if det.get('class_name') == 'license_plate':
            plate_text = det.get('plate_text', '')
            ocr_conf = det.get('ocr_confidence', 0.0)
            print(f"   Plate {i}: '{plate_text}' (conf: {ocr_conf:.2f}, len: {len(plate_text)})")
    
    # Group detections by type (simulate backend logic)
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
    
    print(f"\n🔍 Grouped detections:")
    print(f"   Smoke: {len(smoke_detections)}")
    print(f"   Vehicles: {len(vehicle_detections)}")
    print(f"   Plates: {len(plate_detections)}")
    
    # Test the filtering logic (simulate backend stream.py logic)
    readable_plates = []
    unreadable_plates = []
    
    print(f"\n🔍 Testing plate filtering:")
    
    for i, plate in enumerate(plate_detections):
        plate_text = plate.get('plate_text', '').strip()
        ocr_confidence = plate.get('ocr_confidence', 0.0)
        
        print(f"   Plate {i+1}: Processing '{plate_text}' (conf: {ocr_confidence:.2f})")
        
        # Apply the exact filtering logic from backend/stream.py
        if plate_text and len(plate_text) >= 3 and ocr_confidence >= 0.3:
            # Check if plate text looks like a real license plate (not UNREAD or similar)
            if not plate_text.startswith('UNREAD') and not plate_text.startswith('UNKNOWN') and not plate_text.startswith('PLACEHOLDER'):
                readable_plates.append({
                    'plate_text': plate_text,
                    'ocr_confidence': ocr_confidence,
                    'bbox': plate.get('bbox', []),
                    'ocr_metadata': plate.get('ocr_metadata', {})
                })
                print(f"      ✅ READABLE: '{plate_text}' (passes all checks)")
            else:
                unreadable_plates.append({
                    'plate_text': plate_text,
                    'ocr_confidence': ocr_confidence,
                    'reason': 'placeholder_text'
                })
                print(f"      ❌ UNREADABLE: '{plate_text}' (placeholder text)")
        else:
            unreadable_plates.append({
                'plate_text': plate_text or 'empty',
                'ocr_confidence': ocr_confidence,
                'reason': 'low_confidence_or_empty'
            })
            print(f"      ❌ UNREADABLE: '{plate_text}' (low confidence or empty)")
    
    print(f"\n📊 Filtering results:")
    print(f"   Readable plates: {len(readable_plates)}")
    for plate in readable_plates:
        print(f"      - '{plate['plate_text']}' (conf: {plate['ocr_confidence']:.2f})")
    
    print(f"   Unreadable plates: {len(unreadable_plates)}")
    for plate in unreadable_plates:
        print(f"      - '{plate['plate_text']}' (reason: {plate['reason']})")
    
    # Check what would happen in violation creation
    if len(readable_plates) == 0:
        print(f"\n✅ CORRECT: No violations would be created (no readable plates)")
        print(f"   System should create OCR failure notification instead")
    else:
        print(f"\n⚠️  POTENTIAL ISSUE: {len(readable_plates)} violation(s) would be created")
        print(f"   These plates would be registered as vehicles:")
        for plate in readable_plates:
            print(f"      - register_vehicle('{plate['plate_text']}', 'puv')")
    
    # Test edge cases that might slip through
    print(f"\n🔍 Testing edge cases:")
    
    edge_cases = [
        ("", 0.0),           # Empty string
        ("   ", 0.1),        # Whitespace only  
        ("AB", 0.5),         # Too short
        ("???", 0.4),        # Invalid characters
        ("ABC", 0.4),        # Exactly 3 chars, passes length check
        ("ABCD", 0.35),      # 4 chars, passes all checks
        ("UNREAD-TEST", 0.8), # UNREAD prefix, should be filtered
    ]
    
    for plate_text, ocr_conf in edge_cases:
        stripped = plate_text.strip()
        
        # Apply filtering logic
        if stripped and len(stripped) >= 3 and ocr_conf >= 0.3:
            if not stripped.startswith('UNREAD') and not stripped.startswith('UNKNOWN') and not stripped.startswith('PLACEHOLDER'):
                print(f"   '{plate_text}' (conf: {ocr_conf:.2f}) → ✅ WOULD CREATE VIOLATION")
            else:
                print(f"   '{plate_text}' (conf: {ocr_conf:.2f}) → ❌ Filtered (placeholder)")
        else:
            print(f"   '{plate_text}' (conf: {ocr_conf:.2f}) → ❌ Filtered (low conf/empty/short)")

if __name__ == "__main__":
    debug_violation_flow()