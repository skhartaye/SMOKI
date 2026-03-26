# RPi Simple Detection System

A simplified 5-second detection cycle for the Smoki project that captures frames, runs AI inference, and sends results to the backend dashboard.

## Overview

Instead of continuous streaming with complex threading, this approach:
1. **Captures** a frame from the camera
2. **Runs AI inference** on smoke, vehicle, and license plate detection
3. **Sends results** to the backend with the annotated frame
4. **Waits 5 seconds** and repeats

This is perfect for monitoring applications where you need periodic detection rather than real-time streaming.

## Files

- `rpi_simple_detect.py` - Main detection script
- `check_simple_detect.py` - System health check
- `run_simple_detect.sh` - Easy run script
- `.env.rpi` - Configuration file

## Quick Start

1. **Check system health:**
   ```bash
   python3 check_simple_detect.py
   ```

2. **Run detection system:**
   ```bash
   ./run_simple_detect.sh
   # or directly:
   python3 rpi_simple_detect.py
   ```

## Configuration

Edit `.env.rpi` to configure:

```bash
# Backend API
API_URL=https://smoki-backend-rpi.onrender.com
DEVICE_ID=cam_001
CAMERA_LOCATION=Main_Entrance

# Camera settings
CAMERA_RESOLUTION_WIDTH=640
CAMERA_RESOLUTION_HEIGHT=640
```

## Expected Output

```
🎥 RPi AI Detection System - 5 Second Cycles
==================================================
[INFO] Initializing camera...
✓ Camera ready
[INFO] Loading AI models...
✓ Loaded: smoke-hailo8l.hef
✓ Loaded: license-plate-opt-hailo8l.hef
✓ Loaded: vehicle-class-hailo8l.hef
[INFO] Configuring models...
✓ Configured: smoke-hailo8l.hef
✓ Configured: license-plate-opt-hailo8l.hef
✓ Configured: vehicle-class-hailo8l.hef

🎯 AI Detection System Ready
📍 Location: Main_Entrance
🔗 Backend: https://smoki-backend-rpi.onrender.com
⏱️  Detection cycle: Every 5 seconds
🤖 Models: 3 loaded

[Cycle 1] Starting detection...
✓ Sent: 45123B | 12 dets | 2🔥 8🚗 2🔢
[Cycle 1] Complete in 2.34s | Inference: 890ms
[Cycle 1] Waiting 2.7s for next cycle...

[Cycle 2] Starting detection...
...
```

## Dashboard Integration

The system sends frames and detection metadata to:
- **Frame endpoint:** `POST /api/stream/frame`
- **Detection data:** Included in frame metadata

View results on the dashboard at your backend URL.

## Troubleshooting

### Camera Issues
```bash
# Check camera permissions
sudo usermod -a -G video $USER
# Reboot after adding to video group
sudo reboot
```

### Hailo Issues
```bash
# Check Hailo device
lspci | grep Hailo
# Should show: Hailo Technologies Ltd. Hailo-8 AI Processor
```

### Backend Issues
```bash
# Test backend connectivity
curl https://smoki-backend-rpi.onrender.com/api/health
```

### Model Files
Ensure model files exist at:
- `/home/sevi/smoki_project/src/model-skhart-ready/smoke-hailo8l.hef`
- `/home/sevi/smoki_project/src/model-skhart-ready/license-plate-opt-hailo8l.hef`
- `/home/sevi/smoki_project/src/model-skhart-ready/vehicle-class-hailo8l.hef`

## Performance

- **Cycle time:** ~2-3 seconds (inference + upload)
- **Wait time:** ~2-3 seconds (to reach 5-second total)
- **Memory usage:** ~500MB (models loaded once)
- **CPU usage:** Moderate during inference, low during wait

## Advantages over Streaming

1. **Simpler architecture** - No complex threading
2. **Lower resource usage** - Only active during detection
3. **More reliable** - Less prone to threading issues
4. **Easier debugging** - Clear cycle-based logging
5. **Dashboard focused** - Perfect for monitoring use case

## Next Steps

- Monitor dashboard for detection results
- Adjust detection confidence thresholds if needed
- Scale to multiple cameras by running multiple instances