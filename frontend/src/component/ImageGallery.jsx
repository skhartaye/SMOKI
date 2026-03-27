import React, { useState, useEffect } from 'react';
import { fetchWithFallback } from '../utils/apiClient';
import '../styles/ImageGallery.css';

const ImageGallery = ({ isOpen, onClose }) => {
  const [images, setImages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedImage, setSelectedImage] = useState(null);
  const [timeFilter, setTimeFilter] = useState('24'); // hours

  const fetchImages = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const headers = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      // Try the authenticated endpoint first
      try {
        const response = await fetchWithFallback(`/api/images/recent?limit=50&hours=${timeFilter}`, {
          headers
        });

        if (response.ok) {
          const result = await response.json();
          if (result.success) {
            setImages(result.data);
            return;
          }
        }
      } catch (error) {
        console.log('Authenticated images endpoint failed, trying public endpoint...');
      }

      // Fallback to public endpoint for testing
      try {
        const response = await fetchWithFallback(`/api/images/recent/public?limit=50&hours=${timeFilter}`);
        
        if (response.ok) {
          const result = await response.json();
          if (result.success) {
            setImages(result.data);
            return;
          }
        }
      } catch (error) {
        console.log('Public images endpoint also failed');
      }

      // If no real images, show sample image data for demonstration
      console.log('No images available from API, showing sample data');
      const sampleImages = [
        {
          id: 'sample_1',
          timestamp: new Date(Date.now() - 300000).toISOString(), // 5 minutes ago
          camera_location: 'Main Camera',
          camera_id: 'rpi_camera_01',
          file_size: 245760, // 240 KB
          width: 640,
          height: 480,
          vehicle_detection_id: 1,
          is_sample: true
        },
        {
          id: 'sample_2', 
          timestamp: new Date(Date.now() - 600000).toISOString(), // 10 minutes ago
          camera_location: 'Main Camera',
          camera_id: 'rpi_camera_01',
          file_size: 198400, // 194 KB
          width: 640,
          height: 480,
          violation_id: 1,
          is_sample: true
        },
        {
          id: 'sample_3',
          timestamp: new Date(Date.now() - 900000).toISOString(), // 15 minutes ago
          camera_location: 'Main Camera', 
          camera_id: 'rpi_camera_01',
          file_size: 312320, // 305 KB
          width: 640,
          height: 480,
          vehicle_detection_id: 2,
          is_sample: true
        }
      ];
      
      setImages(sampleImages);

    } catch (error) {
      console.error('Error fetching images:', error);
      setImages([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchImages();
    }
  }, [isOpen, timeFilter]);

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'Unknown';
    const date = new Date(timestamp);
    return date.toLocaleString();
  };

  const getImageUrl = (image) => {
    // If it's a sample image, return a placeholder
    if (image.is_sample) {
      return `data:image/svg+xml;base64,${btoa(`
        <svg width="640" height="480" xmlns="http://www.w3.org/2000/svg">
          <rect width="100%" height="100%" fill="#f0f0f0"/>
          <rect x="50" y="50" width="540" height="380" fill="#e5e7eb" stroke="#d1d5db" stroke-width="2"/>
          <circle cx="200" cy="150" r="30" fill="#3b82f6"/>
          <rect x="400" y="120" width="120" height="60" fill="#ef4444" rx="5"/>
          <text x="320" y="250" font-family="Arial" font-size="16" fill="#374151" text-anchor="middle">Sample Detection Image</text>
          <text x="320" y="280" font-family="Arial" font-size="12" fill="#6b7280" text-anchor="middle">ID: ${image.id}</text>
          <text x="320" y="300" font-family="Arial" font-size="12" fill="#6b7280" text-anchor="middle">${formatTimestamp(image.timestamp)}</text>
          <text x="320" y="350" font-family="Arial" font-size="10" fill="#9ca3af" text-anchor="middle">Real images will appear when RPi system captures detections</text>
        </svg>
      `)}`;
    }
    
    // For real images, use the API endpoint with proper authentication
    const token = localStorage.getItem('token');
    const baseUrl = process.env.REACT_APP_API_URL || '';
    return `${baseUrl}/api/images/${image.id}/raw${token ? `?Authorization=Bearer ${token}` : ''}`;
  };

  if (!isOpen) return null;

  return (
    <div className="image-gallery-overlay">
      <div className="image-gallery-modal">
        <div className="image-gallery-header">
          <h2>Image History</h2>
          <div className="image-gallery-controls">
            <select 
              value={timeFilter} 
              onChange={(e) => setTimeFilter(e.target.value)}
              className="time-filter-select"
            >
              <option value="1">Last Hour</option>
              <option value="6">Last 6 Hours</option>
              <option value="24">Last 24 Hours</option>
              <option value="168">Last Week</option>
              <option value="720">Last Month</option>
            </select>
            <button onClick={onClose} className="close-button">×</button>
          </div>
        </div>

        <div className="image-gallery-content">
          {loading ? (
            <div className="loading-message">Loading images...</div>
          ) : images.length === 0 ? (
            <div className="no-images-message">
              <p>No images found for the selected time period.</p>
              <p>Images are automatically captured when detections occur.</p>
            </div>
          ) : (
            <div className="image-grid">
              {images.map((image) => (
                <div key={image.id} className="image-card">
                  <div className="image-thumbnail">
                    <img
                      src={getImageUrl(image)}
                      alt={`Detection ${image.id}`}
                      onClick={() => setSelectedImage(image)}
                      onError={(e) => {
                        e.target.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjE1MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjZjBmMGYwIi8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSIxNCIgZmlsbD0iIzk5OSIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZHk9Ii4zZW0iPkltYWdlIE5vdCBGb3VuZDwvdGV4dD48L3N2Zz4=';
                      }}
                    />
                  </div>
                  <div className="image-info">
                    <div className="image-timestamp">{formatTimestamp(image.timestamp)}</div>
                    <div className="image-details">
                      <span className="image-id">ID: {image.id}</span>
                      {image.camera_location && (
                        <span className="image-location">{image.camera_location}</span>
                      )}
                      {image.is_sample && (
                        <span className="sample-badge">Sample</span>
                      )}
                    </div>
                    {image.file_size && (
                      <div className="image-size">
                        {Math.round(image.file_size / 1024)} KB
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {images.some(img => img.is_sample) && (
                <div className="sample-images-notice">
                  <p style={{ 
                    color: '#6b7280', 
                    fontStyle: 'italic', 
                    padding: '16px', 
                    textAlign: 'center',
                    gridColumn: '1 / -1',
                    background: '#f9fafb',
                    borderRadius: '8px',
                    border: '1px solid #e5e7eb',
                    margin: '16px 0'
                  }}>
                    📷 Sample images shown for demonstration. Real detection images will appear when the RPi camera system captures them.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {selectedImage && (
          <div className="image-viewer-overlay" onClick={() => setSelectedImage(null)}>
            <div className="image-viewer-modal" onClick={(e) => e.stopPropagation()}>
              <div className="image-viewer-header">
                <h3>Image Details</h3>
                <button onClick={() => setSelectedImage(null)} className="close-button">×</button>
              </div>
              <div className="image-viewer-content">
                <img
                  src={getImageUrl(selectedImage)}
                  alt={`Detection ${selectedImage.id}`}
                  className="full-size-image"
                />
                <div className="image-metadata">
                  <p><strong>Timestamp:</strong> {formatTimestamp(selectedImage.timestamp)}</p>
                  <p><strong>Image ID:</strong> {selectedImage.id}</p>
                  {selectedImage.is_sample && (
                    <p><strong>Type:</strong> <span style={{color: '#3b82f6'}}>Sample Image</span></p>
                  )}
                  {selectedImage.camera_location && (
                    <p><strong>Location:</strong> {selectedImage.camera_location}</p>
                  )}
                  {selectedImage.camera_id && (
                    <p><strong>Camera:</strong> {selectedImage.camera_id}</p>
                  )}
                  {selectedImage.width && selectedImage.height && (
                    <p><strong>Dimensions:</strong> {selectedImage.width} × {selectedImage.height}</p>
                  )}
                  {selectedImage.file_size && (
                    <p><strong>File Size:</strong> {Math.round(selectedImage.file_size / 1024)} KB</p>
                  )}
                  {selectedImage.vehicle_detection_id && (
                    <p><strong>Detection ID:</strong> {selectedImage.vehicle_detection_id}</p>
                  )}
                  {selectedImage.violation_id && (
                    <p><strong>Violation ID:</strong> {selectedImage.violation_id}</p>
                  )}
                  {selectedImage.is_sample && (
                    <div style={{
                      marginTop: '16px',
                      padding: '12px',
                      background: '#eff6ff',
                      border: '1px solid #bfdbfe',
                      borderRadius: '6px',
                      fontSize: '12px',
                      color: '#1e40af'
                    }}>
                      This is a sample image for demonstration. Real detection images will be captured and stored when the RPi camera system is active.
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ImageGallery;