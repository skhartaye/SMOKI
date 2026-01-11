// import './styles/App.css'
import './styles/Dashboard.css';
import { useNavigate } from 'react-router-dom';
import { useState } from 'react';


function Dashboard() {

    const [isCollapsed, setIsCollapsed] = useState(false);

    const navigate = useNavigate()
    const handleToggleSidebar = () => {
        setIsCollapsed(!isCollapsed);
    };

    function handleLogout(){
        localStorage.removeItem('isLoggedIn');
        console.log('Logging out');
        navigate('/');
    }

    return (
    <div className="dashboard">
    
        <div className="page">

            {/* top bar f top line */}
            <header className="top-bar">
                <h1>SMOKi</h1>
                <button id="logoutBtn" onClick={handleLogout}>Logout</button>
            </header>

{/* REMOVE THIS AND STOP CTRL Z */}

            {/* main content */}
            <main className={`content ${isCollapsed ? "collapsed" : ""}`}>
                {/* left column vertical f line */}
                <aside className="sidebar">
                    <button className="toggle-button" onClick={handleToggleSidebar}>
                        {isCollapsed ? "➡️" : "⬅️"}
                    </button>
                    <ul>
                        <li onClick={() => setActivePage("dashboard")}>Dashboard</li>
                        <li onClick={() => setActivePage("camera")}>Camera</li>
                        <li onClick={() => setActivePage("records")}>Records</li>
                        <li onClick={() => setActivePage("graphs")}>Graphs</li>
                    </ul>
                </aside>


{/* REMOVE THIS AND STOP CTRL Z */}

                {/* right contant f horizontal lines */}
                <main className="main-content">
                    <section className="home-page-container">
                        <div className="hp_container_1">
                            <span>text</span>
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
{/* 
                        <div className="hp_container_3">
                            <h1>Device Image One</h1>
                        </div>
                        <div className="hp_container_4">
                            <h1>Device Image Two</h1>
                        </div>
                        <div className="hp_container_5">
                            <h1>Device Image Three</h1>
                        </div>      */}
                    </section>

                    <section className="camera-page-container">
                        <div className='cp-visual-container'>
                            CAMERA
                        </div>

                        <div className='cp-readings-container'>
                            CAMERA 2
                            
                            <div className='cp-records-container'>

                                <div className='cp-time'>
                                    time
                                </div>
                                <div className='cp-vehicle-type'>
                                    vehicle type
                                </div>
                                <div className='cp-plate'>
                                    license plate
                                </div>

                                <div className='cp-smoke-detected'>
                                    smoke detected
                                </div>
                                <div className='cp-density'>
                                    smoke density
                                </div>
                                <div className='cp-color'>
                                    smoke color
                                </div>

                            </div>

                        </div>
                    </section>

                </main>

            </main>

        </div>

    </div>
    
  )
}

export default Dashboard
