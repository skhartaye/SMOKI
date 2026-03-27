import React, { useState, useEffect, useRef } from 'react';
import { AlertCircle, Wifi, WifiOff, Play, Pause } from 'lucide-react';
import '../styles/CameraViewer.css';
import { fetchWithFallback } from '../utils/apiClient';

// Updated: 2026-03-27 - Fixed frame display for production deployment
function WebRTCViewer() {
  const [isStreaming, setIsStreaming] = useState(false);
  const [isHealthy, setIsHealthy] = useState(false);
  const [error, setError] = useState(null);
  const [detections, setDetections] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [lastFrameUpdate, setLastFrameUpdate] = useState(null);
  const [nextRefreshIn, setNextRefreshIn] = useState(5);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const imageRef = useRef(null);
  const detectionIntervalRef = useRef(null);
  const frameIntervalRef = useRef(null);
  const countdownIntervalRef = useRef(null);
  const isStreamingRef = useRef(false);

  const API_URL = import.meta.env.VITE_API_URL || 'https://smoki-backend-rpi.onrender.com';
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
      console.log('🚀 Auto-starting stream because camera is healthy');
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
      const response = await fetchWithFallback('/api/stream/status');
      if (response.ok) {
        const data = await response.json();
        setIsHealthy(data.status === 'active');
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
      
      console.log('🚀 Starting frame refresh mode for simple detection system');

      // Start polling for latest frame every 5 seconds
      frameIntervalRef.current = setInterval(async () => {
        console.log('⏰ 5-second interval triggered, isStreaming:', isStreamingRef.current);
        if (!isStreamingRef.current) {
          console.log('❌ Skipping fetch - not streaming');
          return;
        }

        try {
          // Get latest frame from simple detection system using fetchWithFallback
          setIsRefreshing(true);
          console.log('🔍 Fetching new frame...');
          const response = await fetchWithFallback('/api/stream/latest.jpg');
          console.log('📡 Response status:', response.status);
          
          if (response.ok) {
            const blob = await response.blob();
            console.log('📦 Blob size:', blob.size, 'bytes');
            const frameUrl = URL.createObjectURL(blob);
            
            if (imageRef.current) {
              // Clean up previous blob URL
              if (imageRef.current.src.startsWith('blob:')) {
                URL.revokeObjectURL(imageRef.current.src);
              }
              imageRef.current.src = frameUrl;
              setLastFrameUpdate(new Date());
              setNextRefreshIn(5); // Reset countdown
              
              // Add visual refresh animation
              if (imageRef.current) {
                imageRef.current.style.opacity = '0.8';
                setTimeout(() => {
                  if (imageRef.current) {
                    imageRef.current.style.opacity = '1';
                  }
                }, 200);
              }
              
              console.log(`✅ Frame updated successfully at ${new Date().toLocaleTimeString()}`);
            }
          } else {
            console.error('❌ Failed to fetch frame:', response.status, response.statusText);
          }
        } catch (err) {
          console.error('❌ Frame refresh error:', err);
        } finally {
          setIsRefreshing(false);
        }
      }, 5000); // Refresh every 5 seconds to match detection cycle

      console.log('✅ Frame interval started with ID:', frameIntervalRef.current);

      // Start countdown timer (updates every second)
      countdownIntervalRef.current = setInterval(() => {
        console.log('⏱️ Countdown tick');
        if (!isStreamingRef.current) {
          return;
        }
        setNextRefreshIn(prev => {
          const next = prev - 1;
          return next <= 0 ? 5 : next; // Reset to 5 when it reaches 0
        });
      }, 1000);

      console.log('✅ Countdown interval started with ID:', countdownIntervalRef.current);

      // Load initial frame using fetchWithFallback
      try {
        const response = await fetchWithFallback('/api/stream/latest.jpg');
        if (response.ok) {
          const blob = await response.blob();
          const initialFrameUrl = URL.createObjectURL(blob);
          
          if (imageRef.current) {
            imageRef.current.src = initialFrameUrl;
            imageRef.current.onload = () => {
              console.log('Initial frame loaded successfully');
              setLastFrameUpdate(new Date());
              setNextRefreshIn(5); // Initialize countdown
            };
            imageRef.current.onerror = (e) => {
              console.error('Failed to load initial frame:', e);
              setError('Failed to load camera frame - no frames available yet');
              // Don't stop streaming, just show error temporarily
              setTimeout(() => {
                if (isStreaming) {
                  setError(null);
                }
              }, 5000);
            };
          }
        } else {
          console.error('No initial frame available:', response.status);
          setError('No camera frames available yet');
        }
      } catch (err) {
        console.error('Failed to load initial frame:', err);
        setError('Failed to connect to camera service');
      }

    } catch (err) {
      console.error('Stream error:', err);
      setError('Failed to start frame display: ' + err.message);
      setIsStreaming(false);
    }
  };

  const stopStream = () => {
    setIsStreaming(false);
    isStreamingRef.current = false;
    
    console.log('🛑 Stopping stream and clearing intervals');
    
    // Clear frame refresh interval
    if (frameIntervalRef.current) {
      clearInterval(frameIntervalRef.current);
      frameIntervalRef.current = null;
      console.log('✅ Frame interval cleared');
    }
    
    // Clear countdown interval
    if (countdownIntervalRef.current) {
      clearInterval(countdownIntervalRef.current);
      countdownIntervalRef.current = null;
      console.log('✅ Countdown interval cleared');
    }
    
    if (imageRef.current) {
      // Clean up blob URL if it exists
      if (imageRef.current.src.startsWith('blob:')) {
        URL.revokeObjectURL(imageRef.current.src);
      }
      imageRef.current.src = '';
    }
    
    setNextRefreshIn(5);
  };

  const startDetectionPolling = () => {
    detectionIntervalRef.current = setInterval(async () => {
      try {
        // Get stream status which includes latest detection metadata
        const response = await fetchWithFallback('/api/stream/status');
        
        if (response.ok) {
          const data = await response.json();
          if (data.latest_detections && data.latest_detections.length > 0) {
            // Convert detection format to match expected structure
            const formattedDetections = data.latest_detections.map(det => ({
              timestamp: data.camera_info?.timestamp || new Date().toISOString(),
              location: data.camera_info?.location || 'Unknown',
              metadata: {
                detections: [{
                  class: det.class_name,
                  conf: det.confidence
                }]
              }
            }));
            setDetections(formattedDetections.slice(0, 5)); // Limit to 5 most recent
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
        <h2>Live Camera Feed (Frame Detection)</h2>
        <div className="camera-status">
          {isHealthy ? (
            <>
              <Wifi size={20} className="status-icon healthy" />
              <span className="status-text">Connected</span>
              {lastFrameUpdate && (
                <span className="last-update-text">
                  • Last: {lastFrameUpdate.toLocaleTimeString()} 
                  <span className="update-indicator">🔄</span>
                </span>
              )}
              {isStreaming && (
                <span className="next-refresh-text">
                  • Next: {nextRefreshIn}s {isRefreshing && '⏳'}
                </span>
              )}
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
              <div style={{ position: 'relative', width: '100%', height: '100%' }}>
                <img
                  ref={imageRef}
                  className="camera-stream"
                  alt="Camera feed"
                  style={{ 
                    width: '100%', 
                    height: '100%', 
                    objectFit: 'cover',
                    display: error ? 'none' : 'block'
                  }}
                />
                {error && (
                  <div className="camera-placeholder">
                    <div className="placeholder-icon">📹</div>
                    <p>Waiting for camera frames...</p>
                    <p className="placeholder-hint">RPi detection system starting up</p>
                  </div>
                )}
              </div>
            ) : (
              <div className="camera-placeholder">
                <div className="placeholder-icon">📹</div>
                <p>Camera stream not active</p>
                <p className="placeholder-hint">Click play to start frame display</p>
              </div>
            )}
          </div>

          <div className="camera-controls">
            {isHealthy && (
              <>
                <button
                  className={`stream-button ${isStreaming ? 'active' : ''}`}
                  onClick={isStreaming ? stopStream : startStream}
                >
                  {isStreaming ? (
                    <>
                      <Pause size={18} />
                      <span>Stop Display</span>
                    </>
                  ) : (
                    <>
                      <Play size={18} />
                      <span>Start Display</span>
                    </>
                  )}
                </button>
                
                {isStreaming && (
                  <button
                    className="refresh-button"
                    onClick={async () => {
                      console.log('🔄 Manual refresh triggered');
                      try {
                        const response = await fetchWithFallback('/api/stream/latest.jpg');
                        console.log('📡 Manual refresh response:', response.status);
                        if (response.ok) {
                          const blob = await response.blob();
                          console.log('📦 Manual refresh blob size:', blob.size);
                          const frameUrl = URL.createObjectURL(blob);
                          if (imageRef.current) {
                            if (imageRef.current.src.startsWith('blob:')) {
                              URL.revokeObjectURL(imageRef.current.src);
                            }
                            imageRef.current.src = frameUrl;
                            setLastFrameUpdate(new Date());
                            console.log('✅ Manual refresh successful');
                          }
                        }
                      } catch (err) {
                        console.error('❌ Manual refresh failed:', err);
                      }
                    }}
                  >
                    🔄 Refresh Now
                  </button>
                )}
                
                {isStreaming && (
                  <button
                    className="test-button"
                    onClick={() => {
                      const testUrl = 'https://smoki-backend-rpi.onrender.com/api/stream/latest.jpg';
                      console.log('🧪 Testing direct URL:', testUrl);
                      window.open(testUrl, '_blank');
                    }}
                  >
                    🧪 Test URL
                  </button>
                )}
              </>
            )}
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

export default WebRTCViewer;
