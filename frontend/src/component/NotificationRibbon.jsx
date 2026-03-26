import { useState, useEffect } from 'react';
import { X, AlertTriangle, AlertCircle, CheckCircle } from 'lucide-react';
import '../styles/NotificationRibbon.css';
import { fetchWithFallback } from '../utils/apiClient';

export default function NotificationRibbon() {
  const [visibleNotifications, setVisibleNotifications] = useState([]);

  const fetchNotifications = async () => {
    try {
      const token = localStorage.getItem('token');
      if (!token) {
        console.log('No auth token - skipping notifications fetch');
        return;
      }
      
      const response = await fetchWithFallback('/api/vehicles/notifications/unread?limit=5', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.status === 401) {
        console.log('Auth expired - clearing token but continuing');
        localStorage.removeItem('token');
        return;
      }

      if (response.ok) {
        const result = await response.json();
        if (result.success && result.data) {
          // Add new notifications that aren't already visible
          const newNotifications = result.data.filter(
            notif => !visibleNotifications.some(v => v.id === notif.id)
          );
          
          if (newNotifications.length > 0) {
            newNotifications.forEach(notif => {
              addNotification(notif);
            });
          }
        }
      }
    } catch (error) {
      console.log('Notifications fetch failed (non-critical):', error.message);
    }
  };

  const addNotification = (notification) => {
    const id = notification.id;
    const newNotif = {
      id,
      ...notification,
      isVisible: true
    };

    setVisibleNotifications(prev => [...prev, newNotif]);

    // Auto-remove after 8 seconds
    setTimeout(() => {
      removeNotification(id);
    }, 8000);
  };

  const removeNotification = (id) => {
    setVisibleNotifications(prev => prev.filter(n => n.id !== id));
    
    // Mark as read
    markAsRead(id);
  };

  const markAsRead = async (notificationId) => {
    try {
      const token = localStorage.getItem('token');
      if (!token) return;
      
      await fetchWithFallback(`/api/vehicles/notifications/${notificationId}/read`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
    } catch (error) {
      console.log('Mark as read failed (non-critical):', error.message);
    }
  };

  useEffect(() => {
    // Fetch unread notifications
    fetchNotifications();
    
    // Poll for new notifications every 5 seconds
    const interval = setInterval(fetchNotifications, 5000);
    return () => clearInterval(interval);
  }, []);

  const getSeverityIcon = (severity) => {
    switch (severity) {
      case 'critical':
        return <AlertTriangle size={20} />;
      case 'warning':
        return <AlertCircle size={20} />;
      case 'info':
        return <CheckCircle size={20} />;
      default:
        return <AlertCircle size={20} />;
    }
  };

  const getSeverityClass = (severity) => {
    switch (severity) {
      case 'critical':
        return 'critical';
      case 'warning':
        return 'warning';
      case 'info':
        return 'info';
      default:
        return 'info';
    }
  };

  return (
    <div className="notification-ribbon-container">
      {visibleNotifications.map(notification => (
        <div
          key={notification.id}
          className={`notification-ribbon ${getSeverityClass(notification.severity)}`}
        >
          <div className="notification-icon">
            {getSeverityIcon(notification.severity)}
          </div>
          
          <div className="notification-content">
            <div className="notification-title">
              {notification.title}
              {notification.license_plate && (
                <span className="license-plate">{notification.license_plate}</span>
              )}
            </div>
            <div className="notification-message">
              {notification.message}
            </div>
          </div>

          <button
            className="notification-close"
            onClick={() => removeNotification(notification.id)}
          >
            <X size={18} />
          </button>
        </div>
      ))}
    </div>
  );
}
