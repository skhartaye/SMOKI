import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { User, Lock, LogIn, Zap } from 'lucide-react'
import './styles/App.css'

function App() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const navigate = useNavigate()

  const handleLogin = async (e) => {
    e.preventDefault()
    setIsLoading(true)
    setError('')

    try {
      const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
      const response = await fetch(`${API_URL}/api/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username, password }),
      });

      const data = await response.json();

      if (response.ok) {
        // Store token and user info
        localStorage.setItem('token', data.access_token);
        localStorage.setItem('role', data.role);
        localStorage.setItem('username', data.username);
        localStorage.setItem('isLoggedIn', 'true');
        
        // Set flag to show tutorial on Dashboard
        sessionStorage.setItem('justLoggedIn', 'true');
        
        // Navigate to dashboard
        setTimeout(() => {
          navigate('/dashboard');
        }, 800);
      } else {
        setError(data.detail || 'Invalid username or password');
        setIsLoading(false);
      }
    } catch (error) {
      console.error('Login error:', error);
      setError('Connection error. Please try again.');
      setIsLoading(false);
    }
  }

  return (
    <div className="login-page">
      {isLoading && (
        <div className="login-loading-overlay">
          <div className="loading-content">
            <div className="loading-spinner-large"></div>
            <p>Signing you in...</p>
          </div>
        </div>
      )}
      <div className="login-container">
        <div className="login-header">
          <div className="logo-icon">
            <Zap />
          </div>
          <h1>SMOKi</h1>
          <p>Smoke Emission Monitoring System</p>
        </div>

        <form onSubmit={handleLogin} className="login-form">
          <div className="input-group">
            <div className="input-icon">
              <User />
            </div>
            <input
              type="text"
              placeholder="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              disabled={isLoading}
            />
          </div>

          <div className="input-group">
            <div className="input-icon">
              <Lock />
            </div>
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              disabled={isLoading}
            />
          </div>

          {error && (
            <div className="error-message">
              <span>⚠️</span>
              <span>{error}</span>
            </div>
          )}

          <button type="submit" className="login-button" disabled={isLoading}>
            {isLoading ? (
              <>
                <span className="spinner"></span>
                <span>Signing in...</span>
              </>
            ) : (
              <>
                <LogIn />
                <span>Sign In</span>
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  )
}

export default App
