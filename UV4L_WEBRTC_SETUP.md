# UV4L WebRTC Setup for RPi Camera Streaming

UV4L provides low-latency WebRTC streaming directly from the RPi camera. This is much better than polling frames.

## Installation on RPi

### 1. Install UV4L

```bash
# Add UV4L repository
curl http://www.linux-projects.org/listing/uv4l_repo.gpg.key | sudo apt-key add -
sudo nano /etc/apt/sources.list.d/uv4l.list
```

Add this line:
```
deb http://www.linux-projects.org/listing/uv4l_repo/raspbian/stretch stretch main
```

Then install:
```bash
sudo apt-get update
sudo apt-get install uv4l uv4l-raspicam uv4l-raspicam-extras uv4l-webrtc
```

### 2. Configure UV4L

Edit the config file:
```bash
sudo nano /etc/uv4l/uv4l-raspicam.conf
```

Key settings:
```ini
# Camera settings
width = 640
height = 480
framerate = 30
quality = 80

# WebRTC settings
webrtc-enable-audio = no
webrtc-receive-audio = no
webrtc-datachannel = yes

# Server settings
port = 8080
```

### 3. Start UV4L Service

```bash
# Start the service
sudo systemctl start uv4l_raspicam

# Enable on boot
sudo systemctl enable uv4l_raspicam

# Check status
sudo systemctl status uv4l_raspicam
```

### 4. Access the Stream

- **Local**: http://192.168.1.100:8080
- **WebRTC Stream**: ws://192.168.1.100:8080/stream/webrtc

## Frontend Setup

### 1. Install WebRTC Library

```bash
cd frontend
npm install simple-peer
```

### 2. Create WebRTC Component

Create `frontend/src/component/WebRTCViewer.jsx`:

```jsx
import React, { useState, useEffect, useRef } from 'react';
import { AlertCircle, Wifi, WifiOff, Play, Pause } from 'lucide-react';
import '../styles/CameraViewer.css';

function WebRTCViewer() {
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState(null);
  const videoRef = useRef(null);
  const peerConnectionRef = useRef(null);

  const RPI_IP = '192.168.1.100'; // Change to your RPi IP
  const RPI_PORT = 8080;

  const startStream = async () => {
    try {
      setError(null);
      setIsStreaming(true);

      const video = videoRef.current;
      if (!video) {
        setError('Video element not available');
        return;
      }

      // Create WebRTC peer connection
      const peerConnection = new RTCPeerConnection({
        iceServers: [{ urls: ['stun:stun.l.google.com:19302'] }]
      });

      peerConnectionRef.current = peerConnection;

      // Handle remote stream
      peerConnection.ontrack = (event) => {
        console.log('Received remote stream');
        video.srcObject = event.streams[0];
      };

      // Connect to UV4L WebRTC endpoint
      const wsUrl = `ws://${RPI_IP}:${RPI_PORT}/stream/webrtc`;
      const ws = new WebSocket(wsUrl);

      ws.onopen = async () => {
        console.log('WebSocket connected');
        
        // Create offer
        const offer = await peerConnection.createOffer();
        await peerConnection.setLocalDescription(offer);
        
        // Send offer to UV4L
        ws.send(JSON.stringify({
          type: 'offer',
          sdp: offer.sdp
        }));
      };

      ws.onmessage = async (event) => {
        const message = JSON.parse(event.data);
        
        if (message.type === 'answer') {
          await peerConnection.setRemoteDescription(
            new RTCSessionDescription({
              type: 'answer',
              sdp: message.sdp
            })
          );
        } else if (message.type === 'candidate') {
          await peerConnection.addIceCandidate(
            new RTCIceCandidate(message.candidate)
          );
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        setError('WebSocket connection failed');
        setIsStreaming(false);
      };

      ws.onclose = () => {
        console.log('WebSocket closed');
        setIsStreaming(false);
      };

      // Handle ICE candidates
      peerConnection.onicecandidate = (event) => {
        if (event.candidate && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({
            type: 'candidate',
            candidate: event.candidate
          }));
        }
      };

    } catch (err) {
      console.error('Stream error:', err);
      setError('Failed to start stream: ' + err.message);
      setIsStreaming(false);
    }
  };

  const stopStream = () => {
    setIsStreaming(false);
    if (peerConnectionRef.current) {
      peerConnectionRef.current.close();
      peerConnectionRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
  };

  return (
    <div className="camera-viewer">
      <div className="camera-header">
        <h2>Live Camera Feed (WebRTC)</h2>
        <div className="camera-status">
          {isStreaming ? (
            <>
              <Wifi size={20} className="status-icon healthy" />
              <span className="status-text">Connected</span>
            </>
          ) : (
            <>
              <WifiOff size={20} className="status-icon unhealthy" />
              <span className="status-text">Disconnected</span>
            </>
          )}
        </div>
      </div>

      {error && (
        <div className="camera-error">
          <AlertCircle size={20} />
          <span>{error}</span>
        </div>
      )}

      <div className="camera-stream-container">
        {isStreaming ? (
          <video
            ref={videoRef}
            className="camera-stream"
            autoPlay
            muted
            playsInline
          />
        ) : (
          <div className="camera-placeholder">
            <div className="placeholder-icon">📹</div>
            <p>Camera stream not active</p>
            <p className="placeholder-hint">Click play to start streaming</p>
          </div>
        )}
      </div>

      <div className="camera-controls">
        <button
          className={`stream-button ${isStreaming ? 'active' : ''}`}
          onClick={isStreaming ? stopStream : startStream}
        >
          {isStreaming ? (
            <>
              <Pause size={18} />
              <span>Stop Stream</span>
            </>
          ) : (
            <>
              <Play size={18} />
              <span>Start Stream</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
}

export default WebRTCViewer;
```

### 3. Update Dashboard to Use WebRTC

Replace the CameraViewer import in Dashboard.jsx:

```jsx
import WebRTCViewer from './component/WebRTCViewer';

// Then use it:
<WebRTCViewer />
```

## Benefits of UV4L WebRTC

✅ **Low Latency** - 100-500ms (vs 1-2 seconds with polling)
✅ **Smooth Video** - Native video codec support
✅ **Efficient** - Uses WebRTC for optimal streaming
✅ **Scalable** - Can handle multiple viewers
✅ **No Polling** - True streaming protocol

## Troubleshooting

### UV4L not starting
```bash
sudo systemctl status uv4l_raspicam
sudo journalctl -u uv4l_raspicam -f
```

### WebSocket connection fails
- Check RPi IP address is correct
- Verify port 8080 is open
- Check firewall: `sudo ufw allow 8080`

### No video in browser
- Check browser console for errors
- Verify WebRTC is supported (Chrome, Firefox, Safari)
- Check RPi camera is enabled: `raspi-config`

### High latency
- Reduce resolution in UV4L config
- Reduce framerate
- Use Ethernet instead of WiFi

## Performance

| Metric | Value |
|--------|-------|
| Latency | 100-500ms |
| FPS | 30 |
| Bandwidth | 1-3 Mbps |
| CPU Usage | 20-30% |

## Next Steps

1. Install UV4L on RPi
2. Configure and start service
3. Test at http://192.168.1.100:8080
4. Update frontend to use WebRTC
5. Deploy and test

