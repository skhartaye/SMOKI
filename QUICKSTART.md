# SMOKI Quick Start Guide

Get the SMOKI vehicle emission monitoring system up and running in 5 minutes.

## Prerequisites

- Python 3.8+
- Node.js 16+
- PostgreSQL 12+
- Git

## 1. Clone Repository

```bash
git clone https://github.com/skhartaye/SMOKI.git
cd SMOKI
```

## 2. Setup Backend

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Create .env file
cat > .env << EOF
DB_HOST=localhost
DB_NAME=smoki_db
DB_USER=postgres
DB_PASSWORD=password
DB_PORT=5432
SECRET_KEY=your-secret-key-here
EOF

# Run backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8080
```

Backend will be available at: `http://localhost:8080`

## 3. Setup Frontend

In a new terminal:

```bash
cd frontend

# Install dependencies
npm install

# Create .env file
cat > .env << EOF
VITE_API_URL=http://localhost:8000
EOF

# Run frontend
npm run dev
```

Frontend will be available at: `http://localhost:5173`

## 4. Setup Database

In a new terminal:

```bash
# Create database
createdb smoki_db

# Tables are created automatically on first backend run
```

## 5. Login

Open `http://localhost:5173` and login with:

- **Username**: admin
- **Password**: admin123

## Test Vehicle Detection

```bash
# Get your JWT token first (from login response)
TOKEN="your_jwt_token_here"

# Test vehicle detection
curl -X POST http://localhost:8000/api/vehicles/detect \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "license_plate": "ABC-123",
    "vehicle_type": "sedan",
    "location": "Main Street",
    "confidence": 0.95,
    "smoke_detected": true,
    "emission_level": "high"
  }'

# Check dashboard - you should see the vehicle in Top Violators
```

## Key Features

### Dashboard
- **Top Violators** - Real-time vehicle violations
- **Violators Ranking** - Complete vehicle rankings
- **Notifications** - Pop-up alerts for new violations
- **Dark Mode** - Toggle in sidebar

### API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/vehicles/detect` | Record vehicle detection |
| POST | `/api/vehicles/violation` | Report violation |
| GET | `/api/vehicles/top-violators` | Get top violators |
| GET | `/api/vehicles/ranking` | Get vehicle ranking |
| GET | `/api/vehicles/notifications/unread` | Get alerts |
| POST | `/api/sensors/data` | Add sensor reading |
| GET | `/api/sensors/latest` | Get latest sensor data |

## Troubleshooting

### Backend won't start
```bash
# Check if port 8000 is in use
lsof -i :8000

# Kill process if needed
kill -9 <PID>
```

### Frontend won't start
```bash
# Clear node_modules and reinstall
rm -rf node_modules package-lock.json
npm install
npm run dev
```

### Database connection error
```bash
# Check PostgreSQL is running
psql -U postgres

# Create database if missing
createdb smoki_db
```

### Can't login
```bash
# Check backend is running
curl http://localhost:8000/api/hello

# Check database has users table
psql -U postgres -d smoki_db -c "\dt"
```

## Next Steps

1. **Add Sensor Data** - Send data from ESP32 sensors
2. **Integrate RPi Camera** - See `RPI_CAMERA_SETUP.md`
3. **Deploy to Cloud** - Use Heroku, Railway, or AWS
4. **Mobile App** - Build React Native companion

## File Structure

```
SMOKI/
├── backend/          # FastAPI server
├── frontend/         # React dashboard
├── postgre/          # Database setup
├── esp32/            # Sensor firmware
├── RPI_CAMERA_SETUP.md
├── PROJECT_SUMMARY.md
└── QUICKSTART.md     # This file
```

## Environment Variables

### Backend (.env)
```
DB_HOST=localhost
DB_NAME=smoki_db
DB_USER=postgres
DB_PASSWORD=password
DB_PORT=5432
SECRET_KEY=your-secret-key-here
```

### Frontend (.env)
```
VITE_API_URL=http://localhost:8000
```

## Common Commands

```bash
# Start all services
# Terminal 1
cd backend && python -m uvicorn main:app --reload --host 0.0.0.0 --port 8080

# Terminal 2
cd frontend && npm run dev

# Terminal 3 (optional - for RPi camera)
python3 rpi_camera_stream.py
```

## API Testing

### Using curl

```bash
# Get JWT token
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# Use token in requests
TOKEN="eyJ0eXAiOiJKV1QiLCJhbGc..."

curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/vehicles/top-violators
```

### Using Postman

1. Import collection from `backend/postman_collection.json` (if available)
2. Set `{{base_url}}` to `http://localhost:8000`
3. Set `{{token}}` from login response
4. Run requests

## Performance Tips

- Dashboard updates every 15 seconds
- Notifications auto-dismiss after 8 seconds
- Mobile optimized for 768px and below
- Dark mode reduces eye strain

## Support

- **Issues**: Check GitHub issues
- **Documentation**: See `PROJECT_SUMMARY.md`
- **RPi Setup**: See `RPI_CAMERA_SETUP.md`

---

**Ready to go!** 🚀

Start with the backend and frontend, then integrate your sensors and camera.
