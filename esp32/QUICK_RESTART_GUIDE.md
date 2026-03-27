# Quick RPi Restart Guide

## Issue Fixed
✅ **Fixed IndentationError in `rpi_stream.py` line 819**
- The `try:` block was incorrectly indented
- Script now has valid Python syntax

## Current Status
- ❌ RPi detection script not running (syntax error prevented startup)
- ✅ Backend deployed and ready at https://smoki-backend-rpi.onrender.com
- ✅ Frontend deployed and ready at https://smoki.aeroband.org/dashboard
- ✅ Frontend correctly shows empty state when no real data (no more hardcoded data)

## Steps to Restart RPi Detection

### 1. Copy Fixed Script to RPi
```bash
# From your local machine, copy the fixed script to RPi
scp esp32/rpi_stream.py sevi@<rpi-ip>:/home/sevi/smoki_project/src/model-skhart-ready/
```

### 2. SSH to RPi and Restart
```bash
# SSH to RPi
ssh sevi@<rpi-ip>

# Navigate to project directory
cd /home/sevi/smoki_project/src/model-skhart-ready/

# Test syntax (should show no errors)
python3 -m py_compile rpi_stream.py

# Run with environment variables
source /home/sevi/smoki_project/skhart_fucksyou/bin/activate
python3 rpi_stream.py
```

### 3. Expected Output
```
[INFO] Starting camera...
[OK] Camera ready
[INFO] Loading Hailo models...
[OK] Loaded: yolov8n_seg.hef
[OK] Loaded: yolov8n.hef  
[OK] Loaded: yolov8n_plate.hef
[OK] Configured: yolov8n_seg.hef
[OK] Configured: yolov8n.hef
[OK] Configured: yolov8n_plate.hef

Pipeline ready — https://smoki-backend-rpi.onrender.com
Location: Main Camera  Interval: every 3s

[Snap #1] 04:20:15Z | Smoke:1 Veh:2 Plates:1 | inf=245ms upload=156ms total=401ms next=2.6s
```

### 4. Verify System Working
```bash
# Check backend receives data
curl https://smoki-backend-rpi.onrender.com/api/stream/status

# Should show:
# {"status":"active","fps":1,"buffered_frames":60,"latest_detections":[...]}
```

### 5. Check Frontend
- Visit https://smoki.aeroband.org/dashboard
- Should show real detection data instead of empty state
- Console logs should show actual detection processing

## Alternative: Use Restart Script
```bash
# Use the automated restart script
./restart_rpi_with_env.sh
```

## Troubleshooting
- If still getting syntax errors, ensure the file was copied correctly
- Check Python environment is activated
- Verify Hailo hardware is working: `./check_hailo_hardware.sh`