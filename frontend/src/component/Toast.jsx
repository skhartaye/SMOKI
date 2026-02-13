import { useState, useEffect } from 'react';
import { CheckCircle, AlertCircle, XCircle, Info } from 'lucide-react';
import '../styles/Toast.css';

export default function Toast() {
  const [toasts, setToasts] = useState([]);

  useEffect(() => {
    // Listen for custom toast events
    const handleToast = (event) => {
      const { type, message, duration = 3000 } = event.detail;
      const id = Date.now();
      
      setToasts(prev => [...prev, { id, type, message }]);
      
      setTimeout(() => {
        setToasts(prev => prev.filter(t => t.id !== id));
      }, duration);
    };

    window.addEventListener('showToast', handleToast);
    return () => window.removeEventListener('showToast', handleToast);
  }, []);

  const getIcon = (type) => {
    switch (type) {
      case 'success':
        return <CheckCircle size={20} />;
      case 'error':
        return <XCircle size={20} />;
      case 'warning':
        return <AlertCircle size={20} />;
      case 'info':
      default:
        return <Info size={20} />;
    }
  };

  const removeToast = (id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  };

  return (
    <div className="toast-container">
      {toasts.map(toast => (
        <div key={toast.id} className={`toast toast-${toast.type}`}>
          <div className="toast-icon">
            {getIcon(toast.type)}
          </div>
          <div className="toast-message">
            {toast.message}
          </div>
          <button 
            className="toast-close"
            onClick={() => removeToast(toast.id)}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}

// Helper function to show toast
export const showToast = (type, message, duration = 3000) => {
  window.dispatchEvent(new CustomEvent('showToast', {
    detail: { type, message, duration }
  }));
};
