import React, { useState, useEffect, useRef } from 'react';
import { AlertCircle, Wifi, WifiOff, Play, Pause, Zap } from 'lucide-react';
import '../styles/CameraViewer.css';

function WebRTCViewer() {
  const [isStreaming, setIsStreaming] = useState(false);
  const [isHealthy, setIsHealthy] = useState(false);
  const [error, setError] = useState(null);
  const [detections, setDetections] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const videoRef = useRef(null);
  const detectionIntervalRef = useRef(null);

  const API_URL = import.meta.env.VITE_API_URL || 'https://smoki-backend-rpi.onrender.com';
  const RPI_IP = import.meta.env.VITE_RPI_IP || '192.168.100.198';
  const token = localStorage.getItem('token');

  useEffect(() => {
    checkCameraHealth();
    const healthInterval = setInterval(checkCameraHealth, 10000);
    return () => {
      clearInterval(healthInterval);
      stopStream();
    };
  }, []);

  // Autoplay stream when component mounts
  useEffect(() => {
    if (isHealthy && !isStreaming && !isLoading) {
      startStream();
    }
  }, [isHealthy, isLoading]);

  useEffect(() => {
    if (isStreaming) {
      startDetectionPolling();
    } else {
      stopDetectionPolling();
    }
    return () => stopDetectionPolling();
  }, [isStreaming]);

  const checkCameraHealth = async () => {
    try {
      const response = await fetch(`${API_URL}/api/camera/health`);
      if (response.ok) {
        setIsHealthy(true);
        setError(null);
      } else {
        setIsHealthy(false);
        setError('Camera service unavailable');
      }
    } catch (err) {
      setIsHealthy(false);
      setError('Failed to connect to camera service');
    } finally {
      setIsLoading(false);
    }
  };

  const startStream = async () => {
    try {
      setError(null);
      setIsStreaming(true);
      
      // Wait for video element to mount
      await new Promise(resolve => {
        const checkRef = () => {
          if (videoRef.current) {
            resolve();
          } else {
            setTimeout(checkRef, 50);
          }
        };
        checkRef();
      });

      const video = videoRef.current;
      if (!video) {
        setError('Video element not available');
        setIsStreaming(false);
        return;
      }

      console.log('Video element found:', video);

      // Load HLS stream
      const hlsUrl = `http://${RPI_IP}:8000/stream.m3u8`;
      console.log('Loading HLS stream:', hlsUrl);

      // Check if HLS.js is available
      if (window.Hls) {
        console.log('HLS.js available');
        const hls = new window.Hls({
          debug: false,
          enableWorker: true,
          lowLatencyMode: true,
          backBufferLength: 1,
          maxBufferLength: 2,
          maxMaxBufferLength: 3,
          targetLatency: 4
        });
        
        hls.loadSource(hlsUrl);
        hls.attachMedia(video);
        
        hls.on(window.Hls.Events.MANIFEST_PARSED, () => {
          console.log('HLS manifest parsed, starting playback');
          video.play().catch(e => console.error('Play error:', e));
        });

        // Skip to live edge if player falls behind
        hls.on(window.Hls.Events.FRAG_BUFFERED, () => {
          if (video.buffered.length > 0) {
            const bufferedEnd = video.buffered.end(video.buffered.length - 1);
            const duration = video.duration;
            
            // If more than 6 seconds behind live edge, skip ahead
            if (duration && bufferedEnd - video.currentTime > 6) {
              console.log(`Skipping ahead: ${video.currentTime.toFixed(1)}s -> ${(bufferedEnd - 1).toFixed(1)}s`);
              video.currentTime = bufferedEnd - 1;
            }
          }
        });
        
        hls.on(window.Hls.Events.ERROR, (event, data) => {
          console.error('HLS error:', data);
          if (data.fatal) {
            setError('HLS stream error: ' + data.reason);
            setIsStreaming(false);
          }
        });
      } else {
        console.log('HLS.js not available, using native HLS');
        video.src = hlsUrl;
        video.addEventListener('loadedmetadata', () => {
          console.log('Video metadata loaded');
          video.play().catch(e => console.error('Play error:', e));
        });
        video.addEventListener('error', (e) => {
          console.error('Video error:', e);
          setError('Failed to load stream');
          setIsStreaming(false);
        });
      }

    } catch (err) {
      console.error('Stream error:', err);
      setError('Failed to start stream: ' + err.message);
      setIsStreaming(false);
    }
  };

  const stopStream = () => {
    setIsStreaming(false);
    
    if (videoRef.current) {
      videoRef.current.pause();
      videoRef.current.src = '';
    }
  };

  const startDetectionPolling = () => {
    detectionIntervalRef.current = setInterval(async () => {
      try {
        const response = await fetch(`${API_URL}/api/vehicles/violations/recent?limit=5`, {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        });

        if (response.ok) {
          const data = await response.json();
          if (data.success && data.data) {
            setDetections(data.data);
          }
        }
      } catch (err) {
        console.error('Detection polling error:', err);
      }
    }, 2000);
  };

  const stopDetectionPolling = () => {
    if (detectionIntervalRef.current) {
      clearInterval(detectionIntervalRef.current);
      detectionIntervalRef.current = null;
    }
  };

  return (
    <div className="camera-viewer">
      <div className="camera-header">
        <h2>Live Camera Feed (HLS)</h2>
        <div className="camera-status">
          {isHealthy ? (
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

      {isLoading ? (
        <div className="camera-loading">
          <div className="spinner"></div>
          <p>Checking camera service...</p>
        </div>
      ) : (
        <>
          <div className="camera-stream-container">
            {isStreaming ? (
              <video
                ref={videoRef}
                className="camera-stream"
                controls
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
            {isHealthy && (
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
            )}
          </div>

          {detections.length > 0 && (
            <div className="detections-panel">
              <h3>Detected Vehicles ({detections.length})</h3>
              <div className="detections-list">
                {detections.map((detection, idx) => (
                  <div key={idx} className="detection-item">
                    <div className="detection-plate">
                      {detection.license_plate}
                    </div>
                    <div className="detection-info">
                      <span className="confidence">
                        {(detection.confidence * 100).toFixed(1)}%
                      </span>
                      {detection.smoke_detected && (
                        <span className="smoke-badge">
                          🔴 Smoke: {detection.emission_level}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default WebRTCViewer;
