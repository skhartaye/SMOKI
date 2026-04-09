import React, { useState, useEffect, useRef } from 'react';
import { AlertCircle, Wifi, WifiOff, Play, Pause, Monitor } from 'lucide-react';
import '../styles/CameraViewer.css';

function LaptopViewer() {
  const [isStreaming, setIsStreaming] = useState(false);
  const [isHealthy, setIsHealthy] = useState(false);
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [metadata, setMetadata] = useState(null);
  const videoRef = useRef(null);
  const [lastUpdate, setLastUpdate] = useState(null);

  // Use RPI backend directly where laptop system sends frames
  const LAPTOP_FRAME_URL = `${import.meta.env.VITE_API_URL}/api/stream/latest.jpg`;
  const LAPTOP_STATUS_URL = `${import.meta.env.VITE_API_URL}/api/stream/status`;

  // Check laptop detection system health on mount
  useEffect(() => {
    checkLaptopHealth();
  }, []);

  const checkLaptopHealth = async () => {
    try {
      console.log('🔍 Testing laptop detection system health...');
      
      const response = await fetch(LAPTOP_STATUS_URL);
      if (response.ok) {
        const statusData = await response.json();
        console.log('📊 Laptop system status:', statusData);
        
        if (statusData.status === 'active' && statusData.latest_frame_size > 0) {
          setIsHealthy(true);
          setMetadata(statusData);
          setError(null);
          setIsLoading(false);
          console.log('✅ Laptop detection system is active');
        } else {
          setIsHealthy(false);
          setError('Laptop detection system not active');
          setIsLoading(false);
          console.log('❌ Laptop detection system not active');
        }
      } else {
        throw new Error(`HTTP ${response.status}`);
      }
    } catch (err) {
      setIsHealthy(false);
      setError('Failed to connect to laptop detection system');
      setIsLoading(false);
      console.error('❌ Laptop system health check error:', err);
    }
  };

  const startStream = async () => {
    try {
      setError(null);
      setIsStreaming(true);
      console.log('🚀 Starting laptop detection stream...');
      
      // Function to load image via fetch (bypasses CORS for display)
      const loadImageViaFetch = async () => {
        try {
          const response = await fetch(`${LAPTOP_FRAME_URL}?t=${Date.now()}`);
          if (response.ok) {
            const blob = await response.blob();
            const imageUrl = URL.createObjectURL(blob);
            
            if (videoRef.current) {
              // Clean up previous blob URL
              if (videoRef.current.src && videoRef.current.src.startsWith('blob:')) {
                URL.revokeObjectURL(videoRef.current.src);
              }
              videoRef.current.src = imageUrl;
              setLastUpdate(new Date());
            }
            
            return true;
          } else {
            throw new Error(`HTTP ${response.status}`);
          }
        } catch (error) {
          console.error('❌ Failed to load image via fetch:', error);
          return false;
        }
      };
      
      // Load initial image
      const initialLoad = await loadImageViaFetch();
      if (!initialLoad) {
        setError('Failed to load initial detection frame');
        setIsStreaming(false);
        return;
      }
      
      console.log('✅ Initial frame loaded successfully');
      
      // Start refresh interval
      const refreshInterval = setInterval(async () => {
        try {
          // Get latest metadata
          const statusResponse = await fetch(LAPTOP_STATUS_URL);
          if (statusResponse.ok) {
            const statusData = await statusResponse.json();
            setMetadata(statusData);
            console.log('📊 Updated metadata:', {
              detections: statusData.latest_detections?.length || 0,
              vehicles: statusData.detection_summary?.vehicle_detections || 0,
              smoke: statusData.detection_summary?.smoke_detections || 0,
              plates: statusData.detection_summary?.plate_detections || 0
            });
          }
          
          // Load new image
          await loadImageViaFetch();
          
        } catch (err) {
          console.error('Frame/metadata refresh error:', err);
        }
      }, 2000); // Refresh every 2 seconds

      // Store interval reference for cleanup
      videoRef.current.refreshInterval = refreshInterval;

    } catch (err) {
      console.error('Stream error:', err);
      setError('Failed to start laptop detection stream: ' + err.message);
      setIsStreaming(false);
    }
  };

  const stopStream = () => {
    setIsStreaming(false);
    console.log('⏹️ Stopping laptop detection stream...');
    
    // Clear refresh interval
    if (videoRef.current && videoRef.current.refreshInterval) {
      clearInterval(videoRef.current.refreshInterval);
      videoRef.current.refreshInterval = null;
    }
    
    // Clean up blob URL
    if (videoRef.current && videoRef.current.src && videoRef.current.src.startsWith('blob:')) {
      URL.revokeObjectURL(videoRef.current.src);
      videoRef.current.src = '';
    }
  };

  return (
    <div className="camera-viewer">
      <div className="camera-header">
        <div className="camera-status">
          {isLoading ? (
            <span className="status-loading">Checking laptop system...</span>
          ) : isHealthy ? (
            <>
              <Monitor className="status-icon healthy" size={16} />
              <span className="status-text">Laptop Detection Active</span>
            </>
          ) : (
            <>
              <WifiOff className="status-icon unhealthy" size={16} />
              <span className="status-text">Laptop System Offline</span>
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
              Start Detection View
            </button>
          ) : (
            <button 
              onClick={stopStream}
              className="control-btn stop-btn"
            >
              <Pause size={16} />
              Stop Detection View
            </button>
          )}
          
          {/* Test button to verify direct URL works */}
          <button 
            onClick={() => {
              const testUrl = `${LAPTOP_FRAME_URL}?t=${Date.now()}`;
              console.log('🧪 Testing direct URL:', testUrl);
              window.open(testUrl, '_blank');
            }}
            className="control-btn"
            style={{ marginLeft: '10px', fontSize: '12px' }}
          >
            Test Image URL
          </button>
        </div>
      </div>

      {/* Detection Classes Metadata */}
      {metadata && metadata.latest_detections && metadata.latest_detections.length > 0 && (
        <div className="detection-metadata">
          <div className="metadata-header">
            <span className="metadata-title">Detection Results ({metadata.latest_detections.length})</span>
            <span className="metadata-fps">FPS: {metadata.fps || 0}</span>
          </div>
          <div className="detections-list">
            {metadata.latest_detections.map((detection, index) => (
              <div key={index} className={`detection-item ${detection.class}`}>
                <span className="detection-class">{detection.class}</span>
                <span className="detection-confidence">{(detection.conf * 100).toFixed(1)}%</span>
                <span className="detection-bbox">
                  [{detection.bbox.x1}, {detection.bbox.y1}, {detection.bbox.x2}, {detection.bbox.y2}]
                </span>
              </div>
            ))}
          </div>
          <div className="metadata-footer">
            <div className="metadata-item">
              <span className="metadata-label">Camera:</span>
              <span className="metadata-value">{metadata.camera_info?.camera_id || 'laptop_camera_01'}</span>
            </div>
            <div className="metadata-item">
              <span className="metadata-label">Location:</span>
              <span className="metadata-value">{metadata.camera_info?.location || 'Main_Street_Intersection'}</span>
            </div>
            <div className="metadata-item">
              <span className="metadata-label">Frame:</span>
              <span className="metadata-value">{Math.round((metadata.latest_frame_size || 0) / 1024)}KB</span>
            </div>
          </div>
        </div>
      )}
      
      {/* Summary when no detections */}
      {metadata && (!metadata.latest_detections || metadata.latest_detections.length === 0) && (
        <div className="detection-metadata">
          <div className="metadata-header">
            <span className="metadata-title">No Active Detections</span>
            <span className="metadata-fps">FPS: {metadata.fps || 0}</span>
          </div>
          <div className="no-detections">
            <span>Monitoring for vehicles, smoke, and license plates...</span>
          </div>
          <div className="metadata-footer">
            <div className="metadata-item">
              <span className="metadata-label">Camera:</span>
              <span className="metadata-value">{metadata.camera_info?.camera_id || 'laptop_camera_01'}</span>
            </div>
            <div className="metadata-item">
              <span className="metadata-label">Location:</span>
              <span className="metadata-value">{metadata.camera_info?.location || 'Main_Street_Intersection'}</span>
            </div>
            <div className="metadata-item">
              <span className="metadata-label">Frame:</span>
              <span className="metadata-value">{Math.round((metadata.latest_frame_size || 0) / 1024)}KB</span>
            </div>
          </div>
        </div>
      )}

      <div className="camera-display">
        {!isStreaming ? (
          <div className="camera-placeholder">
            <div className="placeholder-content">
              <Monitor size={48} className={isHealthy ? "healthy" : "unhealthy"} />
              <p>{isLoading ? "Checking laptop detection system..." : isHealthy ? "Click Start Detection View to see detection results" : "Laptop detection system unavailable"}</p>
              <p className="camera-url">Source: {LAPTOP_FRAME_URL}</p>
              {metadata && (
                <div className="placeholder-stats">
                  <p>Last Detection: {metadata.detection_summary?.total_detections || 0} objects</p>
                  <p>Frame Size: {Math.round((metadata.latest_frame_size || 0) / 1024)}KB</p>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="camera-frame">
            {/* Try iframe approach for CORS bypass */}
            <iframe
              src={`${LAPTOP_FRAME_URL}?t=${Date.now()}`}
              style={{
                width: '100%',
                height: '400px',
                border: 'none',
                background: '#f0f0f0'
              }}
              title="Laptop Detection Stream"
              onLoad={() => {
                console.log('✅ Iframe loaded successfully');
                setError(null);
                setLastUpdate(new Date());
              }}
              onError={(e) => {
                console.error('❌ Iframe load error:', e);
                setError('Failed to load detection frame via iframe');
              }}
            />
            
            {/* Fallback: Direct image with different approach */}
            <div style={{ marginTop: '10px' }}>
              <a 
                href={`${LAPTOP_FRAME_URL}?t=${Date.now()}`} 
                target="_blank" 
                rel="noopener noreferrer"
                style={{ 
                  display: 'inline-block', 
                  padding: '8px 16px', 
                  background: '#007bff', 
                  color: 'white', 
                  textDecoration: 'none', 
                  borderRadius: '4px',
                  fontSize: '12px'
                }}
              >
                Open Detection Frame in New Tab
              </a>
            </div>
            
            {lastUpdate && (
              <div className="frame-info">
                <div>Last updated: {lastUpdate.toLocaleTimeString()}</div>
                {metadata && (
                  <div>Frame: {Math.round((metadata.latest_frame_size || 0) / 1024)}KB</div>
                )}
              </div>
            )}
            
            {/* Debug info */}
            <div className="debug-info" style={{ fontSize: '10px', color: '#666', marginTop: '5px' }}>
              <div>Image URL: {LAPTOP_FRAME_URL}</div>
              <div>Status URL: {LAPTOP_STATUS_URL}</div>
            </div>
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

export default LaptopViewer;