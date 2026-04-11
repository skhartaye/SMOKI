#!/usr/bin/env python3
"""
Monitor API calls to see what detection data is being sent
"""
import requests
import json
from datetime import datetime

API_URL = 'https://smoki-backend-rpi.onrender.com'

def check_recent_detections():
    """Check recent detections from the API"""
    try:
        response = requests.get(f"{API_URL}/api/vehicles/detections", timeout=10)
        if response.status_code == 200:
            data = response.json()
            detections = data.get('detections', [])
            
            print(f"📊 Recent detections: {len(detections)}")
            
            for i, detection in enumerate(detections[:5]):  # Show last 5
                timestamp = detection.get('timestamp', 'unknown')
                location = detection.get('location', 'unknown')
                metadata = detection.get('metadata', {})
                
                # Parse detections from metadata
                detection_data = metadata.get('detections', [])
                smoke_count = sum(1 for d in detection_data if 'smoke' in d.get('class_name', '').lower())
                vehicle_count = sum(1 for d in detection_data if d.get('class_name', '').lower() in ['passenger', 'puv', 'services', 'two_wheel', 'vehicle'])
                plate_count = sum(1 for d in detection_data if 'license' in d.get('class_name', '').lower() or 'plate' in d.get('class_name', '').lower())
                
                print(f"  {i+1}. {timestamp} - {location}")
                print(f"     Smoke: {smoke_count}, Vehicles: {vehicle_count}, Plates: {plate_count}")
                
                # Show plate details
                for d in detection_data:
                    if 'license' in d.get('class_name', '').lower() or 'plate' in d.get('class_name', '').lower():
                        plate_text = d.get('plate_text', 'empty')
                        ocr_conf = d.get('ocr_confidence', 0.0)
                        print(f"       Plate: '{plate_text}' (conf: {ocr_conf:.2f})")
        else:
            print(f"❌ Failed to get detections: {response.status_code}")
    
    except Exception as e:
        print(f"❌ Error checking detections: {e}")

def check_recent_violations():
    """Check recent violations from the API"""
    try:
        response = requests.get(f"{API_URL}/api/vehicles/violations", timeout=10)
        if response.status_code == 200:
            data = response.json()
            violations = data.get('violations', [])
            
            print(f"\n📊 Recent violations: {len(violations)}")
            
            for i, violation in enumerate(violations[:5]):  # Show last 5
                license_plate = violation.get('license_plate', 'unknown')
                vehicle_type = violation.get('vehicle_type', 'unknown')
                violation_type = violation.get('violation_type', 'unknown')
                status = violation.get('status', 'unknown')
                created_at = violation.get('created_at', 'unknown')
                
                print(f"  {i+1}. {license_plate} ({vehicle_type}) - {violation_type} - {status}")
                print(f"     Created: {created_at}")
        else:
            print(f"❌ Failed to get violations: {response.status_code}")
    
    except Exception as e:
        print(f"❌ Error checking violations: {e}")

def check_vehicle_ranking():
    """Check vehicle ranking from the API"""
    try:
        response = requests.get(f"{API_URL}/api/vehicles/ranking", timeout=10)
        if response.status_code == 200:
            data = response.json()
            vehicles = data.get('vehicles', [])
            
            print(f"\n📊 Vehicle ranking: {len(vehicles)} vehicles")
            
            for i, vehicle in enumerate(vehicles[:5]):  # Show top 5
                license_plate = vehicle.get('license_plate', 'unknown')
                vehicle_type = vehicle.get('vehicle_type', 'unknown')
                total_violations = vehicle.get('total_violations', 0)
                
                print(f"  {i+1}. {license_plate} ({vehicle_type}) - {total_violations} violations")
        else:
            print(f"❌ Failed to get ranking: {response.status_code}")
    
    except Exception as e:
        print(f"❌ Error checking ranking: {e}")

if __name__ == "__main__":
    print("🔍 Monitoring API State")
    print("=" * 40)
    
    check_recent_detections()
    check_recent_violations()
    check_vehicle_ranking()