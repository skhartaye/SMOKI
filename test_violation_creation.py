#!/usr/bin/env python3
"""
Test script to verify violation creation logic
"""
import json
from datetime import datetime, timezone

def test_violation_criteria():
    print("🧪 Testing Violation Creation Criteria")
    print("=" * 50)
    
    # Test case 1: Smoke + Vehicles + Good OCR
    print("\n📋 Test Case 1: Smoke + Vehicles + Good OCR")
    detections_1 = [
        {
            "model_name": "smoke_detection",
            "class_name": "smoke_black",
            "confidence": 0.6,
            "bbox": {"x1": 100, "y1": 100, "x2": 200, "y2": 200}
        },
        {
            "model_name": "vehicle_detection", 
            "class_name": "puv",
            "confidence": 0.8,
            "bbox": {"x1": 150, "y1": 150, "x2": 300, "y2": 300}
        },
        {
            "model_name": "license_plate",
            "class_name": "license_plate",
            "confidence": 0.7,
            "bbox": {"x1": 200, "y1": 200, "x2": 250, "y2": 220},
            "plate_text": "ABC123",
            "ocr_confidence": 0.65
        }
    ]
    
    result_1 = analyze_detections(detections_1)
    print(f"  Result: {result_1}")
    
    # Test case 2: Smoke + Vehicles + Poor OCR
    print("\n📋 Test Case 2: Smoke + Vehicles + Poor OCR")
    detections_2 = [
        {
            "model_name": "smoke_detection",
            "class_name": "smoke_white",
            "confidence": 0.4,
            "bbox": {"x1": 100, "y1": 100, "x2": 200, "y2": 200}
        },
        {
            "model_name": "vehicle_detection",
            "class_name": "two_wheel", 
            "confidence": 0.9,
            "bbox": {"x1": 150, "y1": 150, "x2": 300, "y2": 300}
        },
        {
            "model_name": "license_plate",
            "class_name": "license_plate",
            "confidence": 0.5,
            "bbox": {"x1": 200, "y1": 200, "x2": 250, "y2": 220},
            "plate_text": "",
            "ocr_confidence": 0.0
        }
    ]
    
    result_2 = analyze_detections(detections_2)
    print(f"  Result: {result_2}")
    
    # Test case 3: No Smoke
    print("\n📋 Test Case 3: No Smoke")
    detections_3 = [
        {
            "model_name": "vehicle_detection",
            "class_name": "passenger",
            "confidence": 0.85,
            "bbox": {"x1": 150, "y1": 150, "x2": 300, "y2": 300}
        },
        {
            "model_name": "license_plate",
            "class_name": "license_plate", 
            "confidence": 0.8,
            "bbox": {"x1": 200, "y1": 200, "x2": 250, "y2": 220},
            "plate_text": "XYZ789",
            "ocr_confidence": 0.75
        }
    ]
    
    result_3 = analyze_detections(detections_3)
    print(f"  Result: {result_3}")

def analyze_detections(detections):
    """Simulate the violation creation logic"""
    
    # Group detections by type (like in create_targeted_violations)
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
    
    print(f"    Smoke: {len(smoke_detections)}, Vehicles: {len(vehicle_detections)}, Plates: {len(plate_detections)}")
    
    # Check violation creation criteria
    if not smoke_detections:
        return "❌ NO VIOLATION - No smoke detected"
    
    if not plate_detections:
        return "⚠️  OCR FAILURE NOTIFICATION - Smoke + vehicles but no plates"
    
    # Find readable license plates
    readable_plates = []
    for plate in plate_detections:
        plate_text = plate.get('plate_text', '').strip()
        ocr_confidence = plate.get('ocr_confidence', 0.0)
        
        if plate_text and len(plate_text) >= 3 and ocr_confidence >= 0.3:
            if not plate_text.startswith('UNREAD') and not plate_text.startswith('UNKNOWN'):
                readable_plates.append(plate_text)
    
    if not readable_plates:
        return "⚠️  OCR FAILURE NOTIFICATION - Plates detected but unreadable"
    
    return f"✅ VIOLATION CREATED - Plates: {readable_plates}"

if __name__ == "__main__":
    test_violation_criteria()