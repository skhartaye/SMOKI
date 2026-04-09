# SMOKi - Air Quality Monitoring Web Dashboard

A standalone web application for displaying air quality monitoring data. The ESP32/Arduino and Raspberry Pi devices send data directly to this backend via HTTP API calls.

## Quick Start

1. **Database Setup**
```bash
# Install PostgreSQL and create database
createdb smoki_db
```

2. **Backend Setup**
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env  # Edit with your database credentials
python -m uvicorn main:app --reload
```

3. **Frontend Setup**
```bash
cd frontend
npm install
cp .env.example .env  # Edit with your backend URL
npm run dev
```

4. **Access**: http://localhost:5173

## API Endpoints

- `POST /api/sensors/data` - Receive sensor data from ESP32/Arduino
- `GET /api/sensors/data` - Get sensor readings
- `POST /api/violators` - Receive detection data from RPi
- `GET /api/violators` - Get violation records

## Architecture

```
ESP32/Arduino ──HTTP POST──> Backend API ──> PostgreSQL Database
                                 │
Raspberry Pi  ──HTTP POST──> ────┘
                                 │
                                 └──> React Frontend
```

The hardware devices are completely separate - they just send HTTP requests to your backend API.