#!/usr/bin/env python3
"""
Test script to verify OCR results are properly formatted for API
"""
import json

# Simulate the detection data that would be sent to API
def test_ocr_formatting():
    print("🧪 Testing OCR API Data Formatting")
    print("=" * 50)
    
    # Simulate plate detections with OCR results (like from laptop_snap.py)
    plate_dets = [
        {
            "confidence": 0.8,
            "bbox": {"x1": 100, "y1": 200, "x2": 150, "y2": 220},
            "text": "ABC123",  # This should become plate_text
            "ocr_confidence": 0.65,
            "ocr_metadata": {
                "processing_method": "basic_easyocr",
                "image_quality_score": 65.0,
                "blur_score": 50.0
            }
        },
        {
            "confidence": 0.7,
            "bbox": {"x1": 200, "y1": 300, "x2": 250, "y2": 320},
            "text": "",  # Empty OCR result
            "ocr_confidence": 0.0,
            "ocr_metadata": {}
        },
        {
            "confidence": 0.9,
            "bbox": {"x1": 300, "y1": 400, "x2": 350, "y2": 420},
            "text": "XYZ789",  # Good OCR result
            "ocr_confidence": 0.82,
            "ocr_metadata": {
                "processing_method": "basic_easyocr",
                "image_quality_score": 82.0,
                "blur_score": 30.0
            }
        }
    ]
    
    # Format detections like laptop_snap.py does
    all_detections = []
    
    for det in plate_dets:
        plate_detection = {
            "model_name": "license_plate",
            "class_name": "license_plate",
            "class": "license_plate",
            "conf": det["confidence"],
            "confidence": det["confidence"],
            "bounding_box": det["bbox"],
            "bbox": det["bbox"],
            "plate_text": det.get("text", ""),  # This is the key field
            "ocr_confidence": det.get("ocr_confidence", 0.0)
        }
        
        # Add enhanced OCR metadata if available
        ocr_metadata = det.get("ocr_metadata", {})
        if ocr_metadata:
            plate_detection["ocr_metadata"] = ocr_metadata
            plate_detection["image_quality_score"] = ocr_metadata.get("image_quality_score", 0.0)
            plate_detection["blur_score"] = ocr_metadata.get("blur_score", 0.0)
        
        all_detections.append(plate_detection)
    
    print("📋 Formatted Detection Data:")
    for i, det in enumerate(all_detections):
        print(f"\n  Plate {i+1}:")
        print(f"    plate_text: '{det['plate_text']}'")
        print(f"    ocr_confidence: {det['ocr_confidence']:.2f}")
        print(f"    bbox: {det['bbox']}")
        
        # Check if this would pass violation creation criteria
        plate_text = det.get('plate_text', '').strip()
        ocr_confidence = det.get('ocr_confidence', 0.0)
        
        if plate_text and len(plate_text) >= 3 and ocr_confidence >= 0.3:
            if not plate_text.startswith('UNREAD') and not plate_text.startswith('UNKNOWN'):
                print(f"    ✅ WOULD CREATE VIOLATION: {plate_text}")
            else:
                print(f"    ❌ PLACEHOLDER TEXT: {plate_text}")
        else:
            print(f"    ❌ WOULD NOT CREATE VIOLATION: text='{plate_text}', conf={ocr_confidence:.2f}")
    
    # Test the full metadata structure
    metadata = {
        "timestamp": "2026-04-11T20:30:00.000Z",
        "camera_id": "SMOKi_Camera_01",
        "location": "Main Camera Station",
        "frame_number": 150,
        "detections": all_detections,
        "smoke_count": 1,
        "vehicle_count": 2,
        "plate_count": len(all_detections),
        "is_violation": True
    }
    
    print(f"\n📤 Full Metadata Structure:")
    print(f"  Total detections: {len(metadata['detections'])}")
    print(f"  Plates with text: {sum(1 for d in metadata['detections'] if d.get('plate_text'))}")
    print(f"  Plates with conf >= 0.3: {sum(1 for d in metadata['detections'] if d.get('ocr_confidence', 0) >= 0.3)}")
    
    # Show JSON structure (truncated)
    print(f"\n📄 JSON Sample:")
    sample_json = json.dumps(metadata, indent=2)[:500] + "..."
    print(sample_json)

if __name__ == "__main__":
    test_ocr_formatting()