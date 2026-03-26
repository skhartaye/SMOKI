# Running SMOKI Services on RPi

## Overview
The SMOKI system requires two services running simultaneously on the RPi:

1. **HLS Stream Server** (port 8001) - Streams video with inference overlays
2. **FastAPI Backend** (port 8000) - Receives detection data and stores in database

## Prerequisites
- Python venv activated: `/home/sevi/smoki_project/skhart_fucksyou`
- Hailo8L device connected
- Database configured in `backend/.env`

## Running Services

### Terminal 1: Start FastAPI Backend
```bash
cd /home/sevi/smoki_project/backend
source /home/sevi/smoki_project/skhart_fucksyou/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

Expected output:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Terminal 2: Start HLS Stream with Inference
```bash
cd /home/sevi/smoki_project/esp32
source /home/sevi/smoki_project/skhart_fucksyou/bin/activate
python rpi_stream.py
```

Expected output:
```
[OK] HLS server started
[OK] Starting inference loop...
[OK] Camera started
[OK] FFmpeg started
--- Low-Latency HLS Active (Sequential Multi-Model) ---
URL: http://localhost:8001/stream.m3u8
```

## Verification

### Check Backend Health
```bash
curl http://192.168.100.199:8000/api/health
```

Expected response:
```json
{"status": "healthy", "database": "connected"}
```

### Check Camera Health
```bash
curl http://192.168.100.199:8000/api/camera/health
```

Expected response:
```json
{"status": "healthy", "stream_url": "/api/stream/playlist.m3u8", "timestamp": "..."}
```

### Check HLS Stream
```bash
curl http://192.168.100.199:8001/stream.m3u8
```

Expected response: HLS playlist with segments

## Data Flow

1. **Camera** → Captures frames at 15 FPS
2. **Hailo8L** → Runs inference (smoke, vehicle, license plate models)
3. **rpi_stream.py** → 
   - Encodes frames to HLS (port 8001)
   - POSTs detections to backend (port 8000)
4. **Backend** → 
   - Receives detections
   - Stores in PostgreSQL database
   - Serves API endpoints

## Troubleshooting

### Backend won't start
- Check Python venv is activated
- Verify database connection in `backend/.env`
- Check port 8000 isn't already in use: `lsof -i :8000`

### HLS stream won't start
- Check Hailo8L device is connected: `lsof -i :8001`
- Verify camera is available: `libcamera-hello --list-cameras`
- Check FFmpeg is installed: `which ffmpeg`

### Detections not being recorded
- Verify backend is running on port 8000
- Check backend logs for POST errors
- Verify `BACKEND_URL` in `rpi_stream.py` is correct

## Systemd Services (Optional)

To run services automatically on boot, see `pwm-fan.service` for reference.
