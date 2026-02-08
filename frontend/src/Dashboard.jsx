import './styles/Dashboard.css';
import { useNavigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { TbTemperature, TbDroplet, TbWind, TbFlame, TbCircleFilled, TbLayoutDashboard, TbFileText, TbChartLine, TbRadar, TbMoon, TbSun, TbLogout, TbMenu2 } from 'react-icons/tb';
import { MdOutlineScience } from 'react-icons/md';

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
    if (!previous || !current || previous === 0) return null;
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
      const response = await fetch(`${API_URL}/api/sensors/data?limit=20`);
      const result = await response.json();
      if (result.success) {
        // Format data for graphs (reverse to show oldest first)
        const formatted = result.data.reverse().map(item => ({
          time: new Date(item.timestamp).toLocaleTimeString(),
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
    // Simple AQI calculation based on PM2.5 (US EPA standard)
    const pm25 = record.pm25 || 0;
    
    if (pm25 <= 12) return { value: Math.round((50 / 12) * pm25), category: 'Good', color: '#4caf50' };
    if (pm25 <= 35.4) return { value: Math.round(50 + ((100 - 50) / (35.4 - 12.1)) * (pm25 - 12.1)), category: 'Moderate', color: '#ffc107' };
    if (pm25 <= 55.4) return { value: Math.round(100 + ((150 - 100) / (55.4 - 35.5)) * (pm25 - 35.5)), category: 'Unhealthy for Sensitive', color: '#ff9800' };
    if (pm25 <= 150.4) return { value: Math.round(150 + ((200 - 150) / (150.4 - 55.5)) * (pm25 - 55.5)), category: 'Unhealthy', color: '#f44336' };
    if (pm25 <= 250.4) return { value: Math.round(200 + ((300 - 200) / (250.4 - 150.5)) * (pm25 - 150.5)), category: 'Very Unhealthy', color: '#9c27b0' };
    return { value: Math.round(300 + ((500 - 300) / (500.4 - 250.5)) * (pm25 - 250.5)), category: 'Hazardous', color: '#7b1fa2' };
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

    return filtered;
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
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <h1>
            <span className="menu-icon"><TbMenu2 /></span>
            <span className="menu-text">SMOKi</span>
          </h1>
        </div>

        <nav className="sidebar-nav">
          <button 
            onClick={() => setActivePage("dashboard")}
            className={`nav-item ${activePage === "dashboard" ? "active" : ""}`}
          >
            <span className="nav-icon"><TbLayoutDashboard /></span>
            <span className="nav-text">Dashboard</span>
          </button>

          <button 
            onClick={() => setActivePage("records")}
            className={`nav-item ${activePage === "records" ? "active" : ""}`}
          >
            <span className="nav-icon"><TbFileText /></span>
            <span className="nav-text">Records</span>
          </button>

          <button 
            onClick={() => setActivePage("graphs")}
            className={`nav-item ${activePage === "graphs" ? "active" : ""}`}
          >
            <span className="nav-icon"><TbChartLine /></span>
            <span className="nav-text">Graphs</span>
          </button>

          <button 
            onClick={() => setActivePage("sensors")}
            className={`nav-item ${activePage === "sensors" ? "active" : ""}`}
          >
            <span className="nav-icon"><TbRadar /></span>
            <span className="nav-text">Sensors</span>
          </button>

          <button 
            onClick={() => setDarkMode(!darkMode)}
            className="nav-item"
          >
            <span className="nav-icon">{darkMode ? <TbSun /> : <TbMoon />}</span>
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
            <span><TbLogout /></span>
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
            <section className="sensors-page-container">
              <div className="sensors-grid">
                <div className="sensor-card">
                  <div className="sensor-card-header">
                    <div className="sensor-icon"><TbTemperature /></div>
                    <h3>Temperature</h3>
                  </div>
                  {(() => {
                    const change = calculateChange(sensorData?.temperature, previousSensorData?.temperature);
                    return change !== null && (
                      <div className={`sensor-change ${change >= 0 ? 'positive' : 'negative'}`}>
                        {change >= 0 ? '↑' : '↓'} {Math.abs(change).toFixed(1)}%
                      </div>
                    );
                  })()}
                  <div className="sensor-value">
                    {sensorData?.temperature ? `${sensorData.temperature.toFixed(1)}°C` : '--°C'}
                  </div>
                  <div className="sensor-status">
                    {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                  </div>
                </div>
                
                <div className="sensor-card">
                  <div className="sensor-card-header">
                    <div className="sensor-icon"><TbDroplet /></div>
                    <h3>Humidity</h3>
                  </div>
                  {(() => {
                    const change = calculateChange(sensorData?.humidity, previousSensorData?.humidity);
                    return change !== null && (
                      <div className={`sensor-change ${change >= 0 ? 'positive' : 'negative'}`}>
                        {change >= 0 ? '↑' : '↓'} {Math.abs(change).toFixed(1)}%
                      </div>
                    );
                  })()}
                  <div className="sensor-value">
                    {sensorData?.humidity ? `${sensorData.humidity.toFixed(1)}%` : '--%'}
                  </div>
                  <div className="sensor-status">
                    {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                  </div>
                </div>
                
                <div className="sensor-card">
                  <div className="sensor-card-header">
                    <div className="sensor-icon"><MdOutlineScience /></div>
                    <h3>VOCs</h3>
                  </div>
                  {(() => {
                    const change = calculateChange(sensorData?.vocs, previousSensorData?.vocs);
                    return change !== null && (
                      <div className={`sensor-change ${change >= 0 ? 'positive' : 'negative'}`}>
                        {change >= 0 ? '↑' : '↓'} {Math.abs(change).toFixed(1)}%
                      </div>
                    );
                  })()}
                  <div className="sensor-value">
                    {sensorData?.vocs ? `${sensorData.vocs.toFixed(1)} kΩ` : '-- kΩ'}
                  </div>
                  <div className="sensor-status">
                    {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                  </div>
                </div>

                <div className="sensor-card">
                  <div className="sensor-card-header">
                    <div className="sensor-icon"><TbWind /></div>
                    <h3>Nitrogen Dioxide</h3>
                  </div>
                  {(() => {
                    const change = calculateChange(sensorData?.nitrogen_dioxide, previousSensorData?.nitrogen_dioxide);
                    return change !== null && (
                      <div className={`sensor-change ${change >= 0 ? 'positive' : 'negative'}`}>
                        {change >= 0 ? '↑' : '↓'} {Math.abs(change).toFixed(1)}%
                      </div>
                    );
                  })()}
                  <div className="sensor-value">
                    {sensorData?.nitrogen_dioxide ? `${sensorData.nitrogen_dioxide.toFixed(2)} PPM` : '-- PPM'}
                  </div>
                  <div className="sensor-status">
                    {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                  </div>
                </div>
                
                <div className="sensor-card">
                  <div className="sensor-card-header">
                    <div className="sensor-icon"><TbFlame /></div>
                    <h3>Carbon Monoxide</h3>
                  </div>
                  {(() => {
                    const change = calculateChange(sensorData?.carbon_monoxide, previousSensorData?.carbon_monoxide);
                    return change !== null && (
                      <div className={`sensor-change ${change >= 0 ? 'positive' : 'negative'}`}>
                        {change >= 0 ? '↑' : '↓'} {Math.abs(change).toFixed(1)}%
                      </div>
                    );
                  })()}
                  <div className="sensor-value">
                    {sensorData?.carbon_monoxide ? `${sensorData.carbon_monoxide.toFixed(2)} PPM` : '-- PPM'}
                  </div>
                  <div className="sensor-status">
                    {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                  </div>
                </div>

                <div className="sensor-card">
                  <div className="sensor-card-header">
                    <div className="sensor-icon"><TbCircleFilled /></div>
                    <h3>PM 2.5</h3>
                  </div>
                  {(() => {
                    const change = calculateChange(sensorData?.pm25, previousSensorData?.pm25);
                    return change !== null && (
                      <div className={`sensor-change ${change >= 0 ? 'positive' : 'negative'}`}>
                        {change >= 0 ? '↑' : '↓'} {Math.abs(change).toFixed(1)}%
                      </div>
                    );
                  })()}
                  <div className="sensor-value">
                    {sensorData?.pm25 ? `${sensorData.pm25.toFixed(1)} µg/m³` : '-- µg/m³'}
                  </div>
                  <div className="sensor-status">
                    {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                  </div>
                </div>
                
                <div className="sensor-card">
                  <div className="sensor-card-header">
                    <div className="sensor-icon"><TbCircleFilled /></div>
                    <h3>PM 10</h3>
                  </div>
                  {(() => {
                    const change = calculateChange(sensorData?.pm10, previousSensorData?.pm10);
                    return change !== null && (
                      <div className={`sensor-change ${change >= 0 ? 'positive' : 'negative'}`}>
                        {change >= 0 ? '↑' : '↓'} {Math.abs(change).toFixed(1)}%
                      </div>
                    );
                  })()}
                  <div className="sensor-value">
                    {sensorData?.pm10 ? `${sensorData.pm10.toFixed(1)} µg/m³` : '-- µg/m³'}
                  </div>
                  <div className="sensor-status">
                    {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                  </div>
                </div>
              </div>
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
                        <h3>🌡️ Temperature (°C)</h3>
                        <div style={{ width: '100%', height: '200px' }}>
                          <ResponsiveContainer debounce={300}>
                            <LineChart data={getFilteredGraphData()}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#ddd" />
                              <XAxis dataKey="time" stroke="#666" />
                              <YAxis stroke="#666" />
                              <Tooltip 
                                contentStyle={{ 
                                  backgroundColor: 'rgba(255,255,255,0.95)', 
                                  border: '1px solid #ddd',
                                  borderRadius: '8px',
                                  padding: '10px'
                                }}
                                labelStyle={{ fontWeight: 'bold', marginBottom: '5px' }}
                              />
                              <Line 
                                type="monotone" 
                                dataKey="temperature" 
                                stroke="#ff6600" 
                                strokeWidth={2}
                                dot={{ r: 4 }}
                                activeDot={{ r: 6 }}
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
                        <h3>💧 Humidity (%)</h3>
                        <div style={{ width: '100%', height: '200px' }}>
                          <ResponsiveContainer debounce={300}>
                            <LineChart data={getFilteredGraphData()}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#ddd" />
                              <XAxis dataKey="time" stroke="#666" />
                              <YAxis stroke="#666" />
                              <Tooltip 
                                contentStyle={{ 
                                  backgroundColor: 'rgba(255,255,255,0.95)', 
                                  border: '1px solid #ddd',
                                  borderRadius: '8px',
                                  padding: '10px'
                                }}
                                labelStyle={{ fontWeight: 'bold', marginBottom: '5px' }}
                              />
                              <Line 
                                type="monotone" 
                                dataKey="humidity" 
                                stroke="#2196F3" 
                                strokeWidth={2}
                                dot={{ r: 4 }}
                                activeDot={{ r: 6 }}
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
                        <h3>🌫️ VOCs (kΩ)</h3>
                        <div style={{ width: '100%', height: '200px' }}>
                          <ResponsiveContainer debounce={300}>
                            <LineChart data={getFilteredGraphData()}>
                              <CartesianGrid strokeDasharray="3 3" />
                              <XAxis dataKey="time" />
                              <YAxis />
                              <Tooltip />
                              <Line type="monotone" dataKey="vocs" stroke="#9C27B0" strokeWidth={2} isAnimationActive={false} />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                      </div>
                    )}

                    {/* NO2 Graph */}
                    {appliedGraphSensorTypes.no2 && (
                    <div className="graph-card">
                      <h3>💨 Nitrogen Dioxide (PPM)</h3>
                      <div style={{ width: '100%', height: '200px' }}>
                        <ResponsiveContainer debounce={300}>
                          <LineChart data={getFilteredGraphData()}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="time" />
                            <YAxis />
                            <Tooltip />
                            <Line type="monotone" dataKey="no2" stroke="#FF9800" strokeWidth={2} isAnimationActive={false} />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                    )}

                    {/* CO Graph */}
                    {appliedGraphSensorTypes.co && (
                    <div className="graph-card">
                      <h3>🔥 Carbon Monoxide (PPM)</h3>
                      <div style={{ width: '100%', height: '200px' }}>
                        <ResponsiveContainer debounce={300}>
                          <LineChart data={getFilteredGraphData()}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="time" />
                            <YAxis />
                            <Tooltip />
                            <Line type="monotone" dataKey="co" stroke="#F44336" strokeWidth={2} isAnimationActive={false} />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                    )}

                    {/* PM2.5 Graph */}
                    {appliedGraphSensorTypes.pm25 && (
                    <div className="graph-card">
                      <h3>⚫ PM 2.5 (µg/m³)</h3>
                      <div style={{ width: '100%', height: '200px' }}>
                        <ResponsiveContainer debounce={300}>
                          <LineChart data={getFilteredGraphData()}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="time" />
                            <YAxis />
                            <Tooltip />
                            <Line type="monotone" dataKey="pm25" stroke="#607D8B" strokeWidth={2} isAnimationActive={false} />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                    )}

                    {/* PM10 Graph */}
                    {appliedGraphSensorTypes.pm10 && (
                    <div className="graph-card">
                      <h3>⚫ PM 10 (µg/m³)</h3>
                      <div style={{ width: '100%', height: '200px' }}>
                        <ResponsiveContainer debounce={300}>
                          <LineChart data={getFilteredGraphData()}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="time" />
                            <YAxis />
                            <Tooltip />
                            <Line type="monotone" dataKey="pm10" stroke="#795548" strokeWidth={2} isAnimationActive={false} />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                    )}
                  </div>
                )}
              </div>
            </section>
          )}
      </main>
    </div>
  )
}

export default Dashboard
