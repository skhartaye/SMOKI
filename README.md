# 💨 SMOKi - Design and Development of an IoT-Driven Vehicle Smoke Emission Classification System Using Convolutional Neural Network with 
Data Analytics Management

Design and Development of an IoT-Driven Vehicle Smoke Emission Classification System Using Convolutional Neural Network with 
Data Analytics Management

**Repository**: [skhartaye/SMOKI](https://github.com/skhartaye/SMOKI)  
**Web Design**: [miiikunnn/SMOKi_web_design_3](https://github.com/miiikunnn/SMOKi_web_design_3)

## 🌟 Features

- **Real-time Sensor Monitoring**: Track temperature, humidity, VOCs, NO₂, CO, PM2.5, and PM10
- **ESP32 Integration**: Wireless data collection from BME680, MICS6814, and PMS7003 sensors
- **AI-Powered Smoke Detection**: Raspberry Pi 5 with Hailo accelerator for real-time video analysis
- **Smoke Density & Color Analysis**: Advanced computer vision for smoke characterization
- **Web Dashboard**: Interactive React-based interface with live graphs and historical data
- **RESTful API**: FastAPI backend for data management
- **PostgreSQL Database**: Reliable data storage with timezone-aware timestamps

## 🏗️ Architecture

```
┌─────────────┐      WiFi      ┌──────────────┐      HTTP      ┌─────────────┐
│   ESP32     │ ──────────────> │   Backend    │ ──────────────> │  Frontend   │
│  (Sensors)  │                 │  (FastAPI)   │                 │   (React)   │
└─────────────┘                 └──────────────┘                 └─────────────┘
                                       │
                                       │ PostgreSQL
                                       ▼
                                ┌──────────────┐
                                │   Database   │
                                └──────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Raspberry Pi 5 + Hailo AI Accelerator                          │
│  ┌──────────────────┐         ┌──────────────────────────────┐  │
│  │  Camera Module   │ ──────> │  Hailo Inference Engine      │  │
│  │  (Video Stream)  │         │  (Smoke Detection & Analysis)│  │
│  └──────────────────┘         └──────────────────────────────┘  │
│                                        │                         │
│                                        ▼                         │
│                              ┌──────────────────┐                │
│                              │  Violator Data   │                │
│                              │  (Metadata)      │                │
│                              └──────────────────┘                │
└─────────────────────────────────────────────────────────────────┘
                                        │
                                        │ HTTP POST
                                        ▼
                                ┌──────────────────┐
                                │   FastAPI        │
                                │   Backend        │
                                └──────────────────┘
                                        │
                                        │ Store
                                        ▼
                                ┌──────────────────┐
                                │   PostgreSQL     │
                                │   (Violators DB) │
                                └──────────────────┘
                                        │
                                        │ Query
                                        ▼
                                ┌──────────────────┐
                                │   React          │
                                │   Dashboard      │
                                │   (Violators)    │
                                └──────────────────┘
```

## 📋 Prerequisites

- **Python 3.10+** (Backend)
- **Node.js 16+** (Frontend)
- **PostgreSQL 12+** (Database)
- **Raspberry Pi 5** with Hailo AI Accelerator (For smoke detection)
- **ESP32** with sensors (For air quality monitoring)

## 🚀 Quick Start

### 1. Database Setup

```bash
# Install PostgreSQL (if not already installed)
# Windows: https://www.postgresql.org/download/windows/
# Linux: sudo apt install postgresql postgresql-contrib
# macOS: brew install postgresql

# Create database
psql -U postgres
CREATE DATABASE smoki_db;
\q

# Configure database credentials
cd postgre
cp .env.example .env
# Edit .env with your PostgreSQL credentials
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run backend server
python -m uvicorn main:app --reload
```

Backend will be available at: `http://127.0.0.1:8000`

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
```

Frontend will be available at: `http://localhost:5173`

### 4. Access the Dashboard

1. Open browser: `http://localhost:5173`

## 📁 Project Structure

```
smoki/
├── backend/              # FastAPI backend
│   ├── main.py          # API endpoints
│   ├── requirements.txt # Python dependencies
│   └── .env            # Database configuration
├── frontend/            # React frontend
│   ├── src/
│   │   ├── App.jsx     # Login page
│   │   ├── Dashboard.jsx # Main dashboard
│   │   └── styles/     # CSS files
│   └── package.json    # Node dependencies
├── postgre/            # Database module
│   ├── database.py     # Database operations
│   └── .env           # Database configuration
├── esp32/             # ESP32 firmware
│   └── esp32_sensor_sender.ino
├── tdlite_rpi.py      # TFLite inference (Raspberry Pi)
└── check_time_sync.py # Time synchronization checker
```

## 🔌 API Endpoints

### Sensor Data
- `POST /api/sensors/data` - Add new sensor reading
- `GET /api/sensors/data?limit=N` - Get latest N readings
- `GET /api/sensors/latest` - Get most recent reading

### Violators (Smoke Detection)
- `POST /api/violators` - Submit violator metadata from Hailo
- `GET /api/violators` - Get list of detected violators
- `GET /api/violators/{id}` - Get specific violator details
- `PUT /api/violators/{id}` - Update violator status
- `DELETE /api/violators/{id}` - Remove violator record

### System
- `GET /api/hello` - Health check
- `GET /api/time` - Server time (for debugging)

### Example Request

```bash
# Add sensor data
curl -X POST http://127.0.0.1:8000/api/sensors/data \
  -H "Content-Type: application/json" \
  -d '{
    "temperature": 25.5,
    "humidity": 60.2,
    "vocs": 150.0,
    "nitrogen_dioxide": 0.05,
    "carbon_monoxide": 0.8,
    "pm25": 12.5,
    "pm10": 18.3
  }'

# Submit violator metadata from Hailo
curl -X POST http://127.0.0.1:8000/api/violators \
  -H "Content-Type: application/json" \
  -d '{
    "timestamp": "2025-02-14T10:30:00Z",
    "license_plate": "ABC123",
    "smoke_density": 85.5,
    "smoke_color": "black",
    "confidence": 0.92,
    "image_path": "/path/to/image.jpg",
    "location": "Main Street",
    "vehicle_type": "truck"
  }'
```

## 🔧 Configuration

### Backend (.env)
```env
DB_HOST=localhost
DB_NAME=smoki_db
DB_USER=postgres
DB_PASSWORD=your_password
DB_PORT=5432
```

### Frontend (.env.production)
```env
VITE_API_URL=https://your-backend-url.com
```

## 🐛 Troubleshooting

### Time Synchronization Issues

If timestamps are incorrect:

```bash
# Run diagnostic tool
python check_time_sync.py

# Fix system time (Linux/Raspberry Pi)
sudo timedatectl set-ntp true

# Update database schema
psql -U postgres -d smoki_db
ALTER TABLE sensor_data 
  ALTER COLUMN timestamp TYPE TIMESTAMPTZ 
  USING timestamp AT TIME ZONE 'UTC';
```

### Database Connection Errors

```bash
# Check PostgreSQL is running
# Windows: Check Services
# Linux: sudo systemctl status postgresql
# Mac: brew services list

# Test connection
psql -U postgres -d smoki_db
```

### ESP32 Connection Issues

1. Check WiFi credentials in `esp32_sensor_sender.ino`
2. Verify backend URL is accessible from ESP32
3. Check firewall settings

## 🎯 Hardware Setup (Optional)

### Required Components
- ESP32 Development Board
- BME680 (Temperature, Humidity, Pressure, VOCs)
- MICS6814 (NO₂, CO, NH₃)
- PMS7003 (PM2.5, PM10)
- RPI5
- Hailo

### Wiring
See `esp32/esp32_sensor_sender.ino` for pin configurations.

## 🚧 Roadmap

- [x] Camera integration with Hailo AI acceleration
- [x] Smoke detection and analysis
- [ ] License plate recognition
- [ ] Email/SMS alerts for threshold violations
- [ ] Data export functionality
- [ ] Multi-user authentication improvements
- [ ] Mobile app
- [ ] Cloud deployment

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 👥 Contributors

- mercado - backend

## 🙏 Acknowledgments

- FastAPI for the excellent web framework
- React and Recharts for the frontend
- PostgreSQL for reliable data storage
- ESP32 community for hardware support

## 📞 Support

For issues and questions:
- Create an issue on GitHub
- Email: aerobandtech@gmail.com

---

**Note**: This is a development project. For production use, implement proper authentication, HTTPS, and security measures.
