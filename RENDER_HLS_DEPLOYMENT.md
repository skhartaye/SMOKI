# Render Deployment Guide for RPi HLS Streaming

Complete step-by-step guide to deploy your RPi camera streaming to Render.

## Architecture

```
RPi5 (Local Network)
├── Hailo inference
├── FFmpeg HLS encoder
└── HTTP server (port 8000)
    └── /dev/shm/hls/stream.m3u8

        ↓ (Network tunnel or direct connection)

Render Web Service
├── FastAPI backend
├── HLS file serving
├── Detection API
└── Vehicle tracking

        ↓

Browser
└── HLS.js player
```

---

## Step 1: Prepare Backend for Render

### 1.1 Update `backend/requirements.txt`

Add these dependencies:

```
fastapi==0.104.1
uvicorn==0.24.0
psycopg==3.1.12
pydantic==2.5.0
python-jose==3.3.0
passlib==1.7.4
python-multipart==0.0.6
requests==2.31.0
python-dotenv==1.0.0
```

### 1.2 Create `backend/render.yaml`

```yaml
services:
  - type: web
    name: smoki-backend
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn main:app --host 0.0.0.0 --port 8000
    envVars:
      - key: DB_HOST
        scope: run
        value: ${DB_HOST}
      - key: DB_NAME
        scope: run
        value: smoki_db
      - key: DB_USER
        scope: run
        value: postgres
      - key: DB_PASSWORD
        scope: run
        value: ${DB_PASSWORD}
      - key: DB_PORT
        scope: run
        value: "5432"
      - key: SECRET_KEY
        scope: run
        value: ${SECRET_KEY}
      - key: ALGORITHM
        scope: run
        value: HS256
      - key: ACCESS_TOKEN_EXPIRE_MINUTES
        scope: run
        value: "30"
      - key: RPI_IP
        scope: run
        value: ${RPI_IP}
      - key: CAMERA_ID
        scope: run
        value: cam_001
      - key: HLS_DIR
        scope: run
        value: /tmp/hls
      - key: ALLOWED_ORIGINS
        scope: run
        value: https://your-frontend.netlify.app,http://localhost:5173

databases:
  - name: smoki-postgres
    databaseName: smoki_db
    user: postgres
    plan: free
```

### 1.3 Update `backend/main.py`

Add HLS endpoints:

```python
from fastapi import FastAPI, Depends, HTTPException, File, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
from pathlib import Path
from datetime import datetime
import json

app = FastAPI()

# ─── CORS ────────────────────────────────────────────────────────────────────
allowed_origins = os.getenv('ALLOWED_ORIGINS', 'http://localhost:5173').split(',')
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── HLS SETUP ───────────────────────────────────────────────────────────────
HLS_DIR = os.getenv('HLS_DIR', '/tmp/hls')
Path(HLS_DIR).mkdir(parents=True, exist_ok=True)

# Mount HLS directory for static file serving
app.mount("/hls", StaticFiles(directory=HLS_DIR), name="hls")

# ─── HLS ENDPOINTS ───────────────────────────────────────────────────────────

@app.get("/api/camera/stream.m3u8")
async def get_hls_playlist(current_user: User = Depends(get_current_user)):
    """Serve HLS playlist"""
    playlist_path = os.path.join(HLS_DIR, "stream.m3u8")
    
    if not os.path.exists(playlist_path):
        raise HTTPException(status_code=404, detail="Stream not available")
    
    return FileResponse(
        playlist_path,
        media_type="application/vnd.apple.mpegurl"
    )

@app.get("/api/camera/health")
async def camera_health(current_user: User = Depends(get_current_user)):
    """Check if camera is streaming"""
    playlist_path = os.path.join(HLS_DIR, "stream.m3u8")
    is_streaming = os.path.exists(playlist_path)
    
    return {
        "status": "streaming" if is_streaming else "offline",
        "stream_url": "/api/camera/stream.m3u8" if is_streaming else None,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/camera/detections")
async def receive_detections(data: dict):
    """Receive detection results from RPi (no auth for RPi)"""
    try:
        camera_id = data.get('camera_id')
        detections = data.get('detections', [])
        timestamp = data.get('timestamp')
        
        print(f"[{timestamp}] Camera {camera_id}: {len(detections)} detections")
        
        # Check for smoke
        smoke_detections = [d for d in detections if 'smoke' in d['class'].lower()]
        if smoke_detections:
            print(f"⚠️  SMOKE DETECTED: {smoke_detections}")
            # TODO: Send alert, save to DB, etc.
        
        return {"status": "received", "count": len(detections)}
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/health")
async def health_check():
    """General health check (no auth required)"""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat()
    }
```

---

## Step 2: Update Frontend

### 2.1 Install HLS.js

```bash
cd frontend
npm install hls.js
```

### 2.2 Update `frontend/src/component/CameraViewer.jsx`

```jsx
import React, { useEffect, useRef, useState } from 'react';
import HLS from 'hls.js';
import '../styles/CameraViewer.css';

function CameraViewer() {
  const videoRef = useRef(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState(null);
  const [cameraStatus, setCameraStatus] = useState('checking');
  const hlsRef = useRef(null);

  useEffect(() => {
    const startStream = async () => {
      try {
        // Check camera health
        const token = localStorage.getItem('token');
        const healthResponse = await fetch('/api/camera/health', {
          headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!healthResponse.ok) {
          setCameraStatus('offline');
          setError('Camera is offline');
          return;
        }

        const health = await healthResponse.json();

        if (health.status !== 'streaming') {
          setCameraStatus('offline');
          setError('Camera is offline');
          return;
        }

        setCameraStatus('online');

        // Initialize HLS player
        const video = videoRef.current;
        const streamUrl = '/api/camera/stream.m3u8';

        if (HLS.isSupported()) {
          const hls = new HLS({
            debug: false,
            enableWorker: true,
            lowLatencyMode: true,
            backBufferLength: 90,
          });

          hlsRef.current = hls;

          hls.loadSource(streamUrl);
          hls.attachMedia(video);

          hls.on(HLS.Events.MANIFEST_PARSED, () => {
            console.log('HLS stream loaded');
            setIsStreaming(true);
            setError(null);
            video.play().catch(e => console.log('Autoplay prevented:', e));
          });

          hls.on(HLS.Events.ERROR, (event, data) => {
            console.error('HLS error:', data);
            if (data.fatal) {
              setError(`Stream error: ${data.details}`);
              setIsStreaming(false);
            }
          });
        } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
          // Safari native HLS support
          video.src = streamUrl;
          video.addEventListener('loadedmetadata', () => {
            setIsStreaming(true);
            setError(null);
            video.play().catch(e => console.log('Autoplay prevented:', e));
          });
        } else {
          setError('HLS streaming not supported in this browser');
        }
      } catch (err) {
        setError(`Failed to start stream: ${err.message}`);
        setCameraStatus('error');
      }
    };

    startStream();

    return () => {
      if (hlsRef.current) {
        hlsRef.current.destroy();
      }
    };
  }, []);

  return (
    <div className="camera-viewer">
      <div className="camera-container">
        {error ? (
          <div className="camera-error">
            <p>{error}</p>
            <small>Status: {cameraStatus}</small>
          </div>
        ) : (
          <>
            <video
              ref={videoRef}
              className="camera-video"
              controls
              autoPlay
              muted
              playsInline
            />
            {isStreaming && (
              <div className="stream-indicator">
                <span className="live-badge">● LIVE</span>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default CameraViewer;
```

### 2.3 Update `frontend/.env`

```env
VITE_API_URL=https://your-backend.onrender.com
VITE_FRONTEND_URL=https://your-frontend.netlify.app
```

---

## Step 3: Deploy to Render

### 3.1 Push to GitHub

```bash
git add .
git commit -m "Add HLS streaming support for RPi camera"
git push origin main
```

### 3.2 Create Render Service

1. Go to https://render.com
2. Click "New +" → "Web Service"
3. Connect your GitHub repository
4. Configure:
   - **Name**: `smoki-backend`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port 8000`

### 3.3 Add Environment Variables

In Render dashboard, add:

```
DB_HOST=your-postgres-host
DB_PASSWORD=your-postgres-password
SECRET_KEY=your-secret-key-here
RPI_IP=192.168.1.100
```

### 3.4 Deploy

Click "Deploy" and wait for the service to start.

---

## Step 4: Configure RPi

### 4.1 On RPi, set environment variables

```bash
export RENDER_BACKEND_URL="https://your-backend.onrender.com"
export CAMERA_ID="cam_001"
export SEND_DETECTIONS="true"
```

### 4.2 Run the optimized script

```bash
python3 rpi5_camera_stream_optimized.py
```

### 4.3 Create systemd service (optional)

Create `/etc/systemd/system/rpi-hls.service`:

```ini
[Unit]
Description=RPi HLS Camera Stream
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi
Environment="RENDER_BACKEND_URL=https://your-backend.onrender.com"
Environment="CAMERA_ID=cam_001"
Environment="SEND_DETECTIONS=true"
ExecStart=/usr/bin/python3 /home/pi/rpi5_camera_stream_optimized.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable:
```bash
sudo systemctl daemon-reload
sudo systemctl enable rpi-hls
sudo systemctl start rpi-hls
```

---

## Step 5: Test

### 5.1 Check backend health

```bash
curl https://your-backend.onrender.com/api/health
```

### 5.2 Check camera health

```bash
curl https://your-backend.onrender.com/api/camera/health \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 5.3 View stream in browser

1. Go to your frontend URL
2. Navigate to Dashboard
3. You should see the live camera feed

---

## Troubleshooting

### Stream not showing

1. Check RPi script is running:
   ```bash
   ps aux | grep rpi5_camera_stream
   ```

2. Check HLS files exist:
   ```bash
   ls -la /dev/shm/hls/
   ```

3. Check backend logs:
   ```bash
   # In Render dashboard, view logs
   ```

4. Check CORS:
   ```bash
   curl -I https://your-backend.onrender.com/api/camera/stream.m3u8
   ```

### High latency

1. Reduce bitrate on RPi:
   ```python
   start_ffmpeg(640, 480, fps=20, bitrate='800k')
   ```

2. Use Ethernet instead of WiFi on RPi

3. Lower resolution:
   ```python
   config = picam2.create_video_configuration(
       main={"format": "RGB888", "size": (480, 360)}
   )
   ```

### Detections not sending

1. Check `SEND_DETECTIONS=true` on RPi
2. Check `RENDER_BACKEND_URL` is correct
3. Check network connectivity from RPi to Render

---

## Performance Expectations

| Metric | Value |
|--------|-------|
| Latency | 2-3 seconds |
| Jitter | Minimal |
| Bandwidth | 1200k |
| Quality | 640x480 @ 20 FPS |
| Availability | Global (24/7) |

---

## Next Steps

1. ✅ RPi script working
2. ⬜ Update backend with HLS endpoints
3. ⬜ Update frontend with HLS player
4. ⬜ Deploy to Render
5. ⬜ Configure RPi for Render
6. ⬜ Test end-to-end

You're almost there!
