# SMOKI Project - COMPLETE Source Code Dump

## Project Structure

```
smoki_project/
├── frontend/                    # React + Vite frontend
│   ├── src/
│   │   ├── App.jsx             # Login page
│   │   ├── Dashboard.jsx       # Main dashboard (2842 lines)
│   │   ├── main.jsx            # React entry point
│   │   ├── index.css           # Global styles
│   │   ├── utils/
│   │   │   ├── apiClient.js    # API client with fallback
│   │   │   └── toastUtils.js   # Toast notifications
│   │   ├── context/
│   │   │   └── SensorStatusContext.jsx  # Global sensor status
│   │   ├── component/          # React components
│   │   │   ├── CameraViewer.jsx
│   │   │   ├── WebRTCViewer.jsx
│   │   │   ├── SensorStatusRibbon.jsx
│   │   │   ├── NotificationRibbon.jsx
│   │   │   ├── ConfirmModal.jsx
│   │   │   ├── SensorDetailModal.jsx
│   │   │   ├── TriangleLoader.jsx
│   │   │   ├── TutorialModal.jsx
│   │   │   ├── Toast.jsx
│   │   │   ├── ProtectedRoute.jsx
│   │   │   ├── DataTimeoutModal.jsx
│   │   │   └── IOSIcons.jsx
│   │   └── styles/             # CSS files
│   │       ├── App.css
│   │       ├── Dashboard.css
│   │       ├── CameraViewer.css
│   │       ├── main.css
│   │       └── ... (other component styles)
│   ├── .env                    # Environment variables
│   ├── package.json
│   └── vite.config.js
│
├── backend/                    # FastAPI backend
│   ├── main.py                # Main FastAPI app
│   ├── auth.py                # JWT authentication
│   ├── stream.py              # HLS streaming
│   ├── vehicles.py            # Vehicle detection endpoints
│   ├── webrtc_proxy.py        # WebRTC proxy
│   ├── .env                   # Environment variables
│   ├── requirements.txt
│   └── package.json
│
├── postgre/                   # Database
│   ├── database.py            # All database operations
│   ├── .env                   # Database credentials
│   └── requirements.txt
│
├── esp32/                     # RPi edge device
│   ├── rpi_stream.py          # Main inference pipeline
│   ├── test_hailo.py          # Hailo diagnostics
│   ├── .env.rpi               # RPi environment
│   ├── RPi_SETUP.md           # Setup instructions
│   └── requirements_rpi.txt
│
└── README.md                  # Project documentation
```

## Key Files Summary

### 1. Backend (FastAPI)

**backend/main.py** - 400+ lines
- Authentication endpoints
- Detection endpoints (smoke, vehicle, summary)
- Sensor data endpoints
- Health check endpoints

**backend/auth.py** - 150+ lines
- JWT token creation/verification
- Password hashing with bcrypt
- User authentication
- Role-based access control

**backend/stream.py** - 150+ lines
- HLS stream management
- MJPEG streaming
- Frame buffering
- Stream status endpoints

**backend/vehicles.py** - 150+ lines
- Vehicle detection recording
- Violation management
- Notification system
- Vehicle ranking

**backend/webrtc_proxy.py** - 50+ lines
- WebRTC signaling proxy
- WebSocket forwarding to RPi

### 2. Frontend (React)

**frontend/src/App.jsx** - 100+ lines
- Login page
- Authentication form
- Error handling

**frontend/src/Dashboard.jsx** - 2842 lines (LARGE FILE)
- Main dashboard interface
- Sensor data display
- Graph visualization
- Records management
- Vehicle violation tracking
- Dark mode support
- Mobile responsive design

**frontend/src/main.jsx** - 30 lines
- React entry point
- Router setup
- Context providers

**frontend/src/utils/apiClient.js** - 100+ lines
- Centralized API client
- Automatic fallback logic
- Helper functions (GET, POST, PUT, DELETE)

**frontend/src/context/SensorStatusContext.jsx** - 50+ lines
- Global sensor status state
- Last update tracking
- Connection status

### 3. Database (PostgreSQL)

**postgre/database.py** - 1100+ lines
- Table creation
- Sensor data operations
- Vehicle management
- Detection recording
- Violation tracking
- Notification system
- Image storage
- Detection summary functions (NEW)

### 4. RPi Edge Device (Python)

**esp32/rpi_stream.py** - 800+ lines
- Picamera2 integration
- Hailo AI inference
- Multi-model execution
- HLS streaming via FFmpeg
- CPU fallback mode
- Detection metadata sending
- Resource cleanup

**esp32/test_hailo.py** - 50+ lines
- Hailo device diagnostics
- Hardware availability check

## API Endpoints

### Authentication
- `POST /api/auth/login` - User login
- `GET /api/auth/me` - Get current user

### Detections
- `POST /api/detections/smoke` - Record smoke detection
- `GET /api/detections/smoke` - Get smoke detections (auth)
- `POST /api/detections/vehicle` - Record vehicle detection
- `GET /api/detections/vehicle/recent` - Get vehicle detections (auth)
- `POST /api/detections/summary` - Record detection summary
- `GET /api/detections/summary/recent` - Get summaries (auth)

### Sensors
- `POST /api/sensors/data` - Add sensor reading
- `GET /api/sensors/data` - Get sensor readings
- `GET /api/sensors/latest` - Get latest reading
- `GET /api/sensors/status` - Get sensor status
- `PUT /api/sensors/data/{id}` - Update reading (admin)
- `DELETE /api/sensors/data/{id}` - Delete reading (admin)

### Vehicles
- `POST /api/vehicles/detect` - Record vehicle detection
- `POST /api/vehicles/violation` - Report violation
- `GET /api/vehicles/top-violators` - Get top violators
- `GET /api/vehicles/ranking` - Get vehicle ranking
- `GET /api/vehicles/violations/recent` - Get recent violations
- `GET /api/vehicles/notifications/unread` - Get notifications
- `POST /api/vehicles/notifications/{id}/read` - Mark as read

### Streaming
- `POST /api/stream/frame` - Receive frame
- `GET /api/stream/stream.mjpeg` - MJPEG stream
- `GET /api/stream/latest.jpg` - Latest frame
- `GET /api/stream/status` - Stream status
- `GET /api/stream/hls-proxy` - HLS proxy

### Health
- `GET /api/health` - Backend health
- `GET /api/camera/health` - Camera health
- `GET /api/time` - Server time

## Database Schema

### detection_summaries (NEW)
```sql
CREATE TABLE detection_summaries (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE,
    camera_id VARCHAR(255),
    location VARCHAR(255),
    detection_count INT,
    smoke_count INT,
    vehicle_count INT,
    mode VARCHAR(50),  -- 'hailo' or 'cpu'
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### Other Tables
- `users` - User accounts with roles
- `sensor_data` - Environmental sensor readings
- `vehicles` - Vehicle registry
- `vehicle_detections` - Individual detections
- `smoke_detections` - Smoke detection records
- `violations` - Traffic violations
- `notifications` - User notifications
- `images` - Stored detection frames
- `image_metadata` - Image metadata

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
SECRET_KEY=your-secret-key
```

### RPi (.env.rpi)
```
BACKEND_URL=http://192.168.1.20:8000
CAMERA_ID=rpi_camera_01
CAMERA_LOCATION=unknown
HEF_PATH=/home/sevi/smoki_project/src/model-skhart-ready/smoke-seg-v3.hef
```

## Key Features

1. **API Fallback System**
   - Primary: Render backend
   - Fallback: Local RPi IP
   - Automatic switching on failure

2. **Multi-Model Inference**
   - Smoke segmentation
   - License plate detection
   - Vehicle classification
   - Sequential execution on Hailo

3. **CPU Fallback Mode**
   - Streams video without inference
   - Watermark: "CPU Mode - No Inference"
   - Sends detection summaries with mode="cpu"

4. **Real-Time Streaming**
   - HLS via FFmpeg
   - MJPEG streaming
   - WebRTC support
   - Low-latency encoding

5. **Detection Metadata**
   - Sent every ~2 seconds
   - Includes: total, smoke, vehicle counts
   - Stored in database
   - Accessible via API

6. **Authentication**
   - JWT tokens
   - Role-based access control
   - Bcrypt password hashing
   - 24-hour token expiry

7. **Responsive UI**
   - Mobile-friendly design
   - Dark mode support
   - Real-time updates
   - Toast notifications

## Deployment

- **Frontend**: Netlify (auto-deploy)
- **Backend**: Render (auto-deploy)
- **Database**: PostgreSQL (Render)
- **RPi**: Local network

## Testing

### Test Detection Summary
```bash
curl -X POST http://localhost:8000/api/detections/summary \
  -H "Content-Type: application/json" \
  -d '{
    "timestamp": "2026-03-26T10:57:23.123456+00:00",
    "camera_id": "rpi_camera_01",
    "location": "test",
    "detection_count": 5,
    "smoke_count": 1,
    "vehicle_count": 4,
    "mode": "hailo"
  }'
```

### Test API Fallback
```javascript
import { fetchWithFallback, getCurrentApiUrl } from './utils/apiClient.js';
const response = await fetchWithFallback('/api/sensors/status');
console.log('Using API:', getCurrentApiUrl());
```

## File Statistics

- **Total Python Files**: 10+
- **Total JavaScript/JSX Files**: 20+
- **Total CSS Files**: 15+
- **Total Lines of Code**: 10,000+
- **Database Tables**: 10+
- **API Endpoints**: 30+

## Recent Updates

1. Detection summary system (lightweight metadata)
2. API fallback logic (centralized client)
3. CPU fallback mode (video without inference)
4. Resource cleanup (camera/FFmpeg)
5. Multi-model inference (sequential execution)

## Known Issues

1. **Hailo Device Not Detected**
   - Error: HAILO_OUT_OF_PHYSICAL_DEVICES (74)
   - Workaround: CPU fallback mode

2. **Camera Resource Busy**
   - Error: Failed to acquire camera
   - Fix: Proper cleanup in finally block

3. **Backend 404 on Vehicle Detections**
   - Cause: Endpoint requires authentication
   - Fix: Include JWT token

## Next Steps

1. Test CPU fallback mode
2. Verify detection summaries storage
3. Update frontend dashboard
4. Implement real-time statistics
5. Add WebRTC fallback
6. Implement detection alerts

---

**Last Updated**: March 26, 2026
**Status**: In Development
**Focus**: Testing fallback systems and detection metadata
