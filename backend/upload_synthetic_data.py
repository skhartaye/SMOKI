#!/usr/bin/env python3
"""
Script to upload synthetic sensor data to the SMOKi system
"""
import requests
import json
from datetime import datetime, timedelta
import random

# Configuration
API_URL = "http://127.0.0.1:8000"
NUM_RECORDS = 50  # Number of synthetic records to create

def generate_synthetic_data(hours_ago=0):
    """Generate realistic synthetic sensor data"""
    timestamp = datetime.now() - timedelta(hours=hours_ago)
    
    # Generate realistic sensor values
    temperature = random.uniform(18, 32)  # 18-32°C
    humidity = random.uniform(30, 70)  # 30-70%
    pressure = random.uniform(1000, 1020)  # 1000-1020 hPa
    vocs = random.uniform(20, 150)  # 20-150 kΩ
    nitrogen_dioxide = random.uniform(0.01, 0.15)  # 0.01-0.15 PPM
    carbon_monoxide = random.uniform(0.1, 5)  # 0.1-5 PPM
    pm25 = random.uniform(5, 50)  # 5-50 µg/m³
    pm10 = random.uniform(10, 100)  # 10-100 µg/m³
    
    return {
        "temperature": round(temperature, 2),
        "humidity": round(humidity, 2),
        "pressure": round(pressure, 2),
        "vocs": round(vocs, 2),
        "nitrogen_dioxide": round(nitrogen_dioxide, 4),
        "carbon_monoxide": round(carbon_monoxide, 2),
        "pm25": round(pm25, 2),
        "pm10": round(pm10, 2)
    }

def upload_data():
    """Upload synthetic data to the API"""
    print(f"Starting to upload {NUM_RECORDS} synthetic sensor records...")
    print(f"API URL: {API_URL}")
    
    success_count = 0
    error_count = 0
    
    for i in range(NUM_RECORDS):
        try:
            # Generate data for different time points (spread over the last 24 hours)
            hours_ago = (NUM_RECORDS - i - 1) * (24 / NUM_RECORDS)
            data = generate_synthetic_data(hours_ago)
            
            # Send POST request
            response = requests.post(
                f"{API_URL}/api/sensors/data",
                json=data,
                timeout=5
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    success_count += 1
                    print(f"✓ Record {i+1}/{NUM_RECORDS} uploaded successfully")
                else:
                    error_count += 1
                    print(f"✗ Record {i+1}/{NUM_RECORDS} failed: {result.get('detail', 'Unknown error')}")
            else:
                error_count += 1
                print(f"✗ Record {i+1}/{NUM_RECORDS} failed with status {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            error_count += 1
            print(f"✗ Record {i+1}/{NUM_RECORDS} failed: {str(e)}")
        except Exception as e:
            error_count += 1
            print(f"✗ Record {i+1}/{NUM_RECORDS} failed: {str(e)}")
    
    print("\n" + "="*50)
    print(f"Upload Summary:")
    print(f"  Successful: {success_count}")
    print(f"  Failed: {error_count}")
    print(f"  Total: {NUM_RECORDS}")
    print("="*50)

if __name__ == "__main__":
    upload_data()
