import React, { useState, useEffect, useRef } from 'react';
import { AlertCircle, Wifi, WifiOff, Play, Pause } from 'lucide-react';
import '../styles/CameraViewer.css';

function CameraViewer() {
  const [isStreaming, setIsStreaming] = useState(false);
  const [isHealthy, setIsHealthy] = useState(false);
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const videoRef = useRef(null);
  const [lastUpdate, setLastUpdate] = useState(null);

  // Use RPI backend directly - CORS is enabled
  const CAMERA_URL = 'https://smoki-backend-rpi.onrender.com/api/stream/latest.jpg';

  // Check camera health on mount
  useEffect(() => {
    checkCameraHealth();
  }, []);

  const checkCameraHealth = async () => {
    try {
      console.log('� Testing camera health with URL:', CAMERA_URL);
      
      const img = new Image();
      
      img.onload = () => {
        setIsHealthy(true);
        setError(null);
        setIsLoading(false);
        console.log('✅ Camera health check passed - image loaded successfully');
        console.log('📏 Image dimensions:', img.width, 'x', img.height);
      };
      
      img.onerror = (e) => {
        setIsHealthy(false);
        setError('Camera service unavailable');
        setIsLoading(false);
        console.error('❌ Camera health check failed - could not load image');
        console.error('❌ Error details:', e);
      };
      
      img.src = `${CAMERA_URL}?t=${Date.now()}`;
    } catch (err) {
      setIsHealthy(false);
      setError('Failed to connect to camera service');
      setIsLoading(false);
      console.error('❌ Camera health check error:', err);
    }
  };

  const startStream = async () => {
    try {
      setError(null);
      setIsStreaming(true);
      console.log('🚀 Starting camera stream...');
      
      // Start frame refresh interval
      const frameInterval = setInterval(() => {
        try {
          // Get latest frame with cache busting
          const frameUrl = `${CAMERA_URL}?t=${Date.now()}`;
          console.log('🔄 Refreshing frame:', frameUrl);
          
          // Update image source to trigger refresh
          if (videoRef.current) {
            videoRef.current.src = frameUrl;
            setLastUpdate(new Date());
          }
        } catch (err) {
          console.error('Frame refresh error:', err);
        }
      }, 2000); // Refresh every 2 seconds for better real-time

      // Store interval reference for cleanup
      videoRef.current.frameInterval = frameInterval;

      // Load initial frame
      const initialFrameUrl = `${CAMERA_URL}?t=${Date.now()}`;
      console.log('� Loading initial frame:', initialFrameUrl);
      
      if (videoRef.current) {
        videoRef.current.src = initialFrameUrl;
        
        videoRef.current.onload = () => {
          console.log('✅ Initial frame loaded successfully');
          console.log('� Frame dimensions:', videoRef.current.naturalWidth, 'x', videoRef.current.naturalHeight);
          setLastUpdate(new Date());
        };
        
        videoRef.current.onerror = (e) => {
          console.error('❌ Failed to load initial frame:', e);
          console.error('❌ Frame URL was:', initialFrameUrl);
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
    console.log('� Stopping camera stream...');
    
    // Clear frame refresh interval
    if (videoRef.current && videoRef.current.frameInterval) {
      clearInterval(videoRef.current.frameInterval);
      videoRef.current.frameInterval = null;
    }
  };

  return (
    <div className="camera-viewer">
      <div className="camera-header">
        <div className="camera-status">
          {isLoading ? (
            <span className="status-loading">Checking camera...</span>
          ) : isHealthy ? (
            <>
              <Wifi className="status-icon healthy" size={16} />
              <span className="status-text">Camera Online</span>
            </>
          ) : (
            <>
              <WifiOff className="status-icon unhealthy" size={16} />
              <span className="status-text">Camera Offline</span>
            </>
          )}
        </div>
        
        <div className="camera-controls">
          {!isStreaming ? (
            <button 
              onClick={startStream} 
              disabled={!isHealthy || isLoading}
              className="control-btn start-btn"
            >
              <Play size={16} />
              Start Stream
            </button>
          ) : (
            <button 
              onClick={stopStream}
              className="control-btn stop-btn"
            >
              <Pause size={16} />
              Stop Stream
            </button>
          )}
          
          {/* Test button to verify direct URL works */}
          <button 
            onClick={() => {
              const testUrl = `${CAMERA_URL}?t=${Date.now()}`;
              console.log('🧪 Testing direct URL:', testUrl);
              window.open(testUrl, '_blank');
            }}
            className="control-btn"
            style={{ marginLeft: '10px', fontSize: '12px' }}
          >
            Test URL
          </button>
        </div>
      </div>

      <div className="camera-display">
        {!isStreaming ? (
          <div className="camera-placeholder">
            <div className="placeholder-content">
              <Wifi size={48} className={isHealthy ? "healthy" : "unhealthy"} />
              <p>{isLoading ? "Checking camera status..." : isHealthy ? "Click Start Stream to view camera" : "Camera service unavailable"}</p>
              <p className="camera-url">Source: {CAMERA_URL}</p>
            </div>
          </div>
        ) : (
          <div className="camera-frame">
            <img 
              ref={videoRef}
              alt="Camera Stream"
              className="camera-image"
              style={{ maxWidth: '100%', height: 'auto' }}
            />
            {lastUpdate && (
              <div className="frame-info">
                Last updated: {lastUpdate.toLocaleTimeString()}
              </div>
            )}
          </div>
        )}
      </div>

      {error && (
        <div className="camera-error">
          <AlertCircle size={20} />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}

export default CameraViewer;