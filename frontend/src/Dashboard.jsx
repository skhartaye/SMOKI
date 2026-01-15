import './styles/Dashboard.css';
import { useNavigate } from 'react-router-dom';
import { useState } from 'react';

function Dashboard() {
  const [activePage, setActivePage] = useState("dashboard");
  const navigate = useNavigate();

  function handleLogout() {
    localStorage.removeItem('isLoggedIn');
    navigate('/');
  }

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
              onClick={() => setActivePage("dashboard")}
              className={activePage === "dashboard" ? "active" : ""}
            >
              <span>🏠</span>
              <span className="text">Dashboard</span>
            </li>
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
              <h1>Records</h1>
              <div className="records-content">
                <p>Vehicle smoke detection records will appear here.</p>
              </div>
            </section>
          )}

          {activePage === "graphs" && (
            <section className="graphs-page-container">
              <h1>Graphs & Analytics</h1>
              <div className="graphs-content">
                <p>Statistical data and graphs will be displayed here.</p>
              </div>
            </section>
          )}
        </div>
      </main>
    </div>
  )
}

export default Dashboard
