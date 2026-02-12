import { useState, useEffect } from 'react';
import { X, AlertTriangle, AlertCircle, CheckCircle } from 'lucide-react';
import '../styles/NotificationRibbon.css';

export default function NotificationRibbon() {
  const [notifications, setNotifications] = useState([]);
  const [visibleNotifications, setVisibleNotifications] = useState([]);

  useEffect(() => {
    // Fetch unread notifications
    fetchNotifications();
    
    // Poll for new notifications every 5 seconds
    const interval = setInterval(fetchNotifications, 5000);
    return () => clearInterval(interval);
  }, []);

  const fetchNotifications = async () => {
    try {
      const token = localStorage.getItem('token');
      const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
      
      const response = await fetch(`${API_URL}/api/vehicles/notifications/unread?limit=5`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

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
      console.error('Error fetching notifications:', error);
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
      const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
      
      await fetch(`${API_URL}/api/vehicles/notifications/${notificationId}/read`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
    } catch (error) {
      console.error('Error marking notification as read:', error);
    }
  };

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
