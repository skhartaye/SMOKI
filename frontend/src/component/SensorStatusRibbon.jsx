import { useState, useEffect } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import '../styles/SensorStatusRibbon.css';

export default function SensorStatusRibbon({ sensorConnected, lastSensorUpdate }) {
  const [showWarning, setShowWarning] = useState(false);
  const [secondsSinceUpdate, setSecondsSinceUpdate] = useState(0);

  useEffect(() => {
    console.log('SensorStatusRibbon - sensorConnected:', sensorConnected, 'lastSensorUpdate:', lastSensorUpdate);
    
    // Show warning if sensor is disconnected
    if (!sensorConnected) {
      setShowWarning(true);
    } else {
      // Hide warning when sensor reconnects
      setShowWarning(false);
    }
  }, [sensorConnected]);

  // Update seconds counter every second
  useEffect(() => {
    if (!showWarning) return;

    const updateSeconds = () => {
      if (!lastSensorUpdate) {
        setSecondsSinceUpdate(0);
        return;
      }
      const lastUpdate = new Date(lastSensorUpdate);
      const now = new Date();
      const seconds = Math.round((now - lastUpdate) / 1000);
      setSecondsSinceUpdate(Math.max(0, seconds)); // Ensure it doesn't go negative
    };

    updateSeconds();
    const interval = setInterval(updateSeconds, 1000);
    return () => clearInterval(interval);
  }, [showWarning]);

  const formatTimeDisplay = (seconds) => {
    if (seconds < 60) {
      return `${seconds}s`;
    } else if (seconds < 3600) {
      const minutes = Math.floor(seconds / 60);
      const remainingSeconds = seconds % 60;
      return remainingSeconds > 0 ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`;
    } else if (seconds < 86400) {
      const hours = Math.floor(seconds / 3600);
      const remainingMinutes = Math.floor((seconds % 3600) / 60);
      return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
    } else {
      const days = Math.floor(seconds / 86400);
      const remainingHours = Math.floor((seconds % 86400) / 3600);
      return remainingHours > 0 ? `${days}d ${remainingHours}h` : `${days}d`;
    }
  };

  if (!showWarning) {
    return null;
  }

  return (
    <div className="sensor-status-ribbon warning">
      <div className="sensor-status-icon">
        <AlertTriangle size={20} />
      </div>
      
      <div className="sensor-status-content">
        <div className="sensor-status-title">
          ⚠️ ESP32 Sensor Offline
        </div>
        <div className="sensor-status-message">
          No data received for {formatTimeDisplay(secondsSinceUpdate)}
        </div>
      </div>

      <button
        className="sensor-status-close"
        onClick={() => setShowWarning(false)}
      >
        <X size={18} />
      </button>
    </div>
  );
}
