import React, { useState, useEffect, useRef } from 'react';
import { AlertCircle, Wifi, WifiOff, Play, Pause } from 'lucide-react';
import '../styles/CameraViewer.css';

function CameraViewer() {
  const [isStreaming, setIsStreaming] = useState(false);
  const [isHealthy, setIsHealthy] = useState(false);
  const [error, setError] = useState(null);
  const [detections, setDetections] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const imgRef = useRef(null);
  const detectionIntervalRef = useRef(null);
  const frameIntervalRef = useRef(null);
  const isStreamingRef = useRef(false);

  const API_URL = import.meta.env.VITE_API_URL || 'https://smoki-backend-rpi.onrender.com';
  const token = localStorage.getItem('token');

  // Check camera health on mount
  useEffect(() => {
    checkCameraHealth();
    const healthInterval = setInterval(checkCameraHealth, 10000);
    return () => {
      clearInterval(healthInterval);
      stopStream();
    };
  }, []);

  // Start/stop detection polling
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
      isStreamingRef.current = true;
      
      // Fetch frames as fast as possible without blocking
      const fetchFrame = async () => {
        if (!isStreamingRef.current) return;
        
        try {
          const response = await fetch(`${API_URL}/api/stream/latest.jpg`);
          if (response.ok) {
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            if (imgRef.current) {
              imgRef.current.src = url;
            }
          }
        } catch (err) {
          console.error('Frame fetch error:', err);
        }
        
        // Schedule next frame immediately (non-blocking)
        if (isStreamingRef.current) {
          requestAnimationFrame(fetchFrame);
        }
      };
      
      // Start fetching frames
      requestAnimationFrame(fetchFrame);
      
    } catch (err) {
      console.error('Start stream error:', err);
      setError('Failed to start stream');
      setIsStreaming(false);
      isStreamingRef.current = false;
    }
  };

  const stopStream = () => {
    setIsStreaming(false);
    isStreamingRef.current = false;
    if (imgRef.current) {
      imgRef.current.src = '';
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
    }, 2000); // Poll every 2 seconds
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
        <h2>Live Camera Feed</h2>
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
              <img
                ref={imgRef}
                alt="Camera Stream"
                className="camera-stream"
                onError={() => {
                  setError('Stream connection lost');
                  setIsStreaming(false);
                }}
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

export default CameraViewer;
