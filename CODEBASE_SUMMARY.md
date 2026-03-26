# SMOKI Project - Complete Source Code Summary

## Project Overview
SMOKI is a real-time smoke and vehicle detection system using:
- **Frontend**: React + Vite (deployed on Netlify)
- **Backend**: FastAPI + PostgreSQL (deployed on Render)
- **RPi Edge Device**: Hailo AI accelerator + Picamera2 for real-time inference
- **Fallback Mode**: CPU-based streaming when Hailo unavailable

## Architecture

### 1. Frontend (React/Vite)
- **Location**: `frontend/src/`
- **Key Components**:
  - `App.jsx` - Main app with routing
  - `Dashboard.jsx` - Main dashboard view
  - `CameraViewer.jsx` - HLS stream viewer
  - `WebRTCViewer.jsx` - WebRTC fallback viewer
  - `SensorStatusContext.jsx` - Global sensor status state
  - `SensorStatusRibbon.jsx` - Status indicator
  - `NotificationRibbon.jsx` - Real-time notifications

- **API Client**: `frontend/src/utils/apiClient.js`
  - Centralized API client with automatic fallback
  - Primary: `https://smoki-backend.onrender.com`
  - Fallback: `http://192.168.1.35:8000` (local RPi IP)

### 2. Backend (FastAPI)
- **Location**: `backend/`
- **Main File**: `backend/main.py`
- **Key Endpoints**:
  - `POST /api/detections/smoke` - Record smoke detections
  - `POST /api/detections/vehicle` - Record vehicle detections with frame
  - `POST /api/detections/summary` - Record detection summaries (NEW)
  - `GET /api/detections/summary/recent` - Get recent summaries
  - `GET /api/detections/vehicle/recent` - Get recent vehicle detections
  - `GET /api/sensors/status` - Get sensor connection status
  - `POST /api/sensors/data` - Add sensor readings
  - `GET /api/auth/login` - User authentication

### 3. Database (PostgreSQL)
- **Location**: `postgre/database.py`
- **Key Tables**:
  - `sensor_data` - Environmental sensor readings
  - `vehicles` - Vehicle registry
  - `vehicle_detections` - Individual detection records
  - `smoke_detections` - Smoke detection records
  - `detection_summaries` - Lightweight detection metadata (NEW)
  - `violations` - Traffic violations
  - `notifications` - User notifications
  - `images` - Stored detection frames
  - `users` - User accounts with roles

### 4. RPi Edge Device (Python)
- **Location**: `esp32/rpi_stream.py`
- **Key Features**:
  - Real-time video capture via Picamera2
  - Multi-model inference (smoke, license plate, vehicle classification)
  - HLS streaming via FFmpeg
  - Hailo AI accelerator support
  - CPU fallback mode when Hailo unavailable
  - Detection metadata sent to backend every ~2 seconds

## Key Files

### Frontend
- `frontend/src/utils/apiClient.js` - API client with fallback logic
- `frontend/.env` - Environment variables with API URLs
- `frontend/src/context/SensorStatusContext.jsx` - Global state management

### Backend
- `backend/main.py` - FastAPI application with all endpoints
- `backend/auth.py` - JWT authentication
- `backend/stream.py` - HLS streaming router
- `backend/vehicles.py` - Vehicle detection router

### Database
- `postgre/database.py` - All database operations and table definitions

### RPi
- `esp32/rpi_stream.py` - Main inference and streaming pipeline
- `esp32/test_hailo.py` - Hailo device diagnostics

## Detection Flow

1. **RPi Captures Frame** → Picamera2 (640x480 @ 15fps)
2. **Hailo Inference** (if available):
   - Smoke segmentation model
   - License plate detection
   - Vehicle classification
3. **CPU Fallback** (if Hailo unavailable):
   - Raw video streaming with "CPU Mode" watermark
4. **Send to Backend**:
   - Full vehicle detections with frame (every detection)
   - Detection summaries (every ~2 seconds)
   - Smoke detections (when detected)
5. **HLS Stream** → FFmpeg encodes to HLS segments
6. **Frontend** → Displays stream + detection metadata

## Detection Summary Schema

```json
{
  "timestamp": "2026-03-26T10:57:23.123456+00:00",
  "camera_id": "rpi_camera_01",
  "location": "unknown",
  "detection_count": 5,
  "smoke_count": 1,
  "vehicle_count": 4,
  "mode": "hailo",
  "metadata": {
    "inference_time_ms": 45
  }
}
```

## API Fallback Logic

The frontend automatically falls back to local RPi IP if Render backend is unavailable:

```javascript
// Try primary API first
fetch('https://smoki-backend.onrender.com/api/...')
  // If fails, try fallback
  .catch(() => fetch('http://192.168.1.35:8000/api/...'))
```

## Environment Variables

### Frontend (.env)
```
VITE_API_URL=https://smoki-backend.onrender.com
VITE_API_URL_FALLBACK=http://192.168.1.35:8000
VITE_RPI_IP=192.168.1.35
```

### Backend (.env)
```
DB_HOST=localhost
DB_NAME=smoki_db
DB_USER=postgres
DB_PASSWORD=password
DB_PORT=5432
```

### RPi (.env.rpi)
```
BACKEND_URL=http://192.168.1.20:8000
CAMERA_ID=rpi_camera_01
CAMERA_LOCATION=unknown
HEF_PATH=/home/sevi/smoki_project/src/model-skhart-ready/smoke-seg-v3.hef
```

## Deployment

- **Frontend**: Netlify (auto-deploy from GitHub)
- **Backend**: Render (auto-deploy from GitHub)
- **Database**: PostgreSQL (Render or self-hosted)
- **RPi**: Local network, runs `python3 rpi_stream.py`

## Recent Updates

1. **API Fallback System** - Centralized client with automatic fallback to local IP
2. **Detection Summaries** - Lightweight metadata sent every ~2 seconds
3. **CPU Fallback Mode** - Streams video without inference when Hailo unavailable
4. **Resource Cleanup** - Fixed camera/FFmpeg cleanup to prevent "Device or resource busy" errors
5. **Multi-Model Inference** - Sequential execution of smoke, license plate, and vehicle models

## Known Issues

- Hailo device not detected on RPi (error 74: HAILO_OUT_OF_PHYSICAL_DEVICES)
  - **Workaround**: CPU fallback mode streams video without inference
- Backend 404 errors on `/api/detections/vehicle/recent`
  - **Cause**: Endpoint requires authentication
  - **Fix**: Frontend should include JWT token in requests

## Next Steps

1. Test CPU fallback mode streaming
2. Verify detection summaries are being stored in database
3. Update frontend to display detection summaries
4. Implement real-time detection dashboard
5. Add WebRTC fallback for low-latency streaming
