# RPi Frame Upload Debugging Guide

## The Problem

The RPi script is timing out when trying to send frames to the backend. This means either:
1. The backend URL is wrong
2. The network connection is too slow
3. The backend endpoint is not working

## How Frame Sending Works

```
RPi Script
    ↓
Captures frame from camera
    ↓
Encodes to JPEG
    ↓
POST to https://smoki-backend-rpi.onrender.com/api/stream/frame
    ↓
Backend receives and stores in StreamManager
    ↓
Frontend fetches from /api/stream/latest.jpg
    ↓
Browser displays video
```

## Step 1: Verify Backend URL

The backend URL is set from environment variable:

```bash
# Check current value
echo $API_URL

# If empty, set it
export API_URL=https://smoki-backend-rpi.onrender.com

# Verify it's set
echo $API_URL
```

## Step 2: Test Backend Connectivity

```bash
# Test if backend is reachable
curl https://smoki-backend-rpi.onrender.com/api/health

# Expected response:
# {"status":"healthy","database":"connected"}
```

If this fails, the backend is down or unreachable.

## Step 3: Test Frame Upload Endpoint

```bash
# Create a test image
python3 << 'EOF'
import cv2
import numpy as np

# Create a simple test image
img = np.zeros((360, 480, 3), dtype=np.uint8)
cv2.putText(img, "Test Frame", (100, 180), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 0), 3)
cv2.imwrite('test_frame.jpg', img)
print("Created test_frame.jpg")
EOF

# Upload the test image
curl -X POST https://smoki-backend-rpi.onrender.com/api/stream/frame \
  -F "frame=@test_frame.jpg"

# Expected response:
# {"success":true,"fps":...,"buffered_frames":...}
```

## Step 4: Run RPi Script with Debug Output

The updated script now shows detailed logs:

```bash
# Run the script
python3 rpi5_camera_stream_optimized.py

# You should see:
# [TEST] Checking backend connectivity to https://smoki-backend-rpi.onrender.com...
# [TEST] ✓ Backend is reachable: {"status":"healthy","database":"connected"}
# [FRAME] Uploading 12345 bytes to https://smoki-backend-rpi.onrender.com/api/stream/frame
# [FRAME] ✓ Upload successful: {"success":true,"fps":1,"buffered_frames":5}
```

## Common Issues & Solutions

### Issue 1: "Connection error - cannot reach backend"

**Cause**: RPi can't reach the backend URL

**Solution**:
```bash
# Check internet connection
ping 8.8.8.8

# Check DNS resolution
nslookup smoki-backend-rpi.onrender.com

# Try with IP if DNS fails
curl https://1.2.3.4/api/health  # Replace with actual IP
```

### Issue 2: "Timeout - network may be slow"

**Cause**: Network is too slow or backend is slow to respond

**Solution**:
```bash
# Check network speed
speedtest-cli

# If slow, reduce frame quality in script:
# Change IMWRITE_JPEG_QUALITY from 70 to 50
```

### Issue 3: "Upload failed: 404"

**Cause**: Endpoint doesn't exist or backend not deployed

**Solution**:
```bash
# Check if endpoint exists
curl https://smoki-backend-rpi.onrender.com/api/stream/status

# If 404, backend needs to be redeployed
```

### Issue 4: "Upload failed: 500"

**Cause**: Backend error processing the frame

**Solution**:
```bash
# Check backend logs in Render dashboard
# Look for errors in /api/stream/frame endpoint
```

## Quick Checklist

- [ ] `API_URL` environment variable is set correctly
- [ ] Backend is reachable: `curl https://smoki-backend-rpi.onrender.com/api/health`
- [ ] Frame upload endpoint works: `curl -X POST ... /api/stream/frame`
- [ ] RPi has internet connection: `ping 8.8.8.8`
- [ ] Network speed is adequate: `speedtest-cli`
- [ ] Backend logs show frame uploads: Check Render dashboard

## Environment Setup

On your RPi, add to `~/.bashrc`:

```bash
export API_URL=https://smoki-backend-rpi.onrender.com
export DEVICE_ID=cam_001
export SEND_DETECTIONS=true
```

Then reload:
```bash
source ~/.bashrc
```

## Running as Systemd Service

Create `/etc/systemd/system/rpi-camera.service`:

```ini
[Unit]
Description=RPi Camera Stream to Render
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi
Environment="API_URL=https://smoki-backend-rpi.onrender.com"
Environment="DEVICE_ID=cam_001"
Environment="SEND_DETECTIONS=true"
ExecStart=/usr/bin/python3 /home/pi/rpi5_camera_stream_optimized.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable rpi-camera
sudo systemctl start rpi-camera
sudo systemctl status rpi-camera
```

View logs:
```bash
sudo journalctl -u rpi-camera -f
```

## Performance Optimization

If frames are uploading but slowly:

1. **Reduce resolution** (already done: 480x360)
2. **Lower JPEG quality** (currently 70, try 50)
3. **Use Ethernet** instead of WiFi
4. **Reduce FPS** (currently 30, try 15)

Edit the script:
```python
# Lower quality
cv2.IMWRITE_JPEG_QUALITY, 50  # was 70

# Lower FPS
time.sleep(0.067)  # ~15 FPS instead of 30
```

## Next Steps

1. Run the connectivity test
2. Check the debug output
3. Fix any issues found
4. Verify frames are uploading
5. Check frontend displays video

