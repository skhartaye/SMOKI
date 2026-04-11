#!/usr/bin/env python3
"""
Test current violation logic to see what's happening with UNREAD plates
"""

def test_current_logic():
    print("🧪 Testing Current Violation Logic")
    print("=" * 50)
    
    # Simulate the detections from your screenshot
    detections = [
        # Smoke detection (at top)
        {
            "class_name": "smoke_black",
            "confidence": 0.52,
            "bbox": {"x1": 570, "y1": 50, "x2": 620, "y2": 100}
        },
        
        # Vehicle detections
        {
            "class_name": "puv",
            "confidence": 0.73,
            "bbox": {"x1": 550, "y1": 120, "x2": 650, "y2": 200}  # Vehicle near smoke
        },
        {
            "class_name": "puv", 
            "confidence": 0.71,
            "bbox": {"x1": 300, "y1": 150, "x2": 400, "y2": 230}  # Vehicle far from smoke
        },
        {
            "class_name": "two_wheel",
            "confidence": 0.68,
            "bbox": {"x1": 200, "y1": 250, "x2": 250, "y2": 300}  # Motorcycle far from smoke
        },
        
        # License plate detections with UNREAD text (this is the problem!)
        {
            "class_name": "license_plate",
            "confidence": 0.65,
            "bbox": {"x1": 580, "y1": 190, "x2": 620, "y2": 200},
            "plate_text": "UNREAD-PUV-124011-1",  # This should be filtered out!
            "ocr_confidence": 0.65
        },
        {
            "class_name": "license_plate",
            "confidence": 0.72,
            "bbox": {"x1": 330, "y1": 220, "x2": 370, "y2": 230},
            "plate_text": "UNREAD-PUV-124011-3",  # This should be filtered out!
            "ocr_confidence": 0.72
        },
        {
            "class_name": "license_plate",
            "confidence": 0.58,
            "bbox": {"x1": 230, "y1": 270, "x2": 270, "y2": 280},
            "plate_text": "UNREAD-TWO_WHEEL-124011-2",  # This should be filtered out!
            "ocr_confidence": 0.58
        }
    ]
    
    print(f"📊 Input detections:")
    print(f"   Smoke: 1")
    print(f"   Vehicles: 3") 
    print(f"   Plates: 3 (all UNREAD)")
    
    # Test the filtering logic
    print(f"\n🔍 Testing plate filtering:")
    
    readable_plates = []
    unreadable_plates = []
    
    for plate in detections:
        if plate.get('class_name') == 'license_plate':
            plate_text = plate.get('plate_text', '').strip()
            ocr_confidence = plate.get('ocr_confidence', 0.0)
            
            print(f"   Processing plate: '{plate_text}' (confidence: {ocr_confidence:.2f})")
            
            # Apply the filtering logic
            if plate_text and len(plate_text) >= 3 and ocr_confidence >= 0.3:
                # Check if plate text looks like a real license plate (not UNREAD or similar)
                if not plate_text.startswith('UNREAD') and not plate_text.startswith('UNKNOWN') and not plate_text.startswith('PLACEHOLDER'):
                    readable_plates.append(plate_text)
                    print(f"     ✅ READABLE: {plate_text}")
                else:
                    unreadable_plates.append(plate_text)
                    print(f"     ❌ UNREADABLE (placeholder): {plate_text}")
            else:
                unreadable_plates.append(plate_text or 'empty')
                print(f"     ❌ UNREADABLE (low confidence/empty): '{plate_text}' (conf: {ocr_confidence:.2f})")
    
    print(f"\n📊 Filtering results:")
    print(f"   Readable plates: {len(readable_plates)} - {readable_plates}")
    print(f"   Unreadable plates: {len(unreadable_plates)} - {unreadable_plates}")
    
    if len(readable_plates) == 0:
        print(f"\n✅ CORRECT BEHAVIOR: No violations should be created because all plates are UNREAD")
        print(f"   The system should create an OCR failure notification instead")
    else:
        print(f"\n❌ PROBLEM: {len(readable_plates)} violations would be created incorrectly")
        print(f"   These plates should have been filtered out: {readable_plates}")

if __name__ == "__main__":
    test_current_logic()