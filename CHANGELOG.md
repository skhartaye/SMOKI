# Changelog

## [1.0.0.5-beta] - 2026-02-27

### Added
- Sensor type filter icon (signal/frequency icon) for better visual consistency
- Tutorial modal now shows on every login (not on page reload)
- Compact timestamp format in records table (MM-DD HH:MM A/P format)

### Changed
- Updated sensor type filter icons on Records and Graphs pages to match design system
- Changed filter icon color to #5b6b8d for consistency with other UI elements
- Records table timestamp display now uses compact format to improve table layout
- Tutorial modal uses sessionStorage flag to detect login vs page reload

### Fixed
- Records table layout now properly displays all columns without wrapping headers
- Timestamp column stays on single line in records table
- Tutorial modal behavior: shows on login, doesn't show on page reload

### Files Modified
- `frontend/src/Dashboard.jsx` - Updated sensor filter icons, added login detection for tutorial, compact timestamp format
- `frontend/src/component/TutorialModal.jsx` - Added triggerOnLogin prop for login detection
- `frontend/src/App.jsx` - Added sessionStorage flag on successful login
- `frontend/src/styles/Dashboard.css` - Updated table styling for better layout

## [1.0.0.4] - 2026-02-26

### Added
- Smoke detection metadata logging to PostgreSQL via FastAPI
- RPi camera script now sends detection data (timestamp, confidence, smoke type, bounding box) to backend
- New endpoints: `POST /api/detections/smoke` and `GET /api/detections/smoke`
- Database functions for smoke detection storage and retrieval
- Report Violator section on dashboard with email reporting functionality
- Report button for each violator that pre-fills email with violation details

### Changed
- Reordered dashboard sections: Violators Ranking now appears before Report Violator
- Improved mobile visibility of sensor status ribbon (z-index and positioning)
- Sensors page video box now matches dashboard size (1.5fr 1fr grid layout)

### Fixed
- Sensor status ribbon timer no longer jumps back to 0 seconds (uses useRef for stable timing)
- Mobile notification ribbon now visible below header

### Files Modified
- `frontend/src/Dashboard.jsx` - Added Report Violator section with email functionality, reordered sections
- `frontend/src/styles/Dashboard.css` - Added report button styling, improved mobile ribbon visibility
- `frontend/src/styles/SensorStatusRibbon.css` - Fixed mobile visibility and z-index
- `backend/main.py` - Added smoke detection endpoints
- `postgre/database.py` - Added smoke detection database functions
- `esp32/rpi5_camera_stream_optimized.py` - Added metadata sending to backend

## [1.0.0.3] - 2026-02-26

### Fixed
- Fixed sensor status ribbon timer jumping from minutes back to 0 seconds
- Improved time display formatting for offline sensor notifications (60s = 1m, 60m = 1h, etc.)

### Improved
- Removed safe/danger reference lines from all graphs for cleaner visualization
- Enhanced filter UX on graphs and records pages:
  - Sensor type filters now apply immediately when clicked (no submit button needed)
  - Date filters now apply immediately on selection
  - Changed "Submit" button to "Clear Filters" for better clarity
  - Removed redundant "Clear all filters" checkbox from dropdown
- Sensor status ribbon now displays time in human-readable format (e.g., "1m 30s", "2h 15m")

### Files Modified
- `frontend/src/component/SensorStatusRibbon.jsx` - Fixed timer logic and improved time formatting
- `frontend/src/Dashboard.jsx` - Removed reference lines, improved filter handlers, updated button labels

## [1.0.0.2-alpha] - 2026-02-26

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
