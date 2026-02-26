# Changelog

## [1.0.0.1] - 2026-02-26

### Removed
- Removed DataTimeoutModal component that displayed when no sensor data was being received
- Removed DataTimeoutModal import from Dashboard.jsx
- Removed DataTimeoutModal styling (DataTimeoutModal.css)

### Changes
- Simplified Dashboard by removing the data timeout notification modal
- Users will no longer see the "No Data Being Received" modal alert

### Files Modified
- `frontend/src/Dashboard.jsx` - Removed import and component usage
- `frontend/src/component/DataTimeoutModal.jsx` - Component file (deprecated)
- `frontend/src/styles/DataTimeoutModal.css` - Styling file (deprecated)
