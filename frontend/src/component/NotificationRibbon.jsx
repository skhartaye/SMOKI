import { useState, useEffect } from 'react';
import { X, AlertTriangle, AlertCircle, CheckCircle, Check, XCircle, FileText } from 'lucide-react';
import '../styles/NotificationRibbon.css';
import { fetchWithFallback } from '../utils/apiClient';

export default function NotificationRibbon() {
  const [visibleNotifications, setVisibleNotifications] = useState([]);
  const [processingActions, setProcessingActions] = useState(new Set());

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

    // Auto-remove after 15 seconds for approval/OCR failure notifications, 8 seconds for others
    const autoRemoveTime = (notification.notification_type === 'violation_approval' || notification.notification_type === 'ocr_failure') ? 15000 : 8000;
    setTimeout(() => {
      removeNotification(id);
    }, autoRemoveTime);
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

  const handleViolationAction = async (notificationId, violationId, action) => {
    if (processingActions.has(notificationId)) return;
    
    setProcessingActions(prev => new Set([...prev, notificationId]));
    
    try {
      const token = localStorage.getItem('token');
      if (!token) {
        console.log('No auth token for violation action');
        return;
      }
      
      if (action === 'verify') {
        // Step 1: Generate verification report
        console.log('Generating verification report for violation:', violationId);
        
        const reportResponse = await fetchWithFallback('/api/stream/generate-report', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            report_type: 'violation_verification',
            violation_id: violationId
          })
        });

        if (reportResponse.ok) {
          const reportResult = await reportResponse.json();
          console.log('Verification report generated:', reportResult);
          
          // Open the report in a new tab immediately
          if (reportResult.report_id) {
            const reportUrl = `https://smoki-backend-rpi.onrender.com/api/stream/reports/${reportResult.report_id}`;
            window.open(reportUrl, '_blank');
            console.log('Verification report opened in new tab:', reportUrl);
          }
          
          // Update notification to show verification options
          setVisibleNotifications(prev => prev.map(notif => 
            notif.id === notificationId 
              ? { ...notif, showVerificationActions: true, reportId: reportResult.report_id }
              : notif
          ));
          
        } else {
          console.error('Failed to generate verification report:', reportResponse.status);
          const errorText = await reportResponse.text();
          console.error('Error details:', errorText);
          alert('Failed to generate verification report. Please try again.');
        }
      } else {
        // Step 2: Actually approve or reject after verification
        const endpoint = action === 'approve' 
          ? `/api/vehicles/violations/${violationId}/approve`
          : `/api/vehicles/violations/${violationId}/reject`;
        
        const response = await fetchWithFallback(endpoint, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`
          }
        });

        if (response.ok) {
          const result = await response.json();
          console.log(`Violation ${action}d:`, result);
          
          // Remove the notification immediately after successful action
          removeNotification(notificationId);
          
          // Show success message
          const actionText = action === 'approve' ? 'approved' : 'rejected';
          console.log(`Violation ${actionText} successfully`);
        } else {
          console.error(`Failed to ${action} violation:`, response.status);
        }
      }
    } catch (error) {
      console.error(`Error ${action}ing violation:`, error);
    } finally {
      setProcessingActions(prev => {
        const newSet = new Set(prev);
        newSet.delete(notificationId);
        return newSet;
      });
    }
  };

  const handleViewReport = (reportId) => {
    // Open the verification report in a new tab
    const reportUrl = `https://smoki-backend-rpi.onrender.com/api/stream/reports/${reportId}`;
    window.open(reportUrl, '_blank');
  };

  const handleOCRVerification = async (notificationId) => {
    if (processingActions.has(notificationId)) return;
    
    setProcessingActions(prev => new Set([...prev, notificationId]));
    
    try {
      // Generate a report using the enhanced report generator with evidence gallery
      console.log('Generating OCR failure verification report for notification:', notificationId);
      
      const reportResponse = await fetchWithFallback('https://smoki-backend-rpi.onrender.com/api/stream/generate-report', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          report_type: 'general'
        })
      });

      if (reportResponse.ok) {
        const reportResult = await reportResponse.json();
        console.log('OCR verification report generated:', reportResult);
        
        if (reportResult.success && reportResult.report_id) {
          // Open the enhanced report with evidence gallery using the stream API
          const reportUrl = `https://smoki-backend-rpi.onrender.com/api/stream/reports/${reportResult.report_id}`;
          window.open(reportUrl, '_blank');
          
          // Mark notification as read and remove it
          removeNotification(notificationId);
          
          console.log('Enhanced OCR verification report with evidence gallery opened for manual review.');
        } else {
          throw new Error(reportResult.message || 'Report generation failed');
        }
      } else {
        const errorText = await reportResponse.text();
        console.error('Failed to generate OCR verification report:', reportResponse.status, errorText);
        throw new Error(`Report generation failed: ${reportResponse.status}`);
      }
    } catch (error) {
      console.error('Error handling OCR verification:', error);
      // Show error message to user
      alert('Failed to generate verification report. Please try again.');
    } finally {
      setProcessingActions(prev => {
        const newSet = new Set(prev);
        newSet.delete(notificationId);
        return newSet;
      });
    }
  };

  // Extract violation ID from notification
  const getViolationId = (notification) => {
    // Use the violation_id field from the notification
    return notification.violation_id;
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
          className={`notification-ribbon ${getSeverityClass(notification.severity)} ${
            notification.notification_type === 'violation_approval' ? 'approval-notification' : ''
          } ${
            notification.notification_type === 'ocr_failure' ? 'ocr-failure-notification' : ''
          }`}
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
            
            {/* Show approval buttons for violation approval notifications */}
            {notification.notification_type === 'violation_approval' && (
              <div className="notification-actions">
                {!notification.showVerificationActions ? (
                  // Step 1: Initial verification button
                  <button
                    className="verify-btn"
                    onClick={() => handleViolationAction(
                      notification.id, 
                      getViolationId(notification), 
                      'verify'
                    )}
                    disabled={processingActions.has(notification.id)}
                  >
                    <FileText size={16} />
                    {processingActions.has(notification.id) ? 'Generating Report...' : 'Verify Details'}
                  </button>
                ) : (
                  // Step 2: After verification, show approve/reject with report view
                  <>
                    <button
                      className="view-report-btn"
                      onClick={() => handleViewReport(notification.reportId)}
                    >
                      <FileText size={16} />
                      View Report
                    </button>
                    <button
                      className="approve-btn"
                      onClick={() => handleViolationAction(
                        notification.id, 
                        getViolationId(notification), 
                        'approve'
                      )}
                      disabled={processingActions.has(notification.id)}
                    >
                      <Check size={16} />
                      {processingActions.has(notification.id) ? 'Processing...' : 'Approve'}
                    </button>
                    <button
                      className="reject-btn"
                      onClick={() => handleViolationAction(
                        notification.id, 
                        getViolationId(notification), 
                        'reject'
                      )}
                      disabled={processingActions.has(notification.id)}
                    >
                      <XCircle size={16} />
                      Reject
                    </button>
                  </>
                )}
              </div>
            )}

            {/* Show verify button for OCR failure notifications */}
            {notification.notification_type === 'ocr_failure' && (
              <div className="notification-actions">
                <button
                  className="verify-btn"
                  onClick={() => handleOCRVerification(notification.id)}
                  disabled={processingActions.has(notification.id)}
                >
                  <FileText size={16} />
                  {processingActions.has(notification.id) ? 'Generating Report...' : 'Verify'}
                </button>
              </div>
            )}
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
