import { useState, useEffect } from 'react';
import { AlertTriangle } from 'lucide-react';
import '../styles/DataTimeoutModal.css';

export default function DataTimeoutModal({ lastSensorUpdate }) {
  const [showModal, setShowModal] = useState(false);
  const [secondsSinceUpdate, setSecondsSinceUpdate] = useState(0);

  // Check if no data is being received (5 seconds)
  useEffect(() => {
    if (!lastSensorUpdate) {
      setShowModal(true);
      return;
    }

    const checkDataReceived = () => {
      const lastUpdate = new Date(lastSensorUpdate);
      const now = new Date();
      const seconds = Math.round((now - lastUpdate) / 1000);
      
      setSecondsSinceUpdate(seconds);

      // Show modal if no data for 30+ seconds
      if (seconds >= 30) {
        setShowModal(true);
      } else {
        setShowModal(false);
      }
    };

    checkDataReceived();
    const interval = setInterval(checkDataReceived, 1000);
    return () => clearInterval(interval);
  }, [lastSensorUpdate]);

  if (!showModal) {
    return null;
  }

  return (
    <div className="data-timeout-overlay" onClick={() => setShowModal(false)}>
      <div className="data-timeout-modal" onClick={(e) => e.stopPropagation()}>
        <div className="data-timeout-icon">
          <AlertTriangle size={40} />
        </div>
        
        <h2 className="data-timeout-title">No Data Being Received</h2>
        <p className="data-timeout-message">
          The system is not receiving any sensor data {secondsSinceUpdate > 0 ? `(${secondsSinceUpdate}s)` : ''}.
        </p>
        <p className="data-timeout-subtitle">
          Please verify your sensor is connected and transmitting data.
        </p>
        
        <button 
          className="data-timeout-close"
          onClick={() => setShowModal(false)}
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}
