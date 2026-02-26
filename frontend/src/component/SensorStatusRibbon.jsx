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
    if (!showWarning || !lastSensorUpdate) return;

    const updateSeconds = () => {
      const lastUpdate = new Date(lastSensorUpdate);
      const now = new Date();
      const seconds = Math.round((now - lastUpdate) / 1000);
      setSecondsSinceUpdate(seconds);
    };

    updateSeconds();
    const interval = setInterval(updateSeconds, 1000);
    return () => clearInterval(interval);
  }, [showWarning, lastSensorUpdate]);

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
          No data received for {secondsSinceUpdate} seconds
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
