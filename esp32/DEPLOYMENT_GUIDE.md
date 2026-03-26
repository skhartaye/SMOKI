# 🚀 Simple Detection System - Deployment Guide

Complete guide for deploying the RPi Simple Detection System in production.

## 📋 Prerequisites

### Hardware Requirements
- Raspberry Pi 5 with Hailo-8L AI accelerator
- Camera module (compatible with Picamera2)
- MicroSD card (32GB+ recommended)
- Stable internet connection

### Software Requirements
- Raspberry Pi OS (64-bit)
- Python 3.9+
- Hailo Platform SDK
- Required Python packages

## 🔧 Installation Steps

### 1. System Setup
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install system dependencies
sudo apt install -y python3-pip python3-venv git curl

# Add user to video group for camera access
sudo usermod -a -G video $USER
# Reboot after adding to video group
sudo reboot
```

### 2. Install Python Dependencies
```bash
# Install required packages
pip3 install opencv-python numpy requests picamera2 python-dotenv

# Verify Hailo platform (should be pre-installed with Hailo SDK)
python3 -c "import hailo_platform; print('Hailo platform OK')"
```

### 3. Deploy Detection System
```bash
# Navigate to project directory
cd /home/sevi/smoki_project/src/model-skhart-ready

# Make deployment script executable
chmod +x deploy_simple_detect.sh

# Run deployment (will check everything and start system)
./deploy_simple_detect.sh
```

## ⚙️ Configuration

### Environment Variables (.env.rpi)
```bash
# Backend Configuration
API_URL=https://smoki-backend-rpi.onrender.com
DEVICE_ID=cam_001
CAMERA_LOCATION=Main_Entrance

# Optional: Camera Settings
CAMERA_RESOLUTION_WIDTH=640
CAMERA_RESOLUTION_HEIGHT=480
```

## 🔄 Auto-Start Service

### Install as System Service
```bash
# Copy service file
sudo cp smoki-detect.service /etc/systemd/system/

# Enable and start service
sudo systemctl enable smoki-detect.service
sudo systemctl start smoki-detect.service

# Check status
sudo systemctl status smoki-detect.service
```

### Service Management
```bash
# Start service
sudo systemctl start smoki-detect

# Stop service
sudo systemctl stop smoki-detect

# Restart service
sudo systemctl restart smoki-detect

# View logs
sudo journalctl -u smoki-detect -f
```

## 📊 Monitoring

### View Live Stream
- **Latest Frame**: `https://smoki-backend-rpi.onrender.com/api/stream/latest.jpg`
- **MJPEG Stream**: `https://smoki-backend-rpi.onrender.com/api/stream/stream.mjpeg`
- **Stream Status**: `https://smoki-backend-rpi.onrender.com/api/stream/status`

### Check System Health
```bash
# Run health check
python3 check_simple_detect.py

# View system logs
sudo journalctl -u smoki-detect -n 50

# Monitor system resources
htop
```

## 🐛 Troubleshooting

### Common Issues

**Camera Permission Error**
```bash
# Add user to video group
sudo usermod -a -G video $USER
sudo reboot
```

**Hailo Device Not Found**
```bash
# Check Hailo device
lspci | grep Hailo
# Should show: Hailo Technologies Ltd. Hailo-8 AI Processor
```

**Backend Connection Issues**
```bash
# Test backend connectivity
curl https://smoki-backend-rpi.onrender.com/api/health
```

**Model Files Missing**
```bash
# Verify model files exist
ls -la /home/sevi/smoki_project/src/model-skhart-ready/*.hef
```

### Performance Tuning

**Optimize Detection Frequency**
- Default: 5-second cycles
- Adjust cycle timing in `rpi_simple_detect.py`

**Memory Management**
```bash
# Increase GPU memory split
sudo raspi-config
# Advanced Options > Memory Split > 128
```

## 📈 Expected Performance

- **Inference Time**: ~1.3 seconds per cycle
- **Detection Accuracy**: 5-10 realistic detections per frame
- **Memory Usage**: ~500MB
- **CPU Usage**: 60-80% during inference, <10% during wait

## 🔗 Integration

### Frontend Dashboard
The system automatically integrates with the web dashboard:
- Live MJPEG stream display
- Real-time detection statistics
- Detection history and alerts

### API Endpoints
- `POST /api/stream/frame` - Receives detection frames
- `GET /api/stream/latest.jpg` - Latest frame with detections
- `GET /api/stream/stream.mjpeg` - Live MJPEG stream
- `GET /api/stream/status` - Stream status and statistics

## 🎯 Production Checklist

- [ ] Hardware setup complete
- [ ] All dependencies installed
- [ ] Model files in place
- [ ] Environment configured
- [ ] Backend connectivity verified
- [ ] Camera permissions set
- [ ] System service enabled
- [ ] Monitoring configured
- [ ] Performance validated

## 📞 Support

For issues or questions:
1. Check logs: `sudo journalctl -u smoki-detect -f`
2. Run health check: `python3 check_simple_detect.py`
3. Verify configuration: `cat .env.rpi`
4. Test individual components: `python3 test_simple_detect.py`