# RPi Detection Fix Deployment Guide

## Quick Deployment (Automated)

### Option 1: PowerShell Script (Windows)
```powershell
# From D:\embed\SMOKI directory
.\esp32\deploy_rpi_fix.ps1
# Or with custom IP:
.\esp32\deploy_rpi_fix.ps1 -RpiIP "192.168.1.100"
```

### Option 2: Bash Script (Linux/WSL)
```bash
# From D:\embed\SMOKI directory
./esp32/deploy_rpi_fix.sh
# Or with custom IP:
./esp32/deploy_rpi_fix.sh 192.168.1.100
```

## Manual Deployment (Step by Step)

### Step 1: Copy Updated Script
```bash
# Copy the fixed script to RPi
scp esp32/rpi_simple_detect.py sevi@<rpi-ip>:/home/sevi/smoki_project/src/model-skhart-ready/
```

### Step 2: SSH to RPi
```bash
ssh sevi@<rpi-ip>
```

### Step 3: Navigate to Project Directory
```bash
cd /home/sevi/smoki_project/src/model-skhart-ready
```

### Step 4: Stop Current Script (if running)
```bash
# Check if running
pgrep -f rpi_simple_detect.py

# Stop if running
pkill -f rpi_simple_detect.py
```

### Step 5: Test Script Syntax
```bash
python3 -m py_compile rpi_simple_detect.py
```

### Step 6: Activate Virtual Environment and Start Script
```bash
source /home/sevi/smoki_project/skhart_fucksyou/bin/activate
python rpi_simple_detect.py --interval 3
```

## Expected Output After Fix

### ✅ Success Indicators
```
[START] rpi_snap.py
[INFO] Starting camera...
[OK] Camera ready
[OK] Face model loaded
[OK] EasyOCR ready
[PG] Schema ready ✓                    # ← This should now show ✓ instead of error
[INFO] Loading Hailo models...
[OK] Loaded: smoke-hailo8l.hef
[OK] Loaded: license-plate-opt-hailo8l.hef
[OK] Loaded: vehicle-class-hailo8l.hef
[OK] Configured: smoke-hailo8l.hef
[OK] Configured: license-plate-opt-hailo8l.hef
[OK] Configured: vehicle-class-hailo8l.hef
[INFO] Running snapshot loop every 3.0s — Ctrl+C to stop
[Sent] smoke=0 veh=0 plates=0 faces=1 inf=68ms
[Snap #1] 2026-03-27T05:51:33Z | Smoke:0 Veh:0 Plates:0 Faces:1 | inf=68ms upload=1126ms total=1827ms next_in=1.2s
```

### ❌ Previous Error (Fixed)
```
[PG] Schema init error: column "camera_id" does not exist  # ← This should be gone
```

## Verification Steps

### 1. Check RPi Script Status
```bash
# On RPi
pgrep -f rpi_simple_detect.py  # Should return a PID
tail -f rpi_detect.log         # Monitor real-time logs
```

### 2. Check Backend Status
```bash
# From any machine
curl https://smoki-backend-rpi.onrender.com/api/stream/status
```

**Expected Response:**
```json
{
  "status": "active",
  "fps": 1,
  "buffered_frames": 60,
  "latest_frame_size": 51759,
  "latest_detections": [...],  // Will show detections when objects appear
  "detection_summary": {
    "total_detections": 0,
    "smoke_detections": 0,
    // ... detailed breakdown
  }
}
```

### 3. Check Frontend
- Visit: https://smoki.aeroband.org/dashboard
- Should show live camera feed
- Should display real detection data when objects appear in camera view

## Troubleshooting

### If Script Won't Start
```bash
# Check Python environment
which python
python --version

# Check dependencies
pip list | grep -E "(opencv|psycopg|requests)"

# Check environment variables
cat /home/sevi/smoki_project/src/model-skhart-ready/.env.rpi
```

### If Database Still Has Issues
```bash
# Check PostgreSQL connection
sudo systemctl status postgresql
sudo -u postgres psql -c "\l"  # List databases
```

### If No Detections Appear
1. **Check camera view** - Make sure there are objects (people, vehicles) in camera view
2. **Check Hailo models** - Ensure all 3 models loaded successfully
3. **Check backend logs** - Look for frame processing messages
4. **Check network** - Ensure RPi can reach backend URL

## What This Fix Does

1. **Fixes Local Database Schema** - Handles `camera_id` column creation gracefully
2. **Improves Error Handling** - Non-fatal index creation errors
3. **Maintains Functionality** - Script continues even if local DB has issues
4. **Preserves Cloud Integration** - Detection data still flows to backend

The RPi script will now start successfully and send detection data to the cloud backend, which will then be displayed on the frontend dashboard.