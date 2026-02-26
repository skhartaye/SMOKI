import { useState, useEffect } from 'react';
import '../styles/DataTimeoutModal.css';

const InfoIcon = () => (
  <svg height="40" stroke-linejoin="round" viewBox="0 0 16 16" width="40" style={{color: 'currentcolor'}}><path d="M14 8C14 11.3137 11.3137 14 8 14C4.68629 14 2 11.3137 2 8C2 4.68629 4.68629 2 8 2C11.3137 2 14 4.68629 14 8Z" fill="currentColor" fillOpacity="0.08"></path><path fillRule="evenodd" clipRule="evenodd" d="M8 6C8.55228 6 9 5.55228 9 5C9 4.44772 8.55228 4 8 4C7.44771 4 7 4.44772 7 5C7 5.55228 7.44771 6 8 6ZM7 7H6.25V8.5H7H7.24999V10.5V11.25H8.74999V10.5V8C8.74999 7.44772 8.30227 7 7.74999 7H7Z" fill="currentColor"></path></svg>
);

export default function DataTimeoutModal({ lastSensorUpdate }) {
  const [showModal, setShowModal] = useState(false);
  const [secondsSinceUpdate, setSecondsSinceUpdate] = useState(0);
  const [isDismissed, setIsDismissed] = useState(false);

  // Check if no data is being received (5 seconds)
  useEffect(() => {
    if (!lastSensorUpdate) {
      if (!isDismissed) {
        setShowModal(true);
      }
      return;
    }

    const checkDataReceived = () => {
      const lastUpdate = new Date(lastSensorUpdate);
      const now = new Date();
      const seconds = Math.round((now - lastUpdate) / 1000);
      
      setSecondsSinceUpdate(seconds);

      // Show modal if no data for 30+ seconds and not dismissed
      if (seconds >= 30 && !isDismissed) {
        setShowModal(true);
      } else if (seconds < 30) {
        // Reset dismissed state when data comes back
        setShowModal(false);
        setIsDismissed(false);
      }
    };

    checkDataReceived();
    const interval = setInterval(checkDataReceived, 1000);
    return () => clearInterval(interval);
  }, [lastSensorUpdate, isDismissed]);

  const handleDismiss = () => {
    setShowModal(false);
    setIsDismissed(true);
  };

  if (!showModal) {
    return null;
  }

  // Format time display: convert to minutes if >= 60 seconds
  const formatTimeDisplay = (seconds) => {
    if (seconds >= 60) {
      const minutes = Math.floor(seconds / 60);
      const remainingSeconds = seconds % 60;
      return remainingSeconds > 0 ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`;
    }
    return `${seconds}s`;
  };

  return (
    <div className="data-timeout-overlay" onClick={handleDismiss}>
      <div className="data-timeout-modal" onClick={(e) => e.stopPropagation()}>
        <div className="data-timeout-icon">
          <InfoIcon />
        </div>
        
        <h2 className="data-timeout-title">No Data Being Received</h2>
        <p className="data-timeout-message">
          The system is not receiving any sensor data {secondsSinceUpdate > 0 ? `(${formatTimeDisplay(secondsSinceUpdate)})` : ''}.
        </p>
        <p className="data-timeout-subtitle">
          Please verify your sensor is connected and transmitting data.
        </p>
        
        <button 
          className="data-timeout-close"
          onClick={handleDismiss}
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}
