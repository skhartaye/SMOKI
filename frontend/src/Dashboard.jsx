import './styles/Dashboard.css';
import { useNavigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Brush, ReferenceLine } from 'recharts';
import { Thermometer, Droplet, Wind, Flame, Circle, Home, FileText, TrendingUp, Zap, Moon, Sun, LogOut, Menu, Activity } from 'lucide-react';

function Dashboard() {
  const [activePage, setActivePage] = useState("dashboard");
  const [sensorData, setSensorData] = useState(null);
  const [previousSensorData, setPreviousSensorData] = useState(null);
  const [records, setRecords] = useState([]);
  const [graphData, setGraphData] = useState([]);
  const [filterSensorTypes, setFilterSensorTypes] = useState({
    temperature: true,
    humidity: true,
    vocs: true,
    no2: true,
    co: true,
    pm25: true,
    pm10: true
  });
  const [appliedSensorTypes, setAppliedSensorTypes] = useState({
    temperature: true,
    humidity: true,
    vocs: true,
    no2: true,
    co: true,
    pm25: true,
    pm10: true
  });
  const [filterDate, setFilterDate] = useState("all");
  const [appliedDate, setAppliedDate] = useState("all");
  const [clearFilters, setClearFilters] = useState(false);
  const [sensorDropdownOpen, setSensorDropdownOpen] = useState(false);
  
  // Graph filters
  const [graphFilterSensorTypes, setGraphFilterSensorTypes] = useState({
    temperature: true,
    humidity: true,
    vocs: true,
    no2: true,
    co: true,
    pm25: true,
    pm10: true
  });
  const [appliedGraphSensorTypes, setAppliedGraphSensorTypes] = useState({
    temperature: true,
    humidity: true,
    vocs: true,
    no2: true,
    co: true,
    pm25: true,
    pm10: true
  });
  const [graphFilterDate, setGraphFilterDate] = useState("all");
  const [appliedGraphDate, setAppliedGraphDate] = useState("all");
  const [clearGraphFilters, setClearGraphFilters] = useState(false);
  const [graphSensorDropdownOpen, setGraphSensorDropdownOpen] = useState(false);
  const [darkMode, setDarkMode] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [selectedSensor, setSelectedSensor] = useState(null); // For sensor detail view
  const [sidebarHovered, setSidebarHovered] = useState(false);
  const [showGraphLoading, setShowGraphLoading] = useState(false);
  
  const navigate = useNavigate();

  // Close dropdowns when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (!event.target.closest('.custom-dropdown')) {
        setSensorDropdownOpen(false);
        setGraphSensorDropdownOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Handle sidebar hover to show loading animation on graphs page
  useEffect(() => {
    let timeoutId;
    if (activePage === "graphs") {
      setShowGraphLoading(true);
      // Hide loading after sidebar animation completes
      timeoutId = setTimeout(() => {
        setShowGraphLoading(false);
      }, 1000);
    }
    return () => {
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [sidebarHovered, activePage]);

  // Fetch latest sensor data for sensors page
  useEffect(() => {
    if (activePage === "sensors") {
      fetchLatestSensorData();
      const interval = setInterval(fetchLatestSensorData, 5000); // Update every 5 seconds
      return () => clearInterval(interval);
    }
  }, [activePage]);

  // Fetch records for records page
  useEffect(() => {
    if (activePage === "records") {
      fetchRecords();
      const interval = setInterval(fetchRecords, 10000); // Update every 10 seconds
      return () => clearInterval(interval);
    }
  }, [activePage]);

  // Fetch graph data for graphs page
  useEffect(() => {
    if (activePage === "graphs") {
      fetchGraphData();
      const interval = setInterval(fetchGraphData, 30000); // Update every 30 seconds
      return () => clearInterval(interval);
    }
  }, [activePage]);

  const fetchLatestSensorData = async () => {
    try {
      const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
      const response = await fetch(`${API_URL}/api/sensors/latest`);
      const result = await response.json();
      if (result.success && result.data) {
        setPreviousSensorData(sensorData);
        setSensorData(result.data);
      }
    } catch (error) {
      console.error('Error fetching sensor data:', error);
    }
  };

  const calculateChange = (current, previous) => {
    // Always return a number - return 0 if no valid data
    if (typeof current !== 'number' || typeof previous !== 'number') return 0;
    if (previous === 0) return 0;
    const change = ((current - previous) / previous) * 100;
    return change;
  };

  const fetchRecords = async () => {
    try {
      const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
      const response = await fetch(`${API_URL}/api/sensors/data?limit=50`);
      const result = await response.json();
      if (result.success) {
        setRecords(result.data);
      }
    } catch (error) {
      console.error('Error fetching records:', error);
    }
  };

  const fetchGraphData = async () => {
    try {
      const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
      const response = await fetch(`${API_URL}/api/sensors/data?limit=500`);
      const result = await response.json();
      if (result.success) {
        // Format data for graphs (reverse to show oldest first)
        const formatted = result.data.reverse().map(item => ({
          time: new Date(item.timestamp).toLocaleTimeString(),
          fullTimestamp: new Date(item.timestamp).toLocaleString(),
          temperature: item.temperature || 0,
          humidity: item.humidity || 0,
          vocs: item.vocs || 0,
          no2: item.nitrogen_dioxide || 0,
          co: item.carbon_monoxide || 0,
          pm25: item.pm25 || 0,
          pm10: item.pm10 || 0
        }));
        setGraphData(formatted);
      }
    } catch (error) {
      console.error('Error fetching graph data:', error);
    }
  };

  function handleLogout() {
    localStorage.removeItem('isLoggedIn');
    navigate('/');
  }

  const formatTimestamp = (timestamp) => {
    const date = new Date(timestamp);
    // Format as: YYYY-MM-DD HH:MM:SS AM/PM
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    
    let hours = date.getHours();
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const seconds = String(date.getSeconds()).padStart(2, '0');
    const ampm = hours >= 12 ? 'PM' : 'AM';
    
    hours = hours % 12;
    hours = hours ? hours : 12; // 0 should be 12
    const hoursStr = String(hours).padStart(2, '0');
    
    return `${year}-${month}-${day} ${hoursStr}:${minutes}:${seconds} ${ampm}`;
  };

  const calculateAQI = (record) => {
    // AQI calculation based on US EPA standard
    // Using the formula: Ip = [(IHI - ILO) / (BPHI - BPLO)] * (Cp - BPLO) + ILO
    
    const pollutants = [];
    
    // PM2.5 breakpoints (µg/m³)
    const pm25Breakpoints = [
      { cLow: 0, cHigh: 12.0, iLow: 0, iHigh: 50 },
      { cLow: 12.1, cHigh: 35.4, iLow: 51, iHigh: 100 },
      { cLow: 35.5, cHigh: 55.4, iLow: 101, iHigh: 150 },
      { cLow: 55.5, cHigh: 150.4, iLow: 151, iHigh: 200 },
      { cLow: 150.5, cHigh: 250.4, iLow: 201, iHigh: 300 },
      { cLow: 250.5, cHigh: 500.4, iLow: 301, iHigh: 500 }
    ];
    
    // PM10 breakpoints (µg/m³)
    const pm10Breakpoints = [
      { cLow: 0, cHigh: 54, iLow: 0, iHigh: 50 },
      { cLow: 55, cHigh: 154, iLow: 51, iHigh: 100 },
      { cLow: 155, cHigh: 254, iLow: 101, iHigh: 150 },
      { cLow: 255, cHigh: 354, iLow: 151, iHigh: 200 },
      { cLow: 355, cHigh: 424, iLow: 201, iHigh: 300 },
      { cLow: 425, cHigh: 604, iLow: 301, iHigh: 500 }
    ];
    
    // CO breakpoints (ppm)
    const coBreakpoints = [
      { cLow: 0, cHigh: 4.4, iLow: 0, iHigh: 50 },
      { cLow: 4.5, cHigh: 9.4, iLow: 51, iHigh: 100 },
      { cLow: 9.5, cHigh: 12.4, iLow: 101, iHigh: 150 },
      { cLow: 12.5, cHigh: 15.4, iLow: 151, iHigh: 200 },
      { cLow: 15.5, cHigh: 30.4, iLow: 201, iHigh: 300 },
      { cLow: 30.5, cHigh: 50.4, iLow: 301, iHigh: 500 }
    ];
    
    // NO2 breakpoints (ppb, convert from ppm)
    const no2Breakpoints = [
      { cLow: 0, cHigh: 53, iLow: 0, iHigh: 50 },
      { cLow: 54, cHigh: 100, iLow: 51, iHigh: 100 },
      { cLow: 101, cHigh: 360, iLow: 101, iHigh: 150 },
      { cLow: 361, cHigh: 649, iLow: 151, iHigh: 200 },
      { cLow: 650, cHigh: 1249, iLow: 201, iHigh: 300 },
      { cLow: 1250, cHigh: 2049, iLow: 301, iHigh: 500 }
    ];
    
    const calculatePollutantAQI = (concentration, breakpoints) => {
      if (!concentration || concentration < 0) return null;
      
      for (let bp of breakpoints) {
        if (concentration >= bp.cLow && concentration <= bp.cHigh) {
          const aqi = ((bp.iHigh - bp.iLow) / (bp.cHigh - bp.cLow)) * (concentration - bp.cLow) + bp.iLow;
          return Math.round(aqi);
        }
      }
      
      // If concentration exceeds all breakpoints, return hazardous
      return 500;
    };
    
    // Calculate AQI for each pollutant
    if (record.pm25) {
      const aqi = calculatePollutantAQI(record.pm25, pm25Breakpoints);
      if (aqi !== null) pollutants.push({ name: 'PM2.5', aqi });
    }
    
    if (record.pm10) {
      const aqi = calculatePollutantAQI(record.pm10, pm10Breakpoints);
      if (aqi !== null) pollutants.push({ name: 'PM10', aqi });
    }
    
    if (record.carbon_monoxide) {
      const aqi = calculatePollutantAQI(record.carbon_monoxide, coBreakpoints);
      if (aqi !== null) pollutants.push({ name: 'CO', aqi });
    }
    
    if (record.nitrogen_dioxide) {
      // Convert ppm to ppb (multiply by 1000)
      const no2Ppb = record.nitrogen_dioxide * 1000;
      const aqi = calculatePollutantAQI(no2Ppb, no2Breakpoints);
      if (aqi !== null) pollutants.push({ name: 'NO2', aqi });
    }
    
    // Return the highest AQI (worst pollutant)
    if (pollutants.length === 0) {
      return { value: 0, category: 'Good', color: '#4caf50', pollutant: 'N/A' };
    }
    
    const maxPollutant = pollutants.reduce((max, p) => p.aqi > max.aqi ? p : max);
    const aqiValue = maxPollutant.aqi;
    
    // Determine category and color based on AQI value
    let category, color;
    if (aqiValue <= 50) {
      category = 'Good';
      color = '#4caf50'; // Green
    } else if (aqiValue <= 100) {
      category = 'Moderate';
      color = '#ffc107'; // Yellow
    } else if (aqiValue <= 150) {
      category = 'Unhealthy for Sensitive';
      color = '#ff9800'; // Orange
    } else if (aqiValue <= 200) {
      category = 'Unhealthy';
      color = '#f44336'; // Red
    } else if (aqiValue <= 300) {
      category = 'Very Unhealthy';
      color = '#9c27b0'; // Purple
    } else {
      category = 'Hazardous';
      color = '#7b1fa2'; // Maroon
    }
    
    return { 
      value: aqiValue, 
      category, 
      color,
      pollutant: maxPollutant.name
    };
  };

  // Tooltip config for graphs
  const tooltipStyle = {
    backgroundColor: darkMode ? 'rgba(45,45,45,0.95)' : 'rgba(255,255,255,0.95)',
    border: darkMode ? '1px solid #555' : '1px solid #ddd',
    borderRadius: '8px',
    padding: '10px',
    color: darkMode ? '#e0e0e0' : '#333'
  };

  const tooltipLabelStyle = {
    fontWeight: 'bold',
    marginBottom: '5px',
    color: darkMode ? '#e0e0e0' : '#333'
  };

  const handleClearFilters = () => {
    const defaultSensors = {
      temperature: true,
      humidity: true,
      vocs: true,
      no2: true,
      co: true,
      pm25: true,
      pm10: true
    };
    setFilterSensorTypes(defaultSensors);
    setAppliedSensorTypes(defaultSensors);
    setFilterDate("all");
    setAppliedDate("all");
  };

  const handleSubmit = () => {
    if (clearFilters) {
      handleClearFilters();
      setClearFilters(false);
    } else {
      setAppliedSensorTypes(filterSensorTypes);
      setAppliedDate(filterDate);
    }
    fetchRecords();
  };

  const toggleSensorType = (sensor) => {
    setFilterSensorTypes(prev => ({
      ...prev,
      [sensor]: !prev[sensor]
    }));
  };

  const toggleGraphSensorType = (sensor) => {
    setGraphFilterSensorTypes(prev => ({
      ...prev,
      [sensor]: !prev[sensor]
    }));
  };

  const handleClearGraphFilters = () => {
    const defaultSensors = {
      temperature: true,
      humidity: true,
      vocs: true,
      no2: true,
      co: true,
      pm25: true,
      pm10: true
    };
    setGraphFilterSensorTypes(defaultSensors);
    setAppliedGraphSensorTypes(defaultSensors);
    setGraphFilterDate("all");
    setAppliedGraphDate("all");
  };

  const handleGraphSubmit = () => {
    if (clearGraphFilters) {
      handleClearGraphFilters();
      setClearGraphFilters(false);
    } else {
      setAppliedGraphSensorTypes(graphFilterSensorTypes);
      setAppliedGraphDate(graphFilterDate);
    }
    fetchGraphData();
  };

  const getFilteredGraphData = () => {
    let filtered = [...graphData];

    // Filter by date using applied date
    if (appliedGraphDate !== "all") {
      const now = new Date();
      filtered = filtered.filter(item => {
        // Parse the time string back to date
        const itemDate = new Date();
        const [time] = item.time.split(' ');
        const [hours, minutes, seconds] = time.split(':');
        itemDate.setHours(parseInt(hours), parseInt(minutes), parseInt(seconds));
        
        const diffTime = Math.abs(now - itemDate);
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
        
        if (appliedGraphDate === "today") {
          return itemDate.toDateString() === now.toDateString();
        } else if (appliedGraphDate === "7days") {
          return diffDays <= 7;
        } else if (appliedGraphDate === "30days") {
          return diffDays <= 30;
        }
        return true;
      });
    }

    // Limit to only 10 data points for better visibility
    const maxPoints = 10;
    if (filtered.length > maxPoints) {
      const step = Math.ceil(filtered.length / maxPoints);
      filtered = filtered.filter((_, index) => index % step === 0);
    }

    // Ensure we have exactly 10 points or less
    if (filtered.length > maxPoints) {
      filtered = filtered.slice(-maxPoints);
    }

    return filtered;
  };

  // Helper function to get peak value for a sensor type
  const getPeakValue = (sensorType) => {
    const filtered = getFilteredGraphData();
    if (filtered.length === 0) return null;
    
    const values = filtered.map(item => item[sensorType]).filter(val => val !== null && val !== undefined);
    if (values.length === 0) return null;
    
    return Math.max(...values);
  };

  const getFilteredRecords = () => {
    let filtered = [...records];

    // Filter by date using applied date
    if (appliedDate !== "all") {
      const now = new Date();
      filtered = filtered.filter(record => {
        const recordDate = new Date(record.timestamp);
        const diffTime = Math.abs(now - recordDate);
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
        
        if (appliedDate === "today") {
          return recordDate.toDateString() === now.toDateString();
        } else if (appliedDate === "7days") {
          return diffDays <= 7;
        } else if (appliedDate === "30days") {
          return diffDays <= 30;
        }
        return true;
      });
    }

    return filtered;
  };

  return (
    <div className={`dashboard ${darkMode ? 'dark-mode' : ''}`}>
      {/* Mobile Menu Button */}
      <button className="mobile-menu-btn" onClick={() => setMobileMenuOpen(!mobileMenuOpen)}>
        <Menu />
      </button>

      {/* Sidebar Overlay */}
      <div 
        className={`sidebar-overlay ${mobileMenuOpen ? 'active' : ''}`}
        onClick={() => setMobileMenuOpen(false)}
      ></div>

      {/* Sidebar */}
      <aside 
        className={`sidebar ${mobileMenuOpen ? 'mobile-open' : ''}`}
        onMouseEnter={() => setSidebarHovered(true)}
        onMouseLeave={() => setSidebarHovered(false)}
      >
        <div className="sidebar-header">
          <h1>
            <span className="menu-icon"><Menu /></span>
            <span className="menu-text">SMOKi</span>
          </h1>
        </div>

        <nav className="sidebar-nav">
          <button 
            onClick={() => {
              setActivePage("dashboard");
              setMobileMenuOpen(false);
            }}
            className={`nav-item ${activePage === "dashboard" ? "active" : ""}`}
          >
            <span className="nav-icon"><Home /></span>
            <span className="nav-text">Dashboard</span>
          </button>

          <button 
            onClick={() => {
              setActivePage("records");
              setMobileMenuOpen(false);
            }}
            className={`nav-item ${activePage === "records" ? "active" : ""}`}
          >
            <span className="nav-icon"><FileText /></span>
            <span className="nav-text">Records</span>
          </button>

          <button 
            onClick={() => {
              setActivePage("graphs");
              setMobileMenuOpen(false);
            }}
            className={`nav-item ${activePage === "graphs" ? "active" : ""}`}
          >
            <span className="nav-icon"><TrendingUp /></span>
            <span className="nav-text">Graphs</span>
          </button>

          <button 
            onClick={() => {
              setActivePage("sensors");
              setMobileMenuOpen(false);
            }}
            className={`nav-item ${activePage === "sensors" ? "active" : ""}`}
          >
            <span className="nav-icon"><Zap /></span>
            <span className="nav-text">Sensors</span>
          </button>

          <button 
            onClick={() => setDarkMode(!darkMode)}
            className="nav-item"
          >
            <span className="nav-icon">{darkMode ? <Sun /> : <Moon />}</span>
            <span className="nav-text">{darkMode ? 'Light Mode' : 'Dark Mode'}</span>
          </button>
        </nav>

        <div className="sidebar-footer">
          <div className="user-info">
            <span className="user-icon">👤</span>
            <div className="user-details">
              <div className="user-name">Admin User</div>
              <div className="user-email">admin@smoki.local</div>
            </div>
          </div>
          <button className="sign-out-btn" onClick={handleLogout}>
            <span><LogOut /></span>
            <span>Sign out</span>
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="main-content">
          {activePage === "dashboard" && (
            <div className="dashboard-page-container">
              <div className="records-header">
                <h1>Dashboard</h1>
                <p className="records-subtitle">Smoke Emission monitoring overview</p>
              </div>
              
              <div className="camera-feed-container">
                <div className="camera-feed-header">
                  <h2>Live Camera Feed</h2>
                  <p>Real-time video monitoring</p>
                </div>
                <div className="camera-feed">
                  <div className="camera-placeholder">
                    CAMERA FEED
                  </div>
                </div>
              </div>
            </div>
          )}

          {activePage === "sensors" && (
            <section className="sensors-page-container-new">
              {!selectedSensor ? (
                // Camera + Sensor Cards View
                <div className="sensors-layout">
                  <div className="sensors-camera-section">
                    <div className="records-header">
                      <h1>Sensors</h1>
                      <p className="records-subtitle">Monitor emissions data and air quality in real-time</p>
                    </div>
                    <div className="camera-feed-box">
                      <div className="camera-placeholder">
                        CAMERA FEED
                      </div>
                    </div>
                  </div>
                  
                  <div className="sensors-cards-column">
                    <div className="sensor-card-compact" onClick={() => setSelectedSensor(true)}>
                      <div className="sensor-card-compact-header">
                        <div className="sensor-icon-small"><Thermometer size={24} /></div>
                        <h3>Temperature</h3>
                      </div>
                      <div className="sensor-value-compact">
                        {sensorData?.temperature ? `${sensorData.temperature.toFixed(1)}°C` : '--°C'}
                      </div>
                      <div className="sensor-status-compact">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div className="sensor-card-compact" onClick={() => setSelectedSensor(true)}>
                      <div className="sensor-card-compact-header">
                        <div className="sensor-icon-small"><Droplet size={24} /></div>
                        <h3>Humidity</h3>
                      </div>
                      <div className="sensor-value-compact">
                        {sensorData?.humidity ? `${sensorData.humidity.toFixed(1)}%` : '--%'}
                      </div>
                      <div className="sensor-status-compact">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div className="sensor-card-compact" onClick={() => setSelectedSensor(true)}>
                      <div className="sensor-card-compact-header">
                        <div className="sensor-icon-small"><Activity size={24} /></div>
                        <h3>VOCs</h3>
                      </div>
                      <div className="sensor-value-compact">
                        {sensorData?.vocs ? `${sensorData.vocs.toFixed(1)} kΩ` : '-- kΩ'}
                      </div>
                      <div className="sensor-status-compact">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div className="sensor-card-compact" onClick={() => setSelectedSensor(true)}>
                      <div className="sensor-card-compact-header">
                        <div className="sensor-icon-small"><Wind size={24} /></div>
                        <h3>Nitrogen Dioxide</h3>
                      </div>
                      <div className="sensor-value-compact">
                        {sensorData?.nitrogen_dioxide ? `${sensorData.nitrogen_dioxide.toFixed(2)} PPM` : '-- PPM'}
                      </div>
                      <div className="sensor-status-compact">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div className="sensor-card-compact" onClick={() => setSelectedSensor(true)}>
                      <div className="sensor-card-compact-header">
                        <div className="sensor-icon-small"><Flame size={24} /></div>
                        <h3>Carbon Monoxide</h3>
                      </div>
                      <div className="sensor-value-compact">
                        {sensorData?.carbon_monoxide ? `${sensorData.carbon_monoxide.toFixed(2)} PPM` : '-- PPM'}
                      </div>
                      <div className="sensor-status-compact">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div className="sensor-card-compact" onClick={() => setSelectedSensor(true)}>
                      <div className="sensor-card-compact-header">
                        <div className="sensor-icon-small"><Circle size={24} /></div>
                        <h3>PM 2.5</h3>
                      </div>
                      <div className="sensor-value-compact">
                        {sensorData?.pm25 ? `${sensorData.pm25.toFixed(1)} µg/m³` : '-- µg/m³'}
                      </div>
                      <div className="sensor-status-compact">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div className="sensor-card-compact" onClick={() => setSelectedSensor(true)}>
                      <div className="sensor-card-compact-header">
                        <div className="sensor-icon-small"><Circle size={24} /></div>
                        <h3>PM 10</h3>
                      </div>
                      <div className="sensor-value-compact">
                        {sensorData?.pm10 ? `${sensorData.pm10.toFixed(1)} µg/m³` : '-- µg/m³'}
                      </div>
                      <div className="sensor-status-compact">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                // Detailed Sensor View - Show All Sensors
                <div className="sensor-detail-view">
                  <button className="back-button" onClick={() => setSelectedSensor(null)}>
                    ← Back to Sensors
                  </button>
                  
                  <div className="sensors-grid">
                    <div className="sensor-card">
                      <div className="sensor-card-header">
                        <div className="sensor-icon"><Thermometer /></div>
                        <h3>Temperature</h3>
                      </div>
                      <div className={`sensor-change ${calculateChange(sensorData?.temperature, previousSensorData?.temperature) >= 0 ? 'positive' : 'negative'}`}>
                        {calculateChange(sensorData?.temperature, previousSensorData?.temperature) >= 0 ? '↑' : '↓'} {Math.abs(calculateChange(sensorData?.temperature, previousSensorData?.temperature)).toFixed(1)}%
                      </div>
                      <div className="sensor-value">
                        {sensorData?.temperature ? `${sensorData.temperature.toFixed(1)}°C` : '--°C'}
                      </div>
                      <div className="sensor-status">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>
                    
                    <div className="sensor-card">
                      <div className="sensor-card-header">
                        <div className="sensor-icon"><Droplet /></div>
                        <h3>Humidity</h3>
                      </div>
                      <div className={`sensor-change ${calculateChange(sensorData?.humidity, previousSensorData?.humidity) >= 0 ? 'positive' : 'negative'}`}>
                        {calculateChange(sensorData?.humidity, previousSensorData?.humidity) >= 0 ? '↑' : '↓'} {Math.abs(calculateChange(sensorData?.humidity, previousSensorData?.humidity)).toFixed(1)}%
                      </div>
                      <div className="sensor-value">
                        {sensorData?.humidity ? `${sensorData.humidity.toFixed(1)}%` : '--%'}
                      </div>
                      <div className="sensor-status">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>
                    
                    <div className="sensor-card">
                      <div className="sensor-card-header">
                        <div className="sensor-icon"><Activity /></div>
                        <h3>VOCs</h3>
                      </div>
                      <div className={`sensor-change ${calculateChange(sensorData?.vocs, previousSensorData?.vocs) >= 0 ? 'positive' : 'negative'}`}>
                        {calculateChange(sensorData?.vocs, previousSensorData?.vocs) >= 0 ? '↑' : '↓'} {Math.abs(calculateChange(sensorData?.vocs, previousSensorData?.vocs)).toFixed(1)}%
                      </div>
                      <div className="sensor-value">
                        {sensorData?.vocs ? `${sensorData.vocs.toFixed(1)} kΩ` : '-- kΩ'}
                      </div>
                      <div className="sensor-status">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div className="sensor-card">
                      <div className="sensor-card-header">
                        <div className="sensor-icon"><Wind /></div>
                        <h3>Nitrogen Dioxide</h3>
                      </div>
                      <div className={`sensor-change ${calculateChange(sensorData?.nitrogen_dioxide, previousSensorData?.nitrogen_dioxide) >= 0 ? 'positive' : 'negative'}`}>
                        {calculateChange(sensorData?.nitrogen_dioxide, previousSensorData?.nitrogen_dioxide) >= 0 ? '↑' : '↓'} {Math.abs(calculateChange(sensorData?.nitrogen_dioxide, previousSensorData?.nitrogen_dioxide)).toFixed(1)}%
                      </div>
                      <div className="sensor-value">
                        {sensorData?.nitrogen_dioxide ? `${sensorData.nitrogen_dioxide.toFixed(2)} PPM` : '-- PPM'}
                      </div>
                      <div className="sensor-status">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>
                    
                    <div className="sensor-card">
                      <div className="sensor-card-header">
                        <div className="sensor-icon"><Flame /></div>
                        <h3>Carbon Monoxide</h3>
                      </div>
                      <div className={`sensor-change ${calculateChange(sensorData?.carbon_monoxide, previousSensorData?.carbon_monoxide) >= 0 ? 'positive' : 'negative'}`}>
                        {calculateChange(sensorData?.carbon_monoxide, previousSensorData?.carbon_monoxide) >= 0 ? '↑' : '↓'} {Math.abs(calculateChange(sensorData?.carbon_monoxide, previousSensorData?.carbon_monoxide)).toFixed(1)}%
                      </div>
                      <div className="sensor-value">
                        {sensorData?.carbon_monoxide ? `${sensorData.carbon_monoxide.toFixed(2)} PPM` : '-- PPM'}
                      </div>
                      <div className="sensor-status">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div className="sensor-card">
                      <div className="sensor-card-header">
                        <div className="sensor-icon"><Circle /></div>
                        <h3>PM 2.5</h3>
                      </div>
                      <div className={`sensor-change ${calculateChange(sensorData?.pm25, previousSensorData?.pm25) >= 0 ? 'positive' : 'negative'}`}>
                        {calculateChange(sensorData?.pm25, previousSensorData?.pm25) >= 0 ? '↑' : '↓'} {Math.abs(calculateChange(sensorData?.pm25, previousSensorData?.pm25)).toFixed(1)}%
                      </div>
                      <div className="sensor-value">
                        {sensorData?.pm25 ? `${sensorData.pm25.toFixed(1)} µg/m³` : '-- µg/m³'}
                      </div>
                      <div className="sensor-status">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>
                    
                    <div className="sensor-card">
                      <div className="sensor-card-header">
                        <div className="sensor-icon"><Circle /></div>
                        <h3>PM 10</h3>
                      </div>
                      <div className={`sensor-change ${calculateChange(sensorData?.pm10, previousSensorData?.pm10) >= 0 ? 'positive' : 'negative'}`}>
                        {calculateChange(sensorData?.pm10, previousSensorData?.pm10) >= 0 ? '↑' : '↓'} {Math.abs(calculateChange(sensorData?.pm10, previousSensorData?.pm10)).toFixed(1)}%
                      </div>
                      <div className="sensor-value">
                        {sensorData?.pm10 ? `${sensorData.pm10.toFixed(1)} µg/m³` : '-- µg/m³'}
                      </div>
                      <div className="sensor-status">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </section>
          )}

          {activePage === "camera" && (
            <section className="camera-page-container">
              <div className='cp-visual-container'>
                CAMERA FEED
              </div>

              <div className='cp-readings-container'>
                <h2>Latest Readings</h2>
                <div className='cp-records-container'>
                  <div className='cp-time'>
                    <div>⏰</div>
                    <div>Time</div>
                  </div>
                  <div className='cp-vehicle-type'>
                    <div>🚗</div>
                    <div>Vehicle Type</div>
                  </div>
                  <div className='cp-plate'>
                    <div>🔢</div>
                    <div>License Plate</div>
                  </div>
                  <div className='cp-smoke-detected'>
                    <div>💨</div>
                    <div>Smoke Detected</div>
                  </div>
                  <div className='cp-density'>
                    <div>📊</div>
                    <div>Smoke Density</div>
                  </div>
                  <div className='cp-color'>
                    <div>🎨</div>
                    <div>Smoke Color</div>
                  </div>
                </div>
              </div>
            </section>
          )}

          {activePage === "records" && (
            <section className="records-page-container">
              <div className="records-header">
                <h1>Sensor Records</h1>
                <p className="records-subtitle">AeroBlend system data logs and monitoring</p>
              </div>

              {/* Filters Section */}
              <div className="filters-container">
                <div className="filters-header">
                  <span className="filter-icon">▼</span> Filters
                </div>
                <div className="filters-content">
                  <div className="filter-group">
                    <label>📊 Sensor Types</label>
                    <div className="custom-dropdown">
                      <div 
                        className="dropdown-header"
                        onClick={() => setSensorDropdownOpen(!sensorDropdownOpen)}
                      >
                        <span>Select Sensors</span>
                        <span className="dropdown-arrow">{sensorDropdownOpen ? '▲' : '▼'}</span>
                      </div>
                      {sensorDropdownOpen && (
                        <div className="dropdown-menu">
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={filterSensorTypes.temperature}
                              onChange={() => toggleSensorType('temperature')}
                            />
                            Temperature
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={filterSensorTypes.humidity}
                              onChange={() => toggleSensorType('humidity')}
                            />
                            Humidity
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={filterSensorTypes.vocs}
                              onChange={() => toggleSensorType('vocs')}
                            />
                            VOCs
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={filterSensorTypes.no2}
                              onChange={() => toggleSensorType('no2')}
                            />
                            NO₂
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={filterSensorTypes.co}
                              onChange={() => toggleSensorType('co')}
                            />
                            CO
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={filterSensorTypes.pm25}
                              onChange={() => toggleSensorType('pm25')}
                            />
                            PM2.5
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={filterSensorTypes.pm10}
                              onChange={() => toggleSensorType('pm10')}
                            />
                            PM10
                          </label>
                          <div className="dropdown-divider"></div>
                          <label className="dropdown-item clear-item">
                            <input 
                              type="checkbox" 
                              checked={clearFilters}
                              onChange={(e) => setClearFilters(e.target.checked)}
                            />
                            Clear all filters
                          </label>
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="filter-group">
                    <label>📅 Date</label>
                    <select 
                      className="filter-select"
                      value={filterDate}
                      onChange={(e) => setFilterDate(e.target.value)}
                    >
                      <option value="all">All Dates</option>
                      <option value="today">Today</option>
                      <option value="7days">Last 7 Days</option>
                      <option value="30days">Last 30 Days</option>
                    </select>
                  </div>
                  <button className="submit-filters-btn" onClick={handleSubmit}>Submit</button>
                </div>
              </div>

              {/* Data Logs Section */}
              <div className="data-logs-container">
                <div className="data-logs-header">
                  <h2>Data Logs</h2>
                  <p>Real-time and historical sensor measurements</p>
                </div>
                
                {records.length === 0 ? (
                  <p className="no-records">No sensor data recorded yet. Waiting for ESP32 data...</p>
                ) : getFilteredRecords().length === 0 ? (
                  <p className="no-records">No records match the selected filters.</p>
                ) : (
                  <div className="records-table-wrapper">
                    <table className="records-table">
                      <thead>
                        <tr>
                          <th>Time Stamp</th>
                          {appliedSensorTypes.temperature && <th>Temp (°C)</th>}
                          {appliedSensorTypes.humidity && <th>Humidity (%)</th>}
                          {appliedSensorTypes.vocs && <th>VOCs (kΩ)</th>}
                          {appliedSensorTypes.no2 && <th>NO₂ (PPM)</th>}
                          {appliedSensorTypes.co && <th>CO (PPM)</th>}
                          {appliedSensorTypes.pm25 && <th>PM2.5 (µg/m³)</th>}
                          {appliedSensorTypes.pm10 && <th>PM10 (µg/m³)</th>}
                          <th>AQI</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {getFilteredRecords().map((record, index) => {
                          // Determine status based on sensor values
                          const isDanger = 
                            (record.temperature > 35) || 
                            (record.carbon_monoxide > 9) || 
                            (record.pm25 > 35) || 
                            (record.pm10 > 50);
                          
                          const isWarning = 
                            (record.temperature > 30 && record.temperature <= 35) || 
                            (record.carbon_monoxide > 5 && record.carbon_monoxide <= 9) || 
                            (record.pm25 > 25 && record.pm25 <= 35) || 
                            (record.pm10 > 35 && record.pm10 <= 50);
                          
                          const status = isDanger ? 'danger' : isWarning ? 'warning' : 'safe';
                          const aqi = calculateAQI(record);
                          
                          return (
                            <tr key={record.id}>
                              <td>{formatTimestamp(record.timestamp)}</td>
                              {appliedSensorTypes.temperature && <td>{record.temperature?.toFixed(1) || 'N/A'}</td>}
                              {appliedSensorTypes.humidity && <td>{record.humidity?.toFixed(1) || 'N/A'}</td>}
                              {appliedSensorTypes.vocs && <td>{record.vocs?.toFixed(1) || 'N/A'}</td>}
                              {appliedSensorTypes.no2 && <td>{record.nitrogen_dioxide?.toFixed(2) || 'N/A'}</td>}
                              {appliedSensorTypes.co && <td>{record.carbon_monoxide?.toFixed(2) || 'N/A'}</td>}
                              {appliedSensorTypes.pm25 && <td>{record.pm25?.toFixed(1) || 'N/A'}</td>}
                              {appliedSensorTypes.pm10 && <td>{record.pm10?.toFixed(1) || 'N/A'}</td>}
                              <td>
                                <span className="aqi-badge" style={{backgroundColor: aqi.color}}>
                                  {aqi.value}
                                </span>
                              </td>
                              <td>
                                <span className={`status-badge status-${status}`}>{status}</span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </section>
          )}

          {activePage === "graphs" && (
            <section className="graphs-page-container">
              {showGraphLoading && (
                <div className="graph-loading-overlay">
                  <div className="loading-spinner"></div>
                </div>
              )}
              <div className="records-header">
                <h1>Sensor Graphs</h1>
                <p className="records-subtitle">Real-time and historical sensor data visualization</p>
              </div>

              {/* Filters Section */}
              <div className="filters-container">
                <div className="filters-header">
                  <span className="filter-icon">▼</span> Filters
                </div>
                <div className="filters-content">
                  <div className="filter-group">
                    <label>📊 Sensor Types</label>
                    <div className="custom-dropdown">
                      <div 
                        className="dropdown-header"
                        onClick={() => setGraphSensorDropdownOpen(!graphSensorDropdownOpen)}
                      >
                        <span>Select Sensors</span>
                        <span className="dropdown-arrow">{graphSensorDropdownOpen ? '▲' : '▼'}</span>
                      </div>
                      {graphSensorDropdownOpen && (
                        <div className="dropdown-menu">
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={graphFilterSensorTypes.temperature}
                              onChange={() => toggleGraphSensorType('temperature')}
                            />
                            Temperature
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={graphFilterSensorTypes.humidity}
                              onChange={() => toggleGraphSensorType('humidity')}
                            />
                            Humidity
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={graphFilterSensorTypes.vocs}
                              onChange={() => toggleGraphSensorType('vocs')}
                            />
                            VOCs
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={graphFilterSensorTypes.no2}
                              onChange={() => toggleGraphSensorType('no2')}
                            />
                            NO₂
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={graphFilterSensorTypes.co}
                              onChange={() => toggleGraphSensorType('co')}
                            />
                            CO
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={graphFilterSensorTypes.pm25}
                              onChange={() => toggleGraphSensorType('pm25')}
                            />
                            PM2.5
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={graphFilterSensorTypes.pm10}
                              onChange={() => toggleGraphSensorType('pm10')}
                            />
                            PM10
                          </label>
                          <div className="dropdown-divider"></div>
                          <label className="dropdown-item clear-item">
                            <input 
                              type="checkbox" 
                              checked={clearGraphFilters}
                              onChange={(e) => setClearGraphFilters(e.target.checked)}
                            />
                            🔄 Clear all filters
                          </label>
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="filter-group">
                    <label>📅 Date</label>
                    <select 
                      className="filter-select"
                      value={graphFilterDate}
                      onChange={(e) => setGraphFilterDate(e.target.value)}
                    >
                      <option value="all">All Dates</option>
                      <option value="today">Today</option>
                      <option value="7days">Last 7 Days</option>
                      <option value="30days">Last 30 Days</option>
                    </select>
                  </div>
                  <button className="submit-filters-btn" onClick={handleGraphSubmit}>Submit</button>
                </div>
              </div>

              {!showGraphLoading && (
                <div className="graphs-content">
                  {graphData.length === 0 ? (
                    <p className="no-data">No data available yet. Waiting for sensor readings...</p>
                  ) : getFilteredGraphData().length === 0 ? (
                    <p className="no-data">No data matches the selected filters.</p>
                  ) : (
                  <div className="graphs-grid">
                    {/* Temperature Graph */}
                    {appliedGraphSensorTypes.temperature && (
                      <div className="graph-card">
                        <div className="graph-header">
                          <div className="graph-value">
                            {(() => {
                              const peak = getPeakValue('temperature');
                              return peak !== null ? (
                                <>
                                  <span className="current-value">{peak.toFixed(1)}</span>
                                  <span className="value-change">°C Peak</span>
                                </>
                              ) : '--';
                            })()}
                          </div>
                          <h3><Thermometer size={20} /> Temperature</h3>
                        </div>
                        <div style={{ width: '100%', height: '280px' }}>
                          <ResponsiveContainer debounce={300}>
                            <LineChart data={getFilteredGraphData()} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                              <XAxis 
                                dataKey="time" 
                                stroke="#999" 
                                tick={{ fontSize: 11, fill: '#999' }}
                                axisLine={false}
                                tickLine={false}
                              />
                              <YAxis 
                                stroke="#999" 
                                tick={{ fontSize: 11, fill: '#999' }}
                                axisLine={false}
                                tickLine={false}
                                domain={['auto', 'auto']}
                              />
                              <Tooltip 
                                contentStyle={{ 
                                  backgroundColor: 'rgba(255,255,255,0.95)', 
                                  border: '1px solid #ddd',
                                  borderRadius: '8px',
                                  padding: '10px'
                                }}
                                labelStyle={{ fontWeight: 'bold', marginBottom: '5px' }}
                                formatter={(value) => [value.toFixed(2), 'Temperature']}
                                labelFormatter={(label, payload) => {
                                  if (payload && payload[0]) {
                                    return payload[0].payload.fullTimestamp || label;
                                  }
                                  return label;
                                }}
                              />
                              <ReferenceLine 
                                y={18} 
                                stroke="#4caf50" 
                                strokeDasharray="5 5" 
                                strokeWidth={2}
                                label={{ value: 'Safe Min', position: 'insideBottomRight', fill: '#4caf50', fontSize: 10 }}
                              />
                              <ReferenceLine 
                                y={27} 
                                stroke="#4caf50" 
                                strokeDasharray="5 5" 
                                strokeWidth={2}
                                label={{ value: 'Safe Max', position: 'insideTopRight', fill: '#4caf50', fontSize: 10 }}
                              />
                              <ReferenceLine 
                                y={30} 
                                stroke="#f44336" 
                                strokeDasharray="5 5" 
                                strokeWidth={2}
                                label={{ value: 'Danger', position: 'insideTopRight', fill: '#f44336', fontSize: 10 }}
                              />
                              <Line 
                                type="monotone" 
                                dataKey="temperature" 
                                stroke="#5b6b8d" 
                                strokeWidth={3}
                                dot={{ fill: '#5b6b8d', r: 5, strokeWidth: 0 }}
                                activeDot={{ r: 8, fill: '#5b6b8d' }}
                                isAnimationActive={false}
                              />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                      </div>
                    )}

                    {/* Humidity Graph */}
                    {appliedGraphSensorTypes.humidity && (
                      <div className="graph-card">
                        <div className="graph-header">
                          <div className="graph-value">
                            {(() => {
                              const peak = getPeakValue('humidity');
                              return peak !== null ? (
                                <>
                                  <span className="current-value">{peak.toFixed(1)}</span>
                                  <span className="value-change">% Peak</span>
                                </>
                              ) : '--';
                            })()}
                          </div>
                          <h3><Droplet size={20} /> Humidity</h3>
                        </div>
                        <div style={{ width: '100%', height: '280px' }}>
                          <ResponsiveContainer debounce={300}>
                            <LineChart data={getFilteredGraphData()} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                              <XAxis 
                                dataKey="time" 
                                stroke="#999" 
                                tick={{ fontSize: 11, fill: '#999' }}
                                axisLine={false}
                                tickLine={false}
                              />
                              <YAxis 
                                stroke="#999" 
                                tick={{ fontSize: 11, fill: '#999' }}
                                axisLine={false}
                                tickLine={false}
                                domain={[0, 'auto']}
                              />
                              <Tooltip 
                                contentStyle={{ 
                                  backgroundColor: 'rgba(255,255,255,0.95)', 
                                  border: '1px solid #ddd',
                                  borderRadius: '8px',
                                  padding: '10px'
                                }}
                                labelStyle={{ fontWeight: 'bold', marginBottom: '5px' }}
                                formatter={(value) => [value.toFixed(2), 'Humidity']}
                                labelFormatter={(label, payload) => {
                                  if (payload && payload[0]) {
                                    return payload[0].payload.fullTimestamp || label;
                                  }
                                  return label;
                                }}
                              />
                              <ReferenceLine 
                                y={30} 
                                stroke="#4caf50" 
                                strokeDasharray="5 5" 
                                strokeWidth={2}
                                label={{ value: 'Safe Min', position: 'insideBottomRight', fill: '#4caf50', fontSize: 12 }}
                              />
                              <ReferenceLine 
                                y={60} 
                                stroke="#4caf50" 
                                strokeDasharray="5 5" 
                                strokeWidth={2}
                                label={{ value: 'Safe Max', position: 'insideTopRight', fill: '#4caf50', fontSize: 12 }}
                              />
                              <ReferenceLine 
                                y={70} 
                                stroke="#f44336" 
                                strokeDasharray="5 5" 
                                strokeWidth={2}
                                label={{ value: 'Danger', position: 'insideTopRight', fill: '#f44336', fontSize: 12 }}
                              />
                              <Line 
                                type="monotone" 
                                dataKey="humidity" 
                                stroke="#5b6b8d" 
                                strokeWidth={3}
                                dot={{ fill: '#5b6b8d', r: 5, strokeWidth: 0 }}
                                activeDot={{ r: 8, fill: '#5b6b8d' }}
                                isAnimationActive={false}
                              />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                      </div>
                    )}

                    {/* VOCs Graph */}
                    {appliedGraphSensorTypes.vocs && (
                      <div className="graph-card">
                        <div className="graph-header">
                          <div className="graph-value">
                            {(() => {
                              const peak = getPeakValue('vocs');
                              return peak !== null ? (
                                <>
                                  <span className="current-value">{peak.toFixed(1)}</span>
                                  <span className="value-change">kΩ Peak</span>
                                </>
                              ) : '--';
                            })()}
                          </div>
                          <h3><Activity size={20} /> VOCs</h3>
                        </div>
                        <div style={{ width: '100%', height: '280px' }}>
                          <ResponsiveContainer debounce={300}>
                            <LineChart data={getFilteredGraphData()} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                              <XAxis 
                                dataKey="time" 
                                stroke="#999" 
                                tick={{ fontSize: 11, fill: '#999' }}
                                axisLine={false}
                                tickLine={false}
                              />
                              <YAxis 
                                stroke="#999" 
                                tick={{ fontSize: 11, fill: '#999' }}
                                axisLine={false}
                                tickLine={false}
                                domain={['auto', 'auto']}
                              />
                              <Tooltip 
                                contentStyle={{ 
                                  backgroundColor: 'rgba(255,255,255,0.95)', 
                                  border: '1px solid #ddd',
                                  borderRadius: '8px',
                                  padding: '10px'
                                }}
                                labelStyle={{ fontWeight: 'bold', marginBottom: '5px' }}
                                formatter={(value) => [value.toFixed(2), 'VOCs']}
                                labelFormatter={(label, payload) => {
                                  if (payload && payload[0]) {
                                    return payload[0].payload.fullTimestamp || label;
                                  }
                                  return label;
                                }}
                              />
                              <ReferenceLine 
                                y={80} 
                                stroke="#4caf50" 
                                strokeDasharray="5 5" 
                                strokeWidth={2}
                                label={{ value: 'Safe', position: 'insideTopRight', fill: '#4caf50', fontSize: 10 }}
                              />
                              <ReferenceLine 
                                y={40} 
                                stroke="#f44336" 
                                strokeDasharray="5 5" 
                                strokeWidth={2}
                                label={{ value: 'Danger', position: 'insideTopRight', fill: '#f44336', fontSize: 10 }}
                              />
                              <Line 
                                type="monotone" 
                                dataKey="vocs" 
                                stroke="#5b6b8d" 
                                strokeWidth={3}
                                dot={{ fill: '#5b6b8d', r: 5, strokeWidth: 0 }}
                                activeDot={{ r: 8, fill: '#5b6b8d' }}
                                isAnimationActive={false}
                              />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                      </div>
                    )}

                    {/* NO2 Graph */}
                    {appliedGraphSensorTypes.no2 && (
                    <div className="graph-card">
                      <div className="graph-header">
                        <div className="graph-value">
                          {(() => {
                            const peak = getPeakValue('no2');
                            return peak !== null ? (
                              <>
                                <span className="current-value">{peak.toFixed(2)}</span>
                                <span className="value-change">PPM Peak</span>
                              </>
                            ) : '--';
                          })()}
                        </div>
                        <h3><Wind size={20} /> Nitrogen Dioxide</h3>
                      </div>
                      <div style={{ width: '100%', height: '280px' }}>
                        <ResponsiveContainer debounce={300}>
                          <LineChart data={getFilteredGraphData()} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                            <XAxis 
                              dataKey="time" 
                              stroke="#999" 
                              tick={{ fontSize: 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                            />
                            <YAxis 
                              stroke="#999" 
                              tick={{ fontSize: 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                              domain={['auto', 'auto']}
                            />
                            <Tooltip 
                              contentStyle={{ 
                                backgroundColor: 'rgba(255,255,255,0.95)', 
                                border: '1px solid #ddd',
                                borderRadius: '8px',
                                padding: '10px'
                              }}
                              labelStyle={{ fontWeight: 'bold', marginBottom: '5px' }}
                              formatter={(value) => [value.toFixed(4), 'NO2']}
                              labelFormatter={(label, payload) => {
                                if (payload && payload[0]) {
                                  return payload[0].payload.fullTimestamp || label;
                                }
                                return label;
                              }}
                            />
                            <ReferenceLine 
                              y={0.053} 
                              stroke="#4caf50" 
                              strokeDasharray="5 5" 
                              strokeWidth={2}
                              label={{ value: 'Safe', position: 'insideTopRight', fill: '#4caf50', fontSize: 10 }}
                            />
                            <ReferenceLine 
                              y={0.1} 
                              stroke="#f44336" 
                              strokeDasharray="5 5" 
                              strokeWidth={2}
                              label={{ value: 'Danger', position: 'insideTopRight', fill: '#f44336', fontSize: 10 }}
                            />
                            <Line 
                              type="monotone" 
                              dataKey="no2" 
                              stroke="#5b6b8d" 
                              strokeWidth={3}
                              dot={{ fill: '#5b6b8d', r: 5, strokeWidth: 0 }}
                              activeDot={{ r: 8, fill: '#5b6b8d' }}
                              isAnimationActive={false}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                    )}

                    {/* CO Graph */}
                    {appliedGraphSensorTypes.co && (
                    <div className="graph-card">
                      <div className="graph-header">
                        <div className="graph-value">
                          {(() => {
                            const peak = getPeakValue('co');
                            return peak !== null ? (
                              <>
                                <span className="current-value">{peak.toFixed(2)}</span>
                                <span className="value-change">PPM Peak</span>
                              </>
                            ) : '--';
                          })()}
                        </div>
                        <h3><Flame size={20} /> Carbon Monoxide</h3>
                      </div>
                      <div style={{ width: '100%', height: '280px' }}>
                        <ResponsiveContainer debounce={300}>
                          <LineChart data={getFilteredGraphData()} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                            <XAxis 
                              dataKey="time" 
                              stroke="#999" 
                              tick={{ fontSize: 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                            />
                            <YAxis 
                              stroke="#999" 
                              tick={{ fontSize: 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                              domain={[(dataMin) => {
                                // Start from 80% of minimum value or 0
                                const minValue = Math.max(0, dataMin * 0.8);
                                return Math.floor(minValue * 1000) / 1000;
                              }, (dataMax) => {
                                // Add 20% padding to max value for better visibility
                                const maxValue = dataMax * 1.2;
                                return Math.ceil(maxValue * 1000) / 1000;
                              }]}
                            />
                            <Tooltip 
                              contentStyle={{ 
                                backgroundColor: 'rgba(255,255,255,0.95)', 
                                border: '1px solid #ddd',
                                borderRadius: '8px',
                                padding: '10px'
                              }}
                              labelStyle={{ fontWeight: 'bold', marginBottom: '5px' }}
                              formatter={(value) => [value.toFixed(4), 'CO']}
                              labelFormatter={(label, payload) => {
                                if (payload && payload[0]) {
                                  return payload[0].payload.fullTimestamp || label;
                                }
                                return label;
                              }}
                            />
                            <Line 
                              type="monotone" 
                              dataKey="co" 
                              stroke="#5b6b8d" 
                              strokeWidth={3}
                              dot={{ fill: '#5b6b8d', r: 5, strokeWidth: 0 }}
                              activeDot={{ r: 8, fill: '#5b6b8d' }}
                              isAnimationActive={false}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                    )}

                    {/* PM2.5 Graph */}
                    {appliedGraphSensorTypes.pm25 && (
                    <div className="graph-card">
                      <div className="graph-header">
                        <div className="graph-value">
                          {(() => {
                            const peak = getPeakValue('pm25');
                            return peak !== null ? (
                              <>
                                <span className="current-value">{peak.toFixed(1)}</span>
                                <span className="value-change">µg/m³ Peak</span>
                              </>
                            ) : '--';
                          })()}
                        </div>
                        <h3><Circle size={20} /> PM 2.5</h3>
                      </div>
                      <div style={{ width: '100%', height: '280px' }}>
                        <ResponsiveContainer debounce={300}>
                          <LineChart data={getFilteredGraphData()} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                            <XAxis 
                              dataKey="time" 
                              stroke="#999" 
                              tick={{ fontSize: 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                            />
                            <YAxis 
                              stroke="#999" 
                              tick={{ fontSize: 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                              domain={['auto', 'auto']}
                            />
                            <Tooltip 
                              contentStyle={{ 
                                backgroundColor: 'rgba(255,255,255,0.95)', 
                                border: '1px solid #ddd',
                                borderRadius: '8px',
                                padding: '10px'
                              }}
                              labelStyle={{ fontWeight: 'bold', marginBottom: '5px' }}
                              formatter={(value) => [value.toFixed(2), 'PM2.5']}
                              labelFormatter={(label, payload) => {
                                if (payload && payload[0]) {
                                  return payload[0].payload.fullTimestamp || label;
                                }
                                return label;
                              }}
                            />
                            <ReferenceLine 
                              y={12} 
                              stroke="#4caf50" 
                              strokeDasharray="5 5" 
                              strokeWidth={2}
                              label={{ value: 'Safe', position: 'insideTopRight', fill: '#4caf50', fontSize: 10 }}
                            />
                            <ReferenceLine 
                              y={35} 
                              stroke="#f44336" 
                              strokeDasharray="5 5" 
                              strokeWidth={2}
                              label={{ value: 'Danger', position: 'insideTopRight', fill: '#f44336', fontSize: 10 }}
                            />
                            <Line 
                              type="monotone" 
                              dataKey="pm25" 
                              stroke="#5b6b8d" 
                              strokeWidth={3}
                              dot={{ fill: '#5b6b8d', r: 5, strokeWidth: 0 }}
                              activeDot={{ r: 8, fill: '#5b6b8d' }}
                              isAnimationActive={false}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                    )}

                    {/* PM10 Graph */}
                    {appliedGraphSensorTypes.pm10 && (
                    <div className="graph-card">
                      <div className="graph-header">
                        <div className="graph-value">
                          {(() => {
                            const peak = getPeakValue('pm10');
                            return peak !== null ? (
                              <>
                                <span className="current-value">{peak.toFixed(1)}</span>
                                <span className="value-change">µg/m³ Peak</span>
                              </>
                            ) : '--';
                          })()}
                        </div>
                        <h3><Circle size={20} /> PM 10</h3>
                      </div>
                      <div style={{ width: '100%', height: '280px' }}>
                        <ResponsiveContainer debounce={300}>
                          <LineChart data={getFilteredGraphData()} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                            <XAxis 
                              dataKey="time" 
                              stroke="#999" 
                              tick={{ fontSize: 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                            />
                            <YAxis 
                              stroke="#999" 
                              tick={{ fontSize: 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                              domain={[0, (dataMax) => Math.max(dataMax, 160)]}
                            />
                            <Tooltip 
                              contentStyle={{ 
                                backgroundColor: 'rgba(255,255,255,0.95)', 
                                border: '1px solid #ddd',
                                borderRadius: '8px',
                                padding: '10px'
                              }}
                              labelStyle={{ fontWeight: 'bold', marginBottom: '5px' }}
                              formatter={(value) => [value.toFixed(2), 'PM10']}
                              labelFormatter={(label, payload) => {
                                if (payload && payload[0]) {
                                  return payload[0].payload.fullTimestamp || label;
                                }
                                return label;
                              }}
                            />
                            <ReferenceLine 
                              y={50} 
                              stroke="#4caf50" 
                              strokeDasharray="5 5" 
                              strokeWidth={2}
                              label={{ value: 'Safe', position: 'insideTopRight', fill: '#4caf50', fontSize: 10 }}
                            />
                            <ReferenceLine 
                              y={150} 
                              stroke="#f44336" 
                              strokeDasharray="5 5" 
                              strokeWidth={2}
                              label={{ value: 'Danger', position: 'insideTopRight', fill: '#f44336', fontSize: 10 }}
                            />
                            <Line 
                              type="monotone" 
                              dataKey="pm10" 
                              stroke="#5b6b8d" 
                              strokeWidth={3}
                              dot={{ fill: '#5b6b8d', r: 5, strokeWidth: 0 }}
                              activeDot={{ r: 8, fill: '#5b6b8d' }}
                              isAnimationActive={false}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                    )}
                  </div>
                )}
              </div>
              )}
            </section>
          )}
      </main>
    </div>
  )
}

export default Dashboard




