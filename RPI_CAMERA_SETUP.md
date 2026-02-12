# RPi4 Camera Integration Guide

This document provides setup instructions for integrating the RPi4 camera with the SMOKI vehicle emission monitoring system.

## Project Overview

**SMOKI** is an IoT-based air quality and vehicle emission monitoring system with three main components:

1. **AeroBand** - ESP32-based air quality sensor network
2. **SMOKI** - RPi5 with camera for vehicle detection and smoke emission analysis
3. **Dashboard** - Web interface for monitoring and violation tracking

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SMOKI Dashboard (Web)                    │
│  - Real-time vehicle detection                              │
│  - Top Violators display                                    │
│  - Violation rankings                                       │
│  - Notification ribbon alerts                               │
└─────────────────────────────────────────────────────────────┘
                            ↑
                    PostgreSQL Database
                            ↑
        ┌───────────────────┼───────────────────┐
        ↓                   ↓                   ↓
   ┌─────────┐         ┌─────────┐         ┌─────────┐
   │ AeroBand│         │  SMOKI  │         │ Backend │
   │ (ESP32) │         │ (RPi5)  │         │ (FastAPI)
   │ Sensors │         │ Camera  │         │ Server  │
   └─────────┘         └─────────┘         └─────────┘
```

## RPi4 Camera Setup (Preparation for RPi5)

### Hardware Requirements

- Raspberry Pi 4 (or RPi5 for production)
- RPi Camera Module v2 or v3
- Hailo-8 AI Accelerator (for vehicle detection)
- Power supply (5V 3A minimum)
- MicroSD card (32GB recommended)

### Software Installation

#### 1. Install Raspberry Pi OS

```bash
# Download and flash Raspberry Pi OS Lite (64-bit) to microSD card
# Using Raspberry Pi Imager or balena Etcher
```

#### 2. Enable Camera Interface

```bash
sudo raspi-config
# Navigate to: Interface Options → Camera → Enable
# Reboot when prompted
```

#### 3. Install Required Libraries

```bash
sudo apt update
sudo apt upgrade -y

# Install Python and pip
sudo apt install -y python3-pip python3-dev

# Install camera libraries
sudo apt install -y libatlas-base-dev libjasper-dev libtiff5 libjasper1 libharfbuzz0b libwebp6 libtiff5 libjasper1 libharfbuzz0b libwebp6 libopenjp2-7 libtiff5

# Install picamera2 (modern camera library)
sudo apt install -y -o APT::Immediate-Configure=false python3-picamera2

# Install OpenCV
pip3 install opencv-python

# Install Hailo runtime (if using Hailo accelerator)
pip3 install hailo-sdk-common
```

#### 4. Install Backend Dependencies

```bash
cd backend
pip3 install -r requirements.txt
```

## API Endpoints for Vehicle Detection

### 1. Register Vehicle Detection

**Endpoint:** `POST /api/vehicles/detect`

**Request:**
```json
{
  "license_plate": "ABC-123",
  "vehicle_type": "sedan",
  "location": "Main Street",
  "confidence": 0.95,
  "smoke_detected": true,
  "emission_level": "high",
  "image_path": "/path/to/image.jpg",
  "metadata": {
    "timestamp": "2024-02-12T10:30:00Z",
    "camera_id": "cam_001"
  }
}
```

**Response:**
```json
{
  "success": true,
  "vehicle_id": 1,
  "detection_id": 42,
  "license_plate": "ABC-123",
  "violations": 5
}
```

### 2. Report Violation

**Endpoint:** `POST /api/vehicles/violation`

**Request:**
```json
{
  "license_plate": "ABC-123",
  "violation_type": "excessive_smoke",
  "severity": "critical",
  "description": "Heavy smoke emission detected"
}
```

**Response:**
```json
{
  "success": true,
  "violation_id": 10,
  "notification_id": 25,
  "license_plate": "ABC-123"
}
```

### 3. Get Top Violators

**Endpoint:** `GET /api/vehicles/top-violators?limit=5`

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "license_plate": "ABC-123",
      "vehicle_type": "sedan",
      "violations": 24,
      "last_detected": "2024-02-12T10:30:00Z",
      "emission_level": "high",
      "smoke_detected": true
    }
  ],
  "count": 1
}
```

### 4. Get Vehicle Ranking

**Endpoint:** `GET /api/vehicles/ranking`

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "license_plate": "ABC-123",
      "vehicle_type": "sedan",
      "violations": 24,
      "last_detected": "2024-02-12T10:30:00Z",
      "status": "active"
    }
  ],
  "count": 1
}
```

### 5. Get Unread Notifications

**Endpoint:** `GET /api/vehicles/notifications/unread?limit=10`

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": 25,
      "title": "Violation: ABC-123",
      "message": "excessive_smoke - Heavy smoke emission detected",
      "notification_type": "violation",
      "timestamp": "2024-02-12T10:30:00Z",
      "severity": "critical",
      "license_plate": "ABC-123"
    }
  ],
  "count": 1
}
```

## Python Script Example for RPi Camera

Create `rpi_camera_stream.py`:

```python
#!/usr/bin/env python3
import requests
import cv2
from picamera2 import Picamera2
import numpy as np
import time
from datetime import datetime

# Configuration
API_URL = "http://localhost:8000"
AUTH_TOKEN = "your_jwt_token_here"
CAMERA_ID = "cam_001"

class VehicleDetector:
    def __init__(self):
        self.picam2 = Picamera2()
        config = self.picam2.create_preview_configuration(
            main={"format": 'XRGB8888', "size": (1280, 720)}
        )
        self.picam2.configure(config)
        self.picam2.start()
        
    def detect_vehicles(self, frame):
        """
        Placeholder for vehicle detection using Hailo or OpenCV
        Replace with actual detection model
        """
        # This would use Hailo or YOLO for actual detection
        detections = []
        return detections
    
    def send_detection(self, license_plate, confidence, smoke_detected, emission_level):
        """Send detection to backend"""
        try:
            payload = {
                "license_plate": license_plate,
                "vehicle_type": "unknown",
                "location": "Main Street",
                "confidence": confidence,
                "smoke_detected": smoke_detected,
                "emission_level": emission_level,
                "metadata": {
                    "timestamp": datetime.now().isoformat(),
                    "camera_id": CAMERA_ID
                }
            }
            
            headers = {
                "Authorization": f"Bearer {AUTH_TOKEN}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(
                f"{API_URL}/api/vehicles/detect",
                json=payload,
                headers=headers
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"Detection recorded: {result}")
                return result
            else:
                print(f"Error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"Error sending detection: {e}")
            return None
    
    def run(self):
        """Main detection loop"""
        print("Starting vehicle detection...")
        
        try:
            while True:
                frame = self.picam2.capture_array()
                
                # Detect vehicles
                detections = self.detect_vehicles(frame)
                
                # Process detections
                for detection in detections:
                    license_plate = detection.get('license_plate')
                    confidence = detection.get('confidence', 0.0)
                    smoke_detected = detection.get('smoke_detected', False)
                    emission_level = detection.get('emission_level', 'normal')
                    
                    # Send to backend
                    self.send_detection(
                        license_plate,
                        confidence,
                        smoke_detected,
                        emission_level
                    )
                
                time.sleep(0.1)  # 10 FPS
                
        except KeyboardInterrupt:
            print("Stopping detection...")
        finally:
            self.picam2.stop()

if __name__ == "__main__":
    detector = VehicleDetector()
    detector.run()
```

## Database Schema

The system uses PostgreSQL with the following tables:

- **vehicles** - Registered vehicles with violation counts
- **vehicle_detections** - Individual detection records
- **violations** - Violation records with severity levels
- **notifications** - Real-time alerts for violations

See `postgre/database.py` for complete schema.

## Frontend Features

### Dashboard Components

1. **Top Violators** - Real-time display of vehicles with highest emissions
2. **Violators Ranking** - Ranked list of all detected vehicles
3. **Notification Ribbon** - Pop-up alerts for new violations
4. **Camera Feed** - Live stream placeholder (ready for integration)

### Notification System

- Real-time violation alerts
- Auto-dismiss after 8 seconds
- Color-coded severity levels (Critical, Warning, Info)
- License plate highlighting

## Deployment Steps

### 1. On RPi4/RPi5

```bash
# Clone repository
git clone https://github.com/skhartaye/SMOKI.git
cd SMOKI

# Install dependencies
cd backend
pip3 install -r requirements.txt

# Run backend server
python3 -m uvicorn main:app --reload --host 0.0.0.0 --port 8080

# In another terminal, run camera detection
python3 rpi_camera_stream.py
```

### 2. On Frontend Server

```bash
cd frontend
npm install
npm run dev
```

### 3. Access Dashboard

Open browser and navigate to:
```
http://your-rpi-ip:5173
```

## Testing

### Test Vehicle Detection

```bash
curl -X POST http://localhost:8000/api/vehicles/detect \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "license_plate": "TEST-001",
    "vehicle_type": "sedan",
    "location": "Test Location",
    "confidence": 0.95,
    "smoke_detected": true,
    "emission_level": "high"
  }'
```

### Test Violation Report

```bash
curl -X POST http://localhost:8000/api/vehicles/violation \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "license_plate": "TEST-001",
    "violation_type": "excessive_smoke",
    "severity": "critical",
    "description": "Test violation"
  }'
```

## Next Steps

1. **Integrate Hailo AI** - Add vehicle detection model
2. **Implement MJPEG Streaming** - Live camera feed to dashboard
3. **Add Smoke Detection** - ML model for smoke emission analysis
4. **Mobile App** - React Native companion app
5. **Cloud Integration** - AWS/Azure backend for multi-site deployment

## Troubleshooting

### Camera Not Detected

```bash
# Check camera connection
vcgencmd get_camera

# Enable camera in raspi-config
sudo raspi-config
```

### API Connection Issues

```bash
# Check backend is running
curl http://localhost:8000/api/hello

# Check firewall
sudo ufw allow 8000
```

### Database Connection

```bash
# Test PostgreSQL connection
psql -h localhost -U postgres -d smoki_db
```

## Support

For issues or questions, please refer to:
- Backend: `backend/README.md`
- Frontend: `frontend/README.md`
- Database: `postgre/README.md`
