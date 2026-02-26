import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import App from './App.jsx'
import Dashboard from './Dashboard.jsx'
import ProtectedRoute from './component/ProtectedRoute.jsx'
import { SensorStatusProvider } from './context/SensorStatusContext.jsx'
import './styles/main.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <SensorStatusProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<App />} />
          <Route 
            path="/dashboard" 
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            } 
          />
        </Routes>
      </BrowserRouter>
    </SensorStatusProvider>
  </React.StrictMode>
)
