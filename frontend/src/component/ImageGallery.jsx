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

      const response = await fetchWithFallback(`/api/images/recent?limit=50&hours=${timeFilter}`, {
        headers
      });

      if (response.ok) {
        const result = await response.json();
        if (result.success) {
          setImages(result.data);
        }
      }
    } catch (error) {
      console.error('Error fetching images:', error);
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

  const getImageUrl = (imageId) => {
    const token = localStorage.getItem('token');
    const baseUrl = process.env.REACT_APP_API_URL || '';
    return `${baseUrl}/api/images/${imageId}/raw?token=${token}`;
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
                      src={getImageUrl(image.id)}
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
                    </div>
                    {image.file_size && (
                      <div className="image-size">
                        {Math.round(image.file_size / 1024)} KB
                      </div>
                    )}
                  </div>
                </div>
              ))}
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
                  src={getImageUrl(selectedImage.id)}
                  alt={`Detection ${selectedImage.id}`}
                  className="full-size-image"
                />
                <div className="image-metadata">
                  <p><strong>Timestamp:</strong> {formatTimestamp(selectedImage.timestamp)}</p>
                  <p><strong>Image ID:</strong> {selectedImage.id}</p>
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