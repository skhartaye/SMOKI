import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { fetchWithFallback } from '../utils/apiClient';

const SensorStatusContext = createContext();

export const SensorStatusProvider = ({ children }) => {
  const [sensorConnected, setSensorConnected] = useState(true);
  const [lastSensorUpdate, setLastSensorUpdate] = useState(null);

  // Check sensor connection status
  const checkSensorStatus = useCallback(async () => {
    try {
      const response = await fetchWithFallback('/api/sensors/status');
      
      const result = await response.json();
      if (result.success) {
        console.log('Sensor status check:', result);
        setSensorConnected(result.connected);
        setLastSensorUpdate(result.last_update);
      }
    } catch (error) {
      console.error('Error checking sensor status:', error);
    }
  }, []);

  // Update last sensor update timestamp
  const updateLastSensorTime = useCallback(() => {
    setLastSensorUpdate(new Date().toISOString());
  }, []);

  // Check sensor status on mount and periodically
  useEffect(() => {
    console.log('SensorStatusProvider mounted - checking sensor status');
    checkSensorStatus();
    const statusInterval = setInterval(checkSensorStatus, 10000); // Check every 10 seconds
    return () => clearInterval(statusInterval);
  }, [checkSensorStatus]);

  return (
    <SensorStatusContext.Provider value={{
      sensorConnected,
      lastSensorUpdate,
      updateLastSensorTime
    }}>
      {children}
    </SensorStatusContext.Provider>
  );
};

export const useSensorStatus = () => {
  const context = useContext(SensorStatusContext);
  if (!context) {
    throw new Error('useSensorStatus must be used within SensorStatusProvider');
  }
  return context;
};
