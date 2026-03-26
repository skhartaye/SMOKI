import React, { useState, useEffect, useRef } from 'react';
import { AlertCircle, Wifi, WifiOff, Play, Pause } from 'lucide-react';
import '../styles/CameraViewer.css';
import { fetchWithFallback } from '../utils/apiClient';

function CameraViewer() {
  const [isStreaming, setIsStreaming] = useState(false);
  const [isHealthy, setIsHealthy] = useState(false);
  const [error, setError] = useState(null);
  const [detections, setDetections] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const videoRef = useRef(null);
  const [lastUpdate, setLastUpdate] = useState(null);

  const detectionIntervalRef = useRef(null);
  const API_URL = import.meta.env.VITE_API_URL || 'https://smoki-backend.onrender.com';
  const RPI_IP = import.meta.env.VITE_RPI_IP || '192.168.1.35';
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
      const response = await fetchWithFallback('/api/camera/health');

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
      
      console.log('Starting frame refresh mode for simple detection system');

      // Start polling for latest frame every 5 seconds
      const frameInterval = setInterval(async () => {
        if (!isStreaming) {
          clearInterval(frameInterval);
          return;
        }

        try {
          // Get latest frame from simple detection system
          const frameUrl = `${API_URL}/api/stream/latest.jpg?t=${Date.now()}`;
          
          // Update image source to trigger refresh
          if (videoRef.current) {
            videoRef.current.src = frameUrl;
            setLastUpdate(new Date());
          }
        } catch (err) {
          console.error('Frame refresh error:', err);
        }
      }, 5000); // Refresh every 5 seconds to match detection cycle

      // Store interval reference for cleanup
      videoRef.current.frameInterval = frameInterval;

      // Load initial frame
      const initialFrameUrl = `${API_URL}/api/stream/latest.jpg?t=${Date.now()}`;
      if (videoRef.current) {
        videoRef.current.src = initialFrameUrl;
        videoRef.current.onload = () => {
          console.log('Initial frame loaded successfully');
          setLastUpdate(new Date());
        };
        videoRef.current.onerror = (e) => {
          console.error('Failed to load initial frame:', e);
          setError('Failed to load camera frame');
          setIsStreaming(false);
        };
      }

    } catch (err) {
      console.error('Stream error:', err);
      setError('Failed to start frame display: ' + err.message);
      setIsStreaming(false);
    }
  };

  const stopStream = () => {
    setIsStreaming(false);
    
    if (videoRef.current) {
      // Clear frame refresh interval
      if (videoRef.current.frameInterval) {
        clearInterval(videoRef.current.frameInterval);
        videoRef.current.frameInterval = null;
      }
      
      // Clear image source
      videoRef.current.src = '';
    }
  };

  const startDetectionPolling = () => {
    detectionIntervalRef.current = setInterval(async () => {
      try {
        // Check stream status for detection metadata
        let response = await fetchWithFallback('/api/stream/status');
        
        if (response.ok) {
          const streamData = await response.json();
          console.log('Stream status:', streamData);
          
          // If we have recent detections from stream metadata, use those
          if (streamData.latest_detections) {
            setDetections(streamData.latest_detections);
            return;
          }
        }

        // Fallback: Try vehicle detections endpoint
        response = await fetchWithFallback('/api/detections/vehicle/recent?limit=5', {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        });

        if (response.ok) {
          const data = await response.json();
          if (data.success && data.data) {
            setDetections(data.data);
            return;
          }
        }
        
        // Fallback to violations endpoint
        response = await fetchWithFallback('/api/vehicles/violations/recent?limit=5', {
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
                ref={videoRef}
                className="camera-stream"
                alt="Live camera feed with AI detections"
              />
            ) : (
              <div className="camera-placeholder">
                <div className="placeholder-icon">📹</div>
                <p>Camera feed not active</p>
                <p className="placeholder-hint">Click play to start frame updates</p>
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
                    <span>Stop Feed</span>
                  </>
                ) : (
                  <>
                    <Play size={18} />
                    <span>Start Feed</span>
                  </>
                )}
              </button>
            )}
            
            {/* Last Update Indicator */}
            {isStreaming && lastUpdate && (
              <div className="last-update">
                <span className="update-label">Last update:</span>
                <span className="update-time">{lastUpdate.toLocaleTimeString()}</span>
              </div>
            )}
          </div>

          {/* Detection Statistics */}
          <div className="detection-stats">
            <div className="stat-item">
              <span className="stat-icon">🔥</span>
              <span className="stat-label">Smoke</span>
              <span className="stat-count">{detections.filter(d => d.class_name?.includes('smoke')).length}</span>
            </div>
            <div className="stat-item">
              <span className="stat-icon">🚗</span>
              <span className="stat-label">Vehicles</span>
              <span className="stat-count">{detections.filter(d => ['passenger', 'puv', 'services', 'two_wheel'].includes(d.class_name)).length}</span>
            </div>
            <div className="stat-item">
              <span className="stat-icon">🔢</span>
              <span className="stat-label">Plates</span>
              <span className="stat-count">{detections.filter(d => d.class_name === 'license_plate').length}</span>
            </div>
          </div>

          {detections.length > 0 && (
            <div className="detections-panel">
              <h3>Detected Objects ({detections.length})</h3>
              <div className="detections-list">
                {detections.map((detection, idx) => (
                  <div key={idx} className="detection-item">
                    <div className="detection-info">
                      <div className="detection-timestamp">
                        {new Date(detection.timestamp).toLocaleTimeString()}
                      </div>
                      <div className="detection-location">
                        📍 {detection.location}
                      </div>
                      {detection.metadata && detection.metadata.detections && (
                        <div className="detection-objects">
                          {detection.metadata.detections.map((obj, i) => (
                            <div key={i} className="object-item">
                              <span className="object-class">{obj.class}</span>
                              <span className="object-conf">{(obj.conf * 100).toFixed(0)}%</span>
                            </div>
                          ))}
                        </div>
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
