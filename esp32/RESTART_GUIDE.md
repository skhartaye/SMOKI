# RPi Detection System Restart Guide

## Current Issues
1. **Frontend showing cached data** - "Using historical data: 3 vehicles"
2. **RPi not sending detection data** - `latest_detections: undefined`

## Step-by-Step Fix

### 1. Fix Frontend Cache Issue
**On your computer:**
- Hard refresh browser: `Ctrl+F5` (Windows) or `Cmd+Shift+R` (Mac)
- Or clear browser cache for https://smoki.aeroband.org
- The hardcoded data has been removed from the code

### 2. Restart RPi Detection System
**On the RPi:**

```bash
# 1. Stop any existing detection processes
pkill -f "rpi_simple_detect.py"
pkill -f "rpi_stream.py"

# 2. Check if processes are stopped
ps aux | grep rpi_

# 3. Copy the restart script (if not already done)
# scp esp32/restart_rpi_with_env.sh sevi@<rpi-ip>:/home/sevi/

# 4. Make script executable
chmod +x /home/sevi/restart_rpi_with_env.sh

# 5. Run the restart script
./restart_rpi_with_env.sh
```

### 3. Verify Everything is Working

**Check RPi process:**
```bash
ps aux | grep rpi_
tail -f /tmp/rpi_detect.log
```

**Check backend connection:**
```bash
curl -X GET https://smoki-backend-rpi.onrender.com/api/stream/status
```

**Expected response:**
```json
{
  "status": "active",
  "fps": 1,
  "buffered_frames": 60,
  "latest_frame_size": 62314,
  "latest_detections": [...],  // Should have detection data
  "detection_summary": {...},
  "camera_info": {...}
}
```

### 4. Check Frontend
- Go to https://smoki.aeroband.org/dashboard
- Open browser console (F12)
- Look for detection data in logs
- Camera stream should show frames
- Detection table should show real detections (not "Unknown Unknown 0.0%")

## Troubleshooting

### If RPi script fails to start:
```bash
# Check environment file exists
ls -la /home/sevi/smoki_project/src/model-skhart-ready/.env.rpi

# Check virtual environment
ls -la /home/sevi/smoki_project/skhart_fucksyou/

# Manual start with debugging
source /home/sevi/smoki_project/skhart_fucksyou/bin/activate
cd /home/sevi/smoki_project/src/model-skhart-ready/
python rpi_simple_detect.py --interval 3
```

### If backend shows no detections:
- Check if RPi is sending frames: Look for `[Sent]` messages in RPi logs
- Check backend logs for `[FRAME]` messages
- Verify network connectivity between RPi and backend

### If frontend still shows cached data:
- Try incognito/private browsing mode
- Clear all browser data for the site
- Wait for frontend redeployment (automatic)

## Expected Behavior After Fix

1. **Frontend Dashboard:**
   - No "Unknown Unknown 0.0%" entries
   - Real detection data when RPi is active
   - Empty detection table when RPi is inactive (not hardcoded data)

2. **Camera Stream:**
   - Shows live frames from RPi every 5 seconds
   - "Connected" status when RPi is sending data

3. **Detection Processing:**
   - Only valid class names: `passenger`, `puv`, `services`, `two_wheel`, `smoke_black`, `smoke_white`, `license_plate`
   - Confidence levels above 10%
   - Realistic license plate generation for vehicles