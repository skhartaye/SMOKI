import { useState, useEffect } from 'react';
import { AlertTriangle } from 'lucide-react';
import '../styles/DataTimeoutModal.css';

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
          <AlertTriangle size={40} />
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
