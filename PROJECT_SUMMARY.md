# SMOKI Project - Complete Setup Summary

## Project Overview

**SMOKI** is a comprehensive IoT-based air quality and vehicle emission monitoring system designed to detect and track vehicles with excessive smoke emissions.

### Three Main Components

1. **AeroBand** - ESP32-based air quality sensor network
   - Measures: Temperature, Humidity, VOCs, NO₂, CO, PM2.5, PM10
   - Real-time data transmission to backend
   - Distributed sensor deployment

2. **SMOKI** - RPi5 vision system (prepared for RPi4)
   - Vehicle detection using Hailo AI accelerator
   - Smoke emission analysis
   - License plate recognition
   - Real-time violation detection

3. **Dashboard** - Web-based monitoring interface
   - Real-time vehicle tracking
   - Top violators display
   - Violation rankings
   - Notification system
   - Dark mode support
   - Mobile responsive design

## What's Been Implemented

### Backend Infrastructure (FastAPI)

✅ **Authentication System**
- JWT token-based authentication
- Role-based access control (Admin, SuperAdmin)
- User management

✅ **Sensor Data Management**
- Air quality sensor data collection
- Time-series data storage
- Data filtering and retrieval

✅ **Vehicle Detection System** (NEW)
- Vehicle registration and tracking
- Detection record storage
- Violation tracking
- Metadata storage (JSON)

✅ **Violation Management** (NEW)
- Violation creation and tracking
- Severity levels (Critical, Warning, Safe)
- Violation history

✅ **Notification System** (NEW)
- Real-time violation alerts
- Notification status tracking
- Unread notification retrieval

### Database (PostgreSQL)

✅ **Tables Created**
- `users` - User accounts and roles
- `sensor_data` - Air quality measurements
- `vehicles` - Vehicle registry
- `vehicle_detections` - Individual detection records
- `violations` - Violation records
- `notifications` - Alert notifications

✅ **Indexes**
- Optimized queries for timestamp-based searches
- Fast vehicle lookup by license plate
- Efficient notification retrieval

### Frontend (React + Vite)

✅ **Dashboard Features**
- Scrollable dashboard with multiple sections
- Real-time data updates
- Dark mode toggle
- Mobile responsive design

✅ **Top Violators Section** (NEW)
- Displays top 3 vehicles with highest violations
- Shows emission levels and smoke detection status
- Color-coded severity badges

✅ **Violators Ranking Section** (NEW)
- Complete ranking of all detected vehicles
- Violation count display
- Status indicators

✅ **Notification Ribbon** (NEW)
- Real-time pop-up alerts
- Auto-dismiss after 8 seconds
- Color-coded by severity
- License plate highlighting
- Dark mode support

✅ **Responsive Design**
- Mobile-optimized layout
- Bottom navigation for mobile
- Scrollable content areas
- Proper spacing and padding

## API Endpoints

### Vehicle Detection
- `POST /api/vehicles/detect` - Record vehicle detection
- `POST /api/vehicles/violation` - Report violation
- `GET /api/vehicles/top-violators` - Get top violators
- `GET /api/vehicles/ranking` - Get vehicle ranking
- `GET /api/vehicles/violations/recent` - Get recent violations

### Notifications
- `GET /api/vehicles/notifications/unread` - Get unread notifications
- `POST /api/vehicles/notifications/{id}/read` - Mark as read

### Sensor Data
- `POST /api/sensors/data` - Add sensor reading
- `GET /api/sensors/data` - Get sensor data
- `GET /api/sensors/latest` - Get latest reading
- `PUT /api/sensors/data/{id}` - Update reading
- `DELETE /api/sensors/data/{id}` - Delete reading

## File Structure

```
SMOKI/
├── backend/
│   ├── main.py              # FastAPI application
│   ├── auth.py              # Authentication logic
│   ├── vehicles.py          # Vehicle detection endpoints (NEW)
│   ├── requirements.txt      # Python dependencies
│   └── Procfile             # Deployment configuration
│
├── frontend/
│   ├── src/
│   │   ├── Dashboard.jsx    # Main dashboard component
│   │   ├── App.jsx          # Login page
│   │   ├── component/
│   │   │   ├── ProtectedRoute.jsx
│   │   │   └── NotificationRibbon.jsx  # Notification system (NEW)
│   │   └── styles/
│   │       ├── Dashboard.css
│   │       ├── App.css
│   │       └── NotificationRibbon.css  # Notification styles (NEW)
│   ├── package.json
│   └── vite.config.js
│
├── postgre/
│   ├── database.py          # Database functions (UPDATED)
│   └── requirements.txt
│
├── esp32/
│   ├── esp32_sensor_sender.ino
│   └── es32_sensor_nointernet.ino
│
├── RPI_CAMERA_SETUP.md      # RPi4 camera integration guide (NEW)
└── PROJECT_SUMMARY.md       # This file
```

## How to Run

### 1. Backend Setup

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8080
```

### 2. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

### 3. Database Setup

```bash
# PostgreSQL must be running
# Database tables are created automatically on first run
```

### 4. Access Dashboard

```
http://localhost:5173
```

## Key Features

### Real-Time Monitoring
- Live vehicle detection updates
- Instant violation alerts
- Automatic notification dismissal
- Polling every 5-15 seconds

### Data Visualization
- Top violators with emission levels
- Vehicle ranking by violations
- Status indicators (Critical/Warning/Safe)
- License plate highlighting

### User Experience
- Intuitive dashboard layout
- Mobile-responsive design
- Dark mode support
- Smooth animations and transitions
- Color-coded severity levels

### Security
- JWT authentication
- Role-based access control
- Protected API endpoints
- Secure password hashing

## Integration Points for RPi4

### Ready for Implementation
1. **Camera Stream** - MJPEG streaming endpoint
2. **Vehicle Detection** - Hailo AI integration
3. **Smoke Detection** - ML model for emission analysis
4. **Image Storage** - Detection image archival
5. **Real-time Processing** - WebSocket for live updates

### Example Integration Script
See `RPI_CAMERA_SETUP.md` for Python script template

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

## Recent Changes

### Latest Commit
- Added RPi4 camera integration infrastructure
- Implemented vehicle detection and violation tracking
- Created real-time notification system
- Updated dashboard with Top Violators and Rankings
- Added comprehensive documentation

### Database Updates
- New tables: vehicles, vehicle_detections, violations, notifications
- Optimized indexes for performance
- JSON metadata support

### Frontend Updates
- Scrollable dashboard
- Dynamic Top Violators section
- Dynamic Violators Ranking
- Real-time notification ribbon
- Mobile-optimized layout

## Next Steps

1. **Hailo AI Integration** - Add vehicle detection model
2. **Camera Streaming** - Implement MJPEG stream endpoint
3. **Smoke Detection Model** - Train/integrate smoke detection
4. **WebSocket Support** - Real-time updates without polling
5. **Image Storage** - Archive detection images
6. **Mobile App** - React Native companion
7. **Cloud Deployment** - Multi-site support
8. **Analytics Dashboard** - Historical trends and reports

## Deployment

### Local Development
```bash
# Terminal 1: Backend
cd backend && python -m uvicorn main:app --reload --host 0.0.0.0 --port 8080

# Terminal 2: Frontend
cd frontend && npm run dev

# Terminal 3: RPi Camera (when ready)
python3 rpi_camera_stream.py
```

### Production (Heroku/Railway)
- Backend: Deploy to Heroku/Railway
- Frontend: Deploy to Netlify/Vercel
- Database: PostgreSQL on cloud provider
- RPi: Run locally on RPi4/RPi5

## Support & Documentation

- **Backend**: See `backend/` directory
- **Frontend**: See `frontend/` directory
- **Database**: See `postgre/` directory
- **RPi Setup**: See `RPI_CAMERA_SETUP.md`
- **ESP32**: See `esp32/` directory

## Project Status

✅ **Complete**
- Authentication system
- Sensor data management
- Vehicle detection infrastructure
- Violation tracking
- Notification system
- Dashboard UI
- Mobile responsiveness

🔄 **In Progress**
- RPi4 camera integration
- Hailo AI setup

⏳ **Planned**
- Live camera streaming
- Smoke detection model
- WebSocket real-time updates
- Mobile app
- Cloud deployment

---

**Last Updated**: February 12, 2026
**Version**: 1.0.0
**Status**: Ready for RPi4 Camera Integration
