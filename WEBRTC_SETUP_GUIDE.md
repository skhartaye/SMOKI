# WebRTC Camera Streaming Setup Guide

Your frontend is now configured to use WebRTC streaming. Follow these steps to get it working:

## Step 1: Install go2rtc (Modern WebRTC Server)

SSH into your RPi and run:

```bash
# Download go2rtc (works on RPi 4/5 with libcamera)
cd /tmp
wget https://github.com/AlexxIT/go2rtc/releases/download/v1.8.5/go2rtc_linux_arm64
chmod +x go2rtc_linux_arm64

# Move to /usr/local/bin
sudo mv go2rtc_linux_arm64 /usr/local/bin/go2rtc

# Verify installation
go2rtc --version
```

## Step 2: Create go2rtc Configuration

Create the config file:

```bash
sudo nano /etc/go2rtc/config.yaml
```

Add this configuration:

```yaml
# go2rtc configuration
rtc:
  listen: :8080
  candidates:
    - 192.168.1.100  # Replace with your RPi IP
    - mdns

streams:
  camera:
    - rtsp://127.0.0.1:554/stream  # libcamera RTSP stream
```

Save with `Ctrl+X`, then `Y`, then `Enter`.

## Step 3: Start libcamera RTSP Server

First, install libcamera tools:

```bash
sudo apt-get update
sudo apt-get install -y libcamera-tools libcamera-apps
```

Create a systemd service for libcamera RTSP:

```bash
sudo nano /etc/systemd/system/libcamera-rtsp.service
```

Add:

```ini
[Unit]
Description=libcamera RTSP Server
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/libcamera-rtsp -o /tmp/rtsp.log
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Save and enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable libcamera-rtsp
sudo systemctl start libcamera-rtsp
```

## Step 4: Start go2rtc Service

Create a systemd service:

```bash
sudo nano /etc/systemd/system/go2rtc.service
```

Add:

```ini
[Unit]
Description=go2rtc WebRTC Server
After=network.target libcamera-rtsp.service

[Service]
Type=simple
ExecStart=/usr/local/bin/go2rtc -c /etc/go2rtc/config.yaml
Restart=on-failure
RestartSec=5
User=pi

[Install]
WantedBy=multi-user.target
```

Save and enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable go2rtc
sudo systemctl start go2rtc
```

## Step 5: Verify Services are Running

```bash
# Check both services
sudo systemctl status libcamera-rtsp
sudo systemctl status go2rtc

# Test locally on RPi
curl http://localhost:8080/api/streams
```

You should see your camera stream listed.

## Step 5: Update Frontend Configuration

The WebRTC URL is configured in `frontend/.env`:

```
VITE_RPI_WEBRTC_URL=ws://192.168.1.100:8080/api/streams/camera/webrtc
```

**Replace `192.168.1.100` with your actual RPi IP address.**

To find your RPi IP:
```bash
hostname -I
```

## Step 6: Test the Connection

1. Start your frontend dev server
2. Navigate to the dashboard
3. Click "Start Stream" on the camera viewer
4. Check browser console (F12) for connection logs

### Expected Console Output:
```
WebSocket connected to go2rtc
Received answer from go2rtc
Received ICE candidate
```

## Troubleshooting

### WebSocket Connection Failed
- Verify RPi IP is correct: `hostname -I` on RPi
- Check port 8080 is open: `sudo ufw allow 8080`
- Verify both services are running: `sudo systemctl status libcamera-rtsp go2rtc`

### No Video Appears
- Check browser console for errors (F12)
- Verify camera is enabled: `raspi-config` → Interfacing Options → Camera
- Test go2rtc web interface: `http://<rpi-ip>:8080`
- Check libcamera is working: `libcamera-hello --list-cameras`

### High Latency
- Reduce resolution in libcamera config
- Use Ethernet instead of WiFi if possible
- Check CPU usage: `top` on RPi

### Services Won't Start
```bash
# Check libcamera logs
journalctl -u libcamera-rtsp -f

# Check go2rtc logs
journalctl -u go2rtc -f

# Restart services
sudo systemctl restart libcamera-rtsp go2rtc
```

## Performance Metrics

| Metric | Expected |
|--------|----------|
| Latency | 100-500ms |
| FPS | 30 |
| Bandwidth | 1-3 Mbps |
| CPU Usage | 20-30% |

## Network Requirements

- RPi and frontend must be on same network (or VPN)
- Port 8080 must be accessible from frontend
- WebSocket support required (all modern browsers)

## Next Steps

Once WebRTC is working:
1. Test with multiple concurrent viewers
2. Monitor CPU/bandwidth usage
3. Adjust resolution/framerate as needed
4. Consider adding authentication to UV4L endpoint
