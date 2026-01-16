import './styles/Dashboard.css';
import { useNavigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

function Dashboard() {
  const [activePage, setActivePage] = useState("dashboard");
  const [showDashboardSub, setShowDashboardSub] = useState(false);
  const [sensorData, setSensorData] = useState(null);
  const [records, setRecords] = useState([]);
  const [graphData, setGraphData] = useState([]);
  const navigate = useNavigate();

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
        setSensorData(result.data);
      }
    } catch (error) {
      console.error('Error fetching sensor data:', error);
    }
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
    return date.toLocaleString();
  };

  return (
    <div className="dashboard">
      {/* top bar */}
      <header className="top-bar">
        <h1>SMOKi</h1>
        <button id="logoutBtn" onClick={handleLogout}>Logout</button>
      </header>

      {/* main content */}
      <main className="content">
        {/* sidebar */}
        <aside className="sidebar">
          <ul>
            <li 
              onClick={() => {
                setActivePage("dashboard");
                setShowDashboardSub(!showDashboardSub);
              }}
              className={activePage === "dashboard" ? "active" : ""}
            >
              <span>🏠</span>
              <span className="text">Dashboard</span>
              <span className="text arrow">{showDashboardSub ? "▼" : "▶"}</span>
            </li>
            {showDashboardSub && (
              <li 
                onClick={() => setActivePage("sensors")}
                className={`sub-item ${activePage === "sensors" ? "active" : ""}`}
              >
                <span>📡</span>
                <span className="text">Sensors</span>
              </li>
            )}
            <li 
              onClick={() => setActivePage("camera")}
              className={activePage === "camera" ? "active" : ""}
            >
              <span>📹</span>
              <span className="text">Camera</span>
            </li>
            <li 
              onClick={() => setActivePage("records")}
              className={activePage === "records" ? "active" : ""}
            >
              <span>📋</span>
              <span className="text">Records</span>
            </li>
            <li 
              onClick={() => setActivePage("graphs")}
              className={activePage === "graphs" ? "active" : ""}
            >
              <span>📊</span>
              <span className="text">Graphs</span>
            </li>
          </ul>
        </aside>

        {/* main content area */}
        <div className="main-content">
          {activePage === "dashboard" && (
            <section className="home-page-container">
              <div className="hp_container_1">
                <span>Welcome to</span>
                <h1>SMOKi</h1>
                <p>
                  Lorem ipsum dolor sit amet, consectetur adipiscing elit.
                  Morbi volutpat tempor feugiat. Sed ac nunc ligula. Quisque a tincidunt massa,
                  at commodo orci. Donec ante mi, malesuada nec sapien at, mattis finibus ex.
                  Curabitur nec quam neque. Quisque vel semper justo. Mauris at fermentum nibh.
                </p>
              </div>

              <div className="hp_container_2">
                <h1>Device Image</h1>
              </div>
            </section>
          )}

          {activePage === "sensors" && (
            <section className="sensors-page-container">
              <div className="sensors-grid">
                <div className="sensor-card">
                  <div className="sensor-icon">🌡️</div>
                  <h3>Temperature</h3>
                  <div className="sensor-value">
                    {sensorData?.temperature ? `${sensorData.temperature.toFixed(1)}°C` : '--°C'}
                  </div>
                  <div className="sensor-status">
                    {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                  </div>
                </div>
                
                <div className="sensor-card">
                  <div className="sensor-icon">💧</div>
                  <h3>Humidity</h3>
                  <div className="sensor-value">
                    {sensorData?.humidity ? `${sensorData.humidity.toFixed(1)}%` : '--%'}
                  </div>
                  <div className="sensor-status">
                    {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                  </div>
                </div>
                
                <div className="sensor-card">
                  <div className="sensor-icon">🌫️</div>
                  <h3>VOCs</h3>
                  <div className="sensor-value">
                    {sensorData?.vocs ? `${sensorData.vocs.toFixed(1)} kΩ` : '-- kΩ'}
                  </div>
                  <div className="sensor-status">
                    {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                  </div>
                </div>

                <div className="sensor-card">
                  <div className="sensor-icon">💨</div>
                  <h3>Nitrogen Dioxide</h3>
                  <div className="sensor-value">
                    {sensorData?.nitrogen_dioxide ? `${sensorData.nitrogen_dioxide.toFixed(2)} PPM` : '-- PPM'}
                  </div>
                  <div className="sensor-status">
                    {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                  </div>
                </div>
                
                <div className="sensor-card">
                  <div className="sensor-icon">🔥</div>
                  <h3>Carbon Monoxide</h3>
                  <div className="sensor-value">
                    {sensorData?.carbon_monoxide ? `${sensorData.carbon_monoxide.toFixed(2)} PPM` : '-- PPM'}
                  </div>
                  <div className="sensor-status">
                    {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                  </div>
                </div>

                <div className="sensor-card">
                  <div className="sensor-icon">⚫</div>
                  <h3>PM 2.5</h3>
                  <div className="sensor-value">
                    {sensorData?.pm25 ? `${sensorData.pm25.toFixed(1)} µg/m³` : '-- µg/m³'}
                  </div>
                  <div className="sensor-status">
                    {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                  </div>
                </div>
                
                <div className="sensor-card">
                  <div className="sensor-icon">⚫</div>
                  <h3>PM 10</h3>
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
              <h1>Sensor Records</h1>
              <div className="records-content">
                {records.length === 0 ? (
                  <p className="no-records">No sensor data recorded yet. Waiting for ESP32 data...</p>
                ) : (
                  <div className="records-table-container">
                    <table className="records-table">
                      <thead>
                        <tr>
                          <th>Timestamp</th>
                          <th>Temp (°C)</th>
                          <th>Humidity (%)</th>
                          <th>VOCs (kΩ)</th>
                          <th>NO₂ (PPM)</th>
                          <th>CO (PPM)</th>
                          <th>PM2.5 (µg/m³)</th>
                          <th>PM10 (µg/m³)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {records.map((record) => (
                          <tr key={record.id}>
                            <td>{formatTimestamp(record.timestamp)}</td>
                            <td>{record.temperature?.toFixed(1) || 'N/A'}</td>
                            <td>{record.humidity?.toFixed(1) || 'N/A'}</td>
                            <td>{record.vocs?.toFixed(1) || 'N/A'}</td>
                            <td>{record.nitrogen_dioxide?.toFixed(2) || 'N/A'}</td>
                            <td>{record.carbon_monoxide?.toFixed(2) || 'N/A'}</td>
                            <td>{record.pm25?.toFixed(1) || 'N/A'}</td>
                            <td>{record.pm10?.toFixed(1) || 'N/A'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </section>
          )}

          {activePage === "graphs" && (
            <section className="graphs-page-container">
              <h1>Sensor Graphs</h1>
              <div className="graphs-content">
                {graphData.length === 0 ? (
                  <p className="no-data">No data available yet. Waiting for sensor readings...</p>
                ) : (
                  <div className="graphs-grid">
                    {/* Temperature Graph */}
                    <div className="graph-card">
                      <h3>🌡️ Temperature (°C)</h3>
                      <ResponsiveContainer width="100%" height={200}>
                        <LineChart data={graphData}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="time" />
                          <YAxis />
                          <Tooltip />
                          <Line type="monotone" dataKey="temperature" stroke="#ff6600" strokeWidth={2} />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>

                    {/* Humidity Graph */}
                    <div className="graph-card">
                      <h3>💧 Humidity (%)</h3>
                      <ResponsiveContainer width="100%" height={200}>
                        <LineChart data={graphData}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="time" />
                          <YAxis />
                          <Tooltip />
                          <Line type="monotone" dataKey="humidity" stroke="#2196F3" strokeWidth={2} />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>

                    {/* VOCs Graph */}
                    <div className="graph-card">
                      <h3>🌫️ VOCs (kΩ)</h3>
                      <ResponsiveContainer width="100%" height={200}>
                        <LineChart data={graphData}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="time" />
                          <YAxis />
                          <Tooltip />
                          <Line type="monotone" dataKey="vocs" stroke="#9C27B0" strokeWidth={2} />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>

                    {/* NO2 Graph */}
                    <div className="graph-card">
                      <h3>💨 Nitrogen Dioxide (PPM)</h3>
                      <ResponsiveContainer width="100%" height={200}>
                        <LineChart data={graphData}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="time" />
                          <YAxis />
                          <Tooltip />
                          <Line type="monotone" dataKey="no2" stroke="#FF9800" strokeWidth={2} />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>

                    {/* CO Graph */}
                    <div className="graph-card">
                      <h3>🔥 Carbon Monoxide (PPM)</h3>
                      <ResponsiveContainer width="100%" height={200}>
                        <LineChart data={graphData}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="time" />
                          <YAxis />
                          <Tooltip />
                          <Line type="monotone" dataKey="co" stroke="#F44336" strokeWidth={2} />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>

                    {/* PM2.5 Graph */}
                    <div className="graph-card">
                      <h3>⚫ PM 2.5 (µg/m³)</h3>
                      <ResponsiveContainer width="100%" height={200}>
                        <LineChart data={graphData}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="time" />
                          <YAxis />
                          <Tooltip />
                          <Line type="monotone" dataKey="pm25" stroke="#607D8B" strokeWidth={2} />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>

                    {/* PM10 Graph */}
                    <div className="graph-card">
                      <h3>⚫ PM 10 (µg/m³)</h3>
                      <ResponsiveContainer width="100%" height={200}>
                        <LineChart data={graphData}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="time" />
                          <YAxis />
                          <Tooltip />
                          <Line type="monotone" dataKey="pm10" stroke="#795548" strokeWidth={2} />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                )}
              </div>
            </section>
          )}
        </div>
      </main>
    </div>
  )
}

export default Dashboard
