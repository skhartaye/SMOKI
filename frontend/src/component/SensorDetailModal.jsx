import { X, Thermometer, Droplet, Activity, Wind, Flame, Circle } from 'lucide-react';
import '../styles/SensorDetailModal.css';

const SENSOR_INFO = {
  temperature: {
    title: 'Temperature',
    unit: '°C',
    description: 'Measures ambient temperature to monitor environmental conditions and detect thermal anomalies in emission sources.',
    importance: 'Temperature is crucial for our smoke emission monitoring system as it helps identify hot spots and correlate with emission intensity. Higher temperatures often indicate active combustion processes.',
    range: '-10°C to 60°C',
    icon: Thermometer
  },
  humidity: {
    title: 'Humidity',
    unit: '%',
    description: 'Measures relative humidity levels in the air to assess moisture content and atmospheric conditions.',
    importance: 'Humidity affects particle behavior and pollutant dispersion. It helps us understand how environmental conditions influence smoke propagation and detection accuracy.',
    range: '0% to 100%',
    icon: Droplet
  },
  vocs: {
    title: 'Volatile Organic Compounds (VOCs)',
    unit: 'kΩ',
    description: 'Detects volatile organic compounds that are released during combustion and industrial processes.',
    importance: 'VOCs are key indicators of emission quality and combustion efficiency. They help identify the type and severity of emissions from vehicles and industrial sources.',
    range: '0 - 1000 kΩ',
    icon: Activity
  },
  nitrogen_dioxide: {
    title: 'Nitrogen Dioxide (NO₂)',
    unit: 'PPM',
    description: 'Measures nitrogen dioxide concentration, a major air pollutant produced by vehicle engines and industrial combustion.',
    importance: 'NO₂ is a critical pollutant for air quality assessment. It directly indicates emission severity and helps enforce environmental regulations for vehicle emissions.',
    range: '0 - 10 PPM',
    icon: Wind
  },
  carbon_monoxide: {
    title: 'Carbon Monoxide (CO)',
    unit: 'PPM',
    description: 'Detects carbon monoxide levels, a toxic gas produced by incomplete combustion in engines.',
    importance: 'CO is a primary indicator of combustion efficiency and emission quality. High CO levels indicate poor engine performance and excessive emissions.',
    range: '0 - 50 PPM',
    icon: Flame
  },
  pm25: {
    title: 'Particulate Matter 2.5 (PM2.5)',
    unit: 'µg/m³',
    description: 'Measures fine particulate matter with diameter less than 2.5 micrometers that can penetrate deep into lungs.',
    importance: 'PM2.5 is the most harmful particulate pollutant for human health. It\'s essential for monitoring smoke emissions and assessing air quality impact.',
    range: '0 - 500 µg/m³',
    icon: Circle
  },
  pm10: {
    title: 'Particulate Matter 10 (PM10)',
    unit: 'µg/m³',
    description: 'Measures coarser particulate matter with diameter less than 10 micrometers.',
    importance: 'PM10 represents larger particles that contribute to visible smoke and air quality degradation. It helps assess overall emission severity.',
    range: '0 - 500 µg/m³',
    icon: Circle
  }
};

export default function SensorDetailModal({ 
  isOpen, 
  sensorType, 
  sensorValue, 
  timestamp,
  onClose 
}) {
  if (!isOpen || !sensorType) return null;

  const info = SENSOR_INFO[sensorType];
  if (!info) return null;

  const IconComponent = info.icon;

  const formatValue = (value) => {
    if (value === null || value === undefined) return '--';
    if (typeof value === 'number') {
      return Math.round(value * 10) / 10;
    }
    return value;
  };

  const formatTimestamp = (ts) => {
    if (!ts) return 'No data';
    const date = new Date(ts);
    return date.toLocaleTimeString('en-US', { 
      hour: '2-digit', 
      minute: '2-digit', 
      second: '2-digit',
      hour12: true 
    });
  };

  return (
    <div className="sensor-detail-modal-overlay" onClick={onClose}>
      <div className="sensor-detail-modal-content" onClick={(e) => e.stopPropagation()}>
        <button className="sensor-detail-modal-close" onClick={onClose}>
          <X size={24} />
        </button>

        <div className="sensor-detail-modal-header">
          <div className="sensor-detail-modal-icon">
            <IconComponent size={48} />
          </div>
          <h2 className="sensor-detail-modal-title">{info.title}</h2>
        </div>

        <div className="sensor-detail-modal-value-section">
          <div className="sensor-detail-modal-value">
            {formatValue(sensorValue)}
            <span className="sensor-detail-modal-unit">{info.unit}</span>
          </div>
          <div className="sensor-detail-modal-timestamp">
            Last updated: {formatTimestamp(timestamp)}
          </div>
        </div>

        <div className="sensor-detail-modal-info-section">
          <div className="sensor-detail-modal-info-block">
            <h3 className="sensor-detail-modal-info-title">What is it?</h3>
            <p className="sensor-detail-modal-info-text">{info.description}</p>
          </div>

          <div className="sensor-detail-modal-info-block">
            <h3 className="sensor-detail-modal-info-title">Why it matters?</h3>
            <p className="sensor-detail-modal-info-text">{info.importance}</p>
          </div>

          <div className="sensor-detail-modal-info-block">
            <h3 className="sensor-detail-modal-info-title">Measurement Range</h3>
            <p className="sensor-detail-modal-range">{info.range}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
