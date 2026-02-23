# Render Setup Guide for RPi5 HLS Streaming

Step-by-step guide to configure your Render backend for RPi5 camera streaming with image storage.

## Overview

Your RPi5 will:
1. Stream HLS video to Render
2. Send detection data to Render API
3. Store images and metadata in PostgreSQL
4. Receive commands from the web dashboard

## Step 1: Create Render Web Service

### 1.1 Go to Render Dashboard

1. Visit https://render.com
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository

### 1.2 Configure Web Service

Fill in the form with:

| Field | Value |
|-------|-------|
| **Name** | `smoki-backend` |
| **Environment** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn main:app --host 0.0.0.0 --port 8000` |
| **Instance Type** | `Starter` (or higher if needed) |

### 1.3 Set Environment Variables

Click **"Environment"** and add these variables:

```
DB_HOST=your-postgres-host.render.com
DB_NAME=smoki_db
DB_USER=postgres
DB_PASSWORD=your-secure-password
DB_PORT=5432
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
RPI_IP=192.168.1.100
CAMERA_ID=cam_001
HLS_DIR=/tmp/hls
ALLOWED_ORIGINS=https://your-frontend.netlify.app,http://localhost:5173
```

**Important:** Use strong passwords and keep them secure.

### 1.4 Deploy

Click **"Create Web Service"** and wait for deployment to complete.

---

## Step 2: Create PostgreSQL Database on Render

### 2.1 Create Database

1. In Render dashboard, click **"New +"** → **"PostgreSQL"**
2. Configure:
   - **Name**: `smoki-postgres`
   - **Database Name**: `smoki_db`
   - **User**: `postgres`
   - **Region**: Same as backend (e.g., Oregon)
   - **Plan**: `Free` (or paid for production)

### 2.2 Get Connection Details

After creation, copy:
- **Host**: `your-db-host.render.com`
- **Port**: `5432`
- **Database**: `smoki_db`
- **User**: `postgres`
- **Password**: (shown once, save it)

### 2.3 Update Backend Environment Variables

Go back to your backend service and update:
```
DB_HOST=your-db-host.render.com
DB_PASSWORD=your-postgres-password
```

---

## Step 3: Initialize Database Schema

### 3.1 Connect to Database

Using psql (install if needed):

```bash
psql postgresql://postgres:PASSWORD@your-db-host.render.com:5432/smoki_db
```

Or use Render's built-in query editor in the dashboard.

### 3.2 Run Schema Creation

Execute the SQL from `postgre/create_image_tables.sql`:

```sql
-- Create images table
CREATE TABLE IF NOT EXISTS images (
    id SERIAL PRIMARY KEY,
    vehicle_detection_id INT REFERENCES vehicle_detections(id) ON DELETE CASCADE,
    violation_id INT REFERENCES violations(id) ON DELETE SET NULL,
    image_data BYTEA NOT NULL,
    image_format VARCHAR(20),
    file_size INT,
    width INT,
    height INT,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create image_metadata table
CREATE TABLE IF NOT EXISTS image_metadata (
    id SERIAL PRIMARY KEY,
    image_id INT REFERENCES images(id) ON DELETE CASCADE,
    camera_id VARCHAR(100),
    camera_location VARCHAR(255),
    exposure_time FLOAT,
    iso_speed INT,
    focal_length FLOAT,
    aperture FLOAT,
    white_balance VARCHAR(50),
    flash_used BOOLEAN,
    gps_latitude FLOAT,
    gps_longitude FLOAT,
    gps_altitude FLOAT,
    device_model VARCHAR(255),
    software_version VARCHAR(100),
    processing_time_ms INT,
    quality_score FLOAT,
    additional_data JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_images_vehicle_detection_id ON images(vehicle_detection_id);
CREATE INDEX IF NOT EXISTS idx_images_violation_id ON images(violation_id);
CREATE INDEX IF NOT EXISTS idx_images_timestamp ON images(timestamp);
CREATE INDEX IF NOT EXISTS idx_image_metadata_image_id ON image_metadata(image_id);
CREATE INDEX IF NOT EXISTS idx_image_metadata_camera_id ON image_metadata(camera_id);
```

---

## Step 4: Configure RPi Environment

### 4.1 Get Backend URL

From Render dashboard, copy your backend service URL:
- Format: `https://smoki-backend.onrender.com`

### 4.2 Update RPi .env File

Edit `esp32/.env.rpi` on your RPi:

```bash
# Critical - Update these
RENDER_BACKEND_URL=https://smoki-backend.onrender.com
CAMERA_ID=cam_001
CAMERA_LOCATION=Main_Entrance
HEF_PATH=/home/pi/smoki_project/models/smoki_model_v1.hef

# Keep defaults or adjust for your setup
SEND_DETECTIONS=true
CAMERA_FPS=20
CAMERA_BITRATE=800k
CONF_THRESH=0.25
```

### 4.3 Source Environment

```bash
source ~/.env.rpi
```

---

## Step 5: Test Connectivity

### 5.1 Test Backend Health

From RPi:

```bash
curl https://smoki-backend.onrender.com/api/health
```

Expected response:
```json
{
  "status": "ok",
  "timestamp": "2024-02-23T10:30:00"
}
```

### 5.2 Test Camera Health Endpoint

```bash
# First, get an auth token (if required)
curl -X POST https://smoki-backend.onrender.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your-password"}'

# Then check camera health
curl https://smoki-backend.onrender.com/api/camera/health \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 5.3 Test Detection Endpoint

```bash
# Send test detection data
curl -X POST https://smoki-backend.onrender.com/api/camera/detections \
  -H "Content-Type: application/json" \
  -d '{
    "camera_id": "cam_001",
    "timestamp": "2024-02-23T10:30:00",
    "detections": [
      {
        "class": "smoke_black",
        "confidence": 0.95,
        "bbox": [100, 100, 200, 200]
      }
    ]
  }'
```

---

## Step 6: Start RPi Streaming

### 6.1 Run Script Manually (Testing)

```bash
source ~/.env.rpi
python3 rpi5_camera_stream_optimized.py
```

Expected output:
```
[INFO] Initializing Hailo...
[INFO] Loading model: /home/pi/smoki_project/models/smoki_model_v1.hef
[INFO] Starting camera...
[INFO] HLS server running on http://192.168.1.100:8000
[INFO] Streaming to /dev/shm/hls
[INFO] Sending detections to https://smoki-backend.onrender.com
```

### 6.2 Create Systemd Service (Auto-Start)

```bash
sudo nano /etc/systemd/system/rpi-hls.service
```

Add:

```ini
[Unit]
Description=RPi5 HLS Camera Stream with Hailo
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi
EnvironmentFile=/home/pi/.env.rpi
ExecStart=/usr/bin/python3 /home/pi/rpi5_camera_stream_optimized.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable rpi-hls
sudo systemctl start rpi-hls
sudo systemctl status rpi-hls
```

---

## Step 7: Verify End-to-End

### 7.1 Check Backend Logs

In Render dashboard:
1. Go to your backend service
2. Click **"Logs"**
3. Look for detection messages

### 7.2 Check Database

```bash
psql postgresql://postgres:PASSWORD@your-db-host.render.com:5432/smoki_db

# Check images table
SELECT COUNT(*) FROM images;

# Check metadata
SELECT COUNT(*) FROM image_metadata;

# View recent images
SELECT id, image_format, file_size, timestamp FROM images ORDER BY timestamp DESC LIMIT 5;
```

### 7.3 Check Frontend

1. Go to your frontend URL
2. Navigate to Dashboard
3. You should see:
   - Live camera feed
   - Detection data
   - Violation alerts

---

## Step 8: Monitor Performance

### 8.1 Backend Metrics

In Render dashboard:
- **CPU Usage**: Should be < 50%
- **Memory**: Should be < 500MB
- **Response Time**: < 200ms

### 8.2 RPi Metrics

```bash
# SSH into RPi
ssh pi@192.168.1.100

# Check service status
sudo systemctl status rpi-hls

# View logs
sudo journalctl -u rpi-hls -f

# Check resource usage
top
```

### 8.3 Database Metrics

In Render dashboard:
- **Connections**: Should be 1-2
- **Storage**: Monitor growth
- **Query Performance**: Check slow queries

---

## Troubleshooting

### Backend won't start

```bash
# Check logs in Render dashboard
# Common issues:
# - Missing environment variables
# - Database connection failed
# - Port already in use
```

### RPi can't connect to backend

```bash
# Test connectivity
curl -v https://smoki-backend.onrender.com/api/health

# Check firewall
sudo ufw status

# Check DNS
nslookup smoki-backend.onrender.com
```

### Images not storing

```bash
# Check database connection
psql postgresql://postgres:PASSWORD@your-db-host.render.com:5432/smoki_db

# Verify tables exist
\dt

# Check for errors in backend logs
```

### High latency

```bash
# Reduce resolution on RPi
CAMERA_RESOLUTION_WIDTH=480
CAMERA_RESOLUTION_HEIGHT=360
CAMERA_FPS=15

# Use Ethernet instead of WiFi
# Check network speed: iperf3
```

### Out of memory on Render

```bash
# Upgrade instance type in Render dashboard
# Or optimize backend code
# Or reduce HLS segment size
```

---

## Production Checklist

- [ ] Backend deployed on Render
- [ ] PostgreSQL database created
- [ ] Schema initialized with image tables
- [ ] Environment variables set correctly
- [ ] RPi .env.rpi configured
- [ ] RPi systemd service created
- [ ] End-to-end connectivity tested
- [ ] Images storing in database
- [ ] Frontend displaying data
- [ ] Monitoring alerts configured
- [ ] Backups enabled
- [ ] SSL certificates valid

---

## Next Steps

1. ✅ Create Render web service
2. ✅ Create PostgreSQL database
3. ✅ Initialize schema
4. ✅ Configure RPi
5. ✅ Test connectivity
6. ✅ Start streaming
7. ⬜ Monitor in production
8. ⬜ Optimize performance
9. ⬜ Set up alerts

You're ready to stream to production!
