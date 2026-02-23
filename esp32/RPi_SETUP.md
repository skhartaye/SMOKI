# RPi5 Setup Guide for Render Deployment

Complete setup instructions for running the optimized HLS streaming on RPi5 with Hailo acceleration.

## Prerequisites

- RPi5 with 8GB+ RAM
- Hailo-8 accelerator installed
- PiCamera2 connected
- Ethernet or WiFi connection
- Python 3.9+

## Step 1: Install Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python dependencies
sudo apt install -y python3-pip python3-dev python3-venv

# Install FFmpeg
sudo apt install -y ffmpeg

# Install Hailo runtime (if not already installed)
# Follow: https://docs.hailo.ai/general/getting_started/

# Install Python packages
pip3 install --upgrade pip
pip3 install numpy opencv-python requests picamera2 hailo-platform
```

## Step 2: Configure Environment

### 2.1 Copy and edit the environment file

```bash
# Copy the .env.rpi file to your RPi
scp esp32/.env.rpi pi@192.168.1.100:/home/pi/.env.rpi

# Or manually create it
nano ~/.env.rpi
```

### 2.2 Update critical variables

Edit `~/.env.rpi` and set:

```bash
# Your Render backend URL (get from Render dashboard)
RENDER_BACKEND_URL=https://your-backend.onrender.com

# Path to your Hailo model
HEF_PATH=/home/pi/smoki_project/models/smoki_model_v1.hef

# Camera location identifier
CAMERA_ID=cam_001
CAMERA_LOCATION=Main_Entrance
```

### 2.3 Source the environment

```bash
# Add to ~/.bashrc for persistence
echo "source ~/.env.rpi" >> ~/.bashrc
source ~/.bashrc

# Or source manually before running
source ~/.env.rpi
```

## Step 3: Prepare Model File

```bash
# Create model directory
mkdir -p ~/smoki_project/models

# Copy your Hailo model (smoki_model_v1.hef) to:
# ~/smoki_project/models/smoki_model_v1.hef

# Verify it exists
ls -lh ~/smoki_project/models/smoki_model_v1.hef
```

## Step 4: Create RAM Disk for HLS (Optional but Recommended)

```bash
# Create RAM disk mount point
sudo mkdir -p /dev/shm/hls

# Make it writable
sudo chmod 777 /dev/shm/hls

# Verify
df -h /dev/shm
```

## Step 5: Test Locally

```bash
# Source environment
source ~/.env.rpi

# Run the script
python3 rpi5_camera_stream_optimized.py
```

Expected output:
```
[INFO] Initializing Hailo...
[INFO] Loading model: /home/pi/smoki_project/models/smoki_model_v1.hef
[INFO] Starting camera...
[INFO] HLS server running on http://192.168.1.100:8000
[INFO] Streaming to /dev/shm/hls
```

## Step 6: Create Systemd Service (For Auto-Start)

### 6.1 Create service file

```bash
sudo nano /etc/systemd/system/rpi-hls.service
```

### 6.2 Add content

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

### 6.3 Enable and start

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable on boot
sudo systemctl enable rpi-hls

# Start service
sudo systemctl start rpi-hls

# Check status
sudo systemctl status rpi-hls

# View logs
sudo journalctl -u rpi-hls -f
```

## Step 7: Verify Connectivity

### 7.1 Check local stream

```bash
# From RPi
curl http://localhost:8000/stream.m3u8

# From another machine on network
curl http://192.168.1.100:8000/stream.m3u8
```

### 7.2 Check Render backend connection

```bash
# Test backend health
curl https://your-backend.onrender.com/api/health

# Check camera health (requires auth token)
curl https://your-backend.onrender.com/api/camera/health \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Step 8: Monitor Performance

### 8.1 Check CPU/Memory usage

```bash
# Real-time monitoring
top

# Or use htop
sudo apt install htop
htop
```

Expected:
- CPU: 40-60% (Hailo offloads inference)
- Memory: 500-800MB
- Latency: 1-2 seconds

### 8.2 Check HLS files

```bash
# Monitor HLS directory
watch -n 1 'ls -lh /dev/shm/hls/'

# Check file sizes
du -sh /dev/shm/hls/
```

### 8.3 View service logs

```bash
# Last 50 lines
sudo journalctl -u rpi-hls -n 50

# Follow in real-time
sudo journalctl -u rpi-hls -f

# Filter by time
sudo journalctl -u rpi-hls --since "10 minutes ago"
```

## Troubleshooting

### Script won't start

```bash
# Check Python version
python3 --version  # Should be 3.9+

# Check dependencies
python3 -c "import hailo_platform; print('Hailo OK')"
python3 -c "import picamera2; print('PiCamera2 OK')"
python3 -c "import cv2; print('OpenCV OK')"

# Check model file
ls -lh $HEF_PATH
```

### No HLS files generated

```bash
# Check HLS directory permissions
ls -ld /dev/shm/hls
chmod 777 /dev/shm/hls

# Check FFmpeg installation
which ffmpeg
ffmpeg -version
```

### High latency

```bash
# Reduce resolution
# Edit rpi5_camera_stream_optimized.py and change:
# start_ffmpeg(480, 360, fps=15, bitrate='600k')

# Use Ethernet instead of WiFi
# Check network speed
iperf3 -c your-server-ip
```

### Detections not sending to Render

```bash
# Check backend URL
echo $RENDER_BACKEND_URL

# Test connectivity
curl -v https://your-backend.onrender.com/api/health

# Check firewall
sudo ufw status
```

### Out of memory

```bash
# Check available RAM
free -h

# Reduce HLS playlist size in .env.rpi
HLS_PLAYLIST_SIZE=3

# Reduce resolution
# Edit script to use 480x360 instead of 640x480
```

## Performance Tuning

### For better latency

```bash
# In .env.rpi
CAMERA_FPS=15
CAMERA_BITRATE=600k
HLS_SEGMENT_DURATION=1
```

### For better quality

```bash
# In .env.rpi
CAMERA_FPS=30
CAMERA_BITRATE=1200k
CAMERA_RESOLUTION_WIDTH=1280
CAMERA_RESOLUTION_HEIGHT=720
```

### For low bandwidth

```bash
# In .env.rpi
CAMERA_FPS=10
CAMERA_BITRATE=400k
CAMERA_RESOLUTION_WIDTH=480
CAMERA_RESOLUTION_HEIGHT=360
```

## Next Steps

1. ✅ Install dependencies
2. ✅ Configure environment
3. ✅ Test locally
4. ✅ Create systemd service
5. ✅ Verify Render connectivity
6. ⬜ Monitor in production
7. ⬜ Optimize performance

You're ready to stream!
