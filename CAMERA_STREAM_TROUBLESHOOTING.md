# Camera Stream Troubleshooting Guide

## Current Status
- ✅ Backend is healthy
- ✅ Camera health endpoint returns healthy
- ❌ Stream not displaying on frontend

## Root Cause Analysis

### What's Happening:
1. **RPi Script** sends frames to `POST /api/stream/frame`
2. **Backend** stores frames in `StreamManager`
3. **Frontend** requests `GET /api/stream/stream.mjpeg`
4. **Backend** streams MJPEG from stored frames

### Why It's Not Working:

The issue is likely one of these:

1. **RPi not sending frames** - Check if RPi script is running
2. **Frames not being stored** - Backend not receiving POST requests
3. **MJPEG stream empty** - No frames in buffer yet
4. **Browser caching** - Old frontend code cached

## Verification Steps

### Step 1: Check if RPi is sending frames

```bash
# On backend server, check stream status
curl https://smoki-backend-rpi.onrender.com/api/stream/status

# Expected response:
# {"status": "active", "fps": 20, "buffered_frames": 5}
```

### Step 2: Check if frames are being received

```bash
# Get latest frame
curl https://smoki-backend-rpi.onrender.com/api/stream/latest.jpg -o frame.jpg

# If this works, frames are being received
```

### Step 3: Test MJPEG stream directly

```bash
# Try to get MJPEG stream (will stream continuously)
curl https://smoki-backend-rpi.onrender.com/api/stream/stream.mjpeg

# Should see binary MJPEG data with frame boundaries
```

### Step 4: Check frontend console

1. Open browser DevTools (F12)
2. Go to Console tab
3. Look for errors related to:
   - CORS issues
   - Failed image loads
   - Network errors

## Solutions

### Solution 1: Ensure RPi Script is Running

On your Raspberry Pi:

```bash
# Check if script is running
ps aux | grep rpi5_camera_stream_optimized.py

# If not running, start it
python3 rpi5_camera_stream_optimized.py

# Or with systemd
sudo systemctl start rpi-hls
sudo systemctl status rpi-hls
```

### Solution 2: Verify Backend Configuration

Check that `RENDER_BACKEND_URL` is correct in RPi script:

```bash
# Should be set to your Render backend URL
export API_URL=https://smoki-backend-rpi.onrender.com
```

### Solution 3: Clear Browser Cache

1. Hard refresh frontend (Ctrl+Shift+R or Cmd+Shift+R)
2. Clear browser cache
3. Try again

### Solution 4: Check Network Connectivity

From RPi, verify it can reach backend:

```bash
# Test connectivity
curl https://smoki-backend-rpi.onrender.com/api/health

# Should return: {"status": "healthy", "database": "connected"}
```

### Solution 5: Monitor Backend Logs

In Render dashboard:
1. Go to smoki-backend-rpi service
2. Click "Logs"
3. Look for:
   - Frame upload requests
   - Stream requests
   - Any errors

## Expected Behavior

When working correctly:

1. **RPi sends frame** → Backend receives POST to `/api/stream/frame`
2. **Backend stores frame** → Frame added to StreamManager buffer
3. **Frontend requests stream** → Backend sends MJPEG stream
4. **Browser displays** → Video plays in CameraViewer component

## Performance Metrics

| Metric | Expected | Actual |
|--------|----------|--------|
| FPS | 20-30 | ? |
| Latency | 1-2 sec | ? |
| Frame Buffer | 5-30 | ? |
| Stream Status | active | ? |

## Quick Checklist

- [ ] RPi script is running
- [ ] RPi can reach backend (curl test)
- [ ] Backend receiving frames (check `/api/stream/status`)
- [ ] Frontend can fetch latest frame (check `/api/stream/latest.jpg`)
- [ ] Browser console has no errors
- [ ] Frontend is not cached (hard refresh)
- [ ] CORS headers are correct

## Next Steps

1. Run verification steps above
2. Check which step fails
3. Apply corresponding solution
4. Test again

If still not working, check the backend logs for specific error messages.

