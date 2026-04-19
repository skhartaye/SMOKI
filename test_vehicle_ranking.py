#!/usr/bin/env python3
"""
Test vehicle ranking API
"""
import requests

def test_vehicle_ranking():
    """Test the vehicle ranking API"""
    print("🧪 Testing Vehicle Ranking API")
    print("=" * 40)
    
    try:
        response = requests.get('https://smoki-backend-rpi.onrender.com/api/vehicles/ranking')
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            vehicles = data.get('data', [])
            
            print(f"✅ Found {len(vehicles)} vehicles in ranking")
            print("\n🏆 Top Vehicle Violators:")
            
            for i, vehicle in enumerate(vehicles[:5]):  # Show top 5
                plate = vehicle.get('license_plate', 'Unknown')
                vehicle_type = vehicle.get('vehicle_type', 'Unknown')
                violations = vehicle.get('violations', 0)
                status = vehicle.get('status', 'Unknown')
                
                print(f"  {i+1}. {plate} ({vehicle_type}) - {violations} violations [{status}]")
            
            if len(vehicles) == 0:
                print("❌ No vehicles found in ranking")
            
        else:
            print(f"❌ API Error: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_vehicle_ranking()