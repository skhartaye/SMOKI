import './styles/Dashboard.css';
import './styles/AQI.css';
import './styles/ActionButtons.css';
import './styles/InfoPage.css';
import { useNavigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Brush, ReferenceLine } from 'recharts';
import { Thermometer, Droplet, Wind, Flame, Circle, Home, FileText, TrendingUp, Zap, Moon, Sun, LogOut, Menu, Activity } from 'lucide-react';
import NotificationRibbon from './component/NotificationRibbon';
import SensorStatusRibbon from './component/SensorStatusRibbon';
import Toast from './component/Toast';
import { showToast } from './utils/toastUtils';
import { EditIcon, DeleteIcon, PlusIcon } from './component/IOSIcons';
import ConfirmModal from './component/ConfirmModal';
import SensorDetailModal from './component/SensorDetailModal';
import TriangleLoader from './component/TriangleLoader';
import TutorialModal from './component/TutorialModal';
import WebRTCViewer from './component/WebRTCViewer';
import { useSensorStatus } from './context/SensorStatusContext';
import { fetchWithFallback } from './utils/apiClient';
import { calculateOverallAQI, getAQICategory, getPollutantDisplayName, getPollutantUnit } from './utils/aqiCalculator';

const InfoIcon = () => (
  <svg height="16" strokeLinejoin="round" viewBox="0 0 16 16" width="16" style={{color: 'currentcolor'}}><path d="M14 8C14 11.3137 11.3137 14 8 14C4.68629 14 2 11.3137 2 8C2 4.68629 4.68629 2 8 2C11.3137 2 14 4.68629 14 8Z" fill="currentColor" fillOpacity="0.08"></path><path fillRule="evenodd" clipRule="evenodd" d="M8 6C8.55228 6 9 5.55228 9 5C9 4.44772 8.55228 4 8 4C7.44771 4 7 4.44772 7 5C7 5.55228 7.44771 6 8 6ZM7 7H6.25V8.5H7H7.24999V10.5V11.25H8.74999V10.5V8C8.74999 7.44772 8.30227 7 7.74999 7H7Z" fill="currentColor"></path></svg>
);

const UserIcon = ({ size = 24 }) => (
  <svg data-testid="geist-icon" height={size} strokeLinejoin="round" viewBox="0 0 16 16" width={size} style={{color: 'currentcolor', display: 'block'}}><path fillRule="evenodd" clipRule="evenodd" d="M7.75 0C5.95507 0 4.5 1.45507 4.5 3.25V3.75C4.5 5.54493 5.95507 7 7.75 7H8.25C10.0449 7 11.5 5.54493 11.5 3.75V3.25C11.5 1.45507 10.0449 0 8.25 0H7.75ZM6 3.25C6 2.2835 6.7835 1.5 7.75 1.5H8.25C9.2165 1.5 10 2.2835 10 3.25V3.75C10 4.7165 9.2165 5.5 8.25 5.5H7.75C6.7835 5.5 6 4.7165 6 3.75V3.25ZM2.5 14.5V13.1709C3.31958 11.5377 4.99308 10.5 6.82945 10.5H9.17055C11.0069 10.5 12.6804 11.5377 13.5 13.1709V14.5H2.5ZM6.82945 9C4.35483 9 2.10604 10.4388 1.06903 12.6857L1 12.8353V13V15.25V16H1.75H14.25H15V15.25V13V12.8353L14.931 12.6857C13.894 10.4388 11.6452 9 9.17055 9H6.82945Z" fill="#666"></path></svg>
);

function Dashboard() {
  const [activePage, setActivePage] = useState("dashboard");
  const [sensorData, setSensorData] = useState(null);
  const [previousSensorData, setPreviousSensorData] = useState(null);
  const [aqiData, setAqiData] = useState(null);
  const [records, setRecords] = useState([]);
  const [graphData, setGraphData] = useState([]);
  const [correlationData, setCorrelationData] = useState([]);
  const [filterSensorTypes, setFilterSensorTypes] = useState({
    temperature: true,
    humidity: true,
    vocs: true,
    no2: true,
    co: true,
    pm25: true,
    pm10: true,
    pressure: true
  });
  const [appliedSensorTypes, setAppliedSensorTypes] = useState({
    temperature: true,
    humidity: true,
    vocs: true,
    no2: true,
    co: true,
    pm25: true,
    pm10: true,
    pressure: true
  });
  const [filterDate, setFilterDate] = useState("all");
  const [appliedDate, setAppliedDate] = useState("all");
  const [clearFilters, setClearFilters] = useState(false);
  const [sensorDropdownOpen, setSensorDropdownOpen] = useState(false);
  
  // Graph filters
  const [graphFilterSensorTypes, setGraphFilterSensorTypes] = useState({
    temperature: true,
    humidity: true,
    vocs: true,
    no2: true,
    co: true,
    pm25: true,
    pm10: true,
    pressure: true,
    aqi: true
  });
  const [appliedGraphSensorTypes, setAppliedGraphSensorTypes] = useState({
    temperature: true,
    humidity: true,
    vocs: true,
    no2: true,
    co: true,
    pm25: true,
    pm10: true,
    pressure: true,
    aqi: true
  });
  const [graphFilterDate, setGraphFilterDate] = useState("all");
  const [appliedGraphDate, setAppliedGraphDate] = useState("all");
  const [clearGraphFilters, setClearGraphFilters] = useState(false);
  const [graphSensorDropdownOpen, setGraphSensorDropdownOpen] = useState(false);
  const [darkMode, setDarkMode] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [selectedSensor, setSelectedSensor] = useState(null); // For sensor detail view
  const [sidebarHovered, setSidebarHovered] = useState(false);
  const [showGraphLoading, setShowGraphLoading] = useState(false);
  const [userRole] = useState(localStorage.getItem('role') || 'Admin');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingRecord, setEditingRecord] = useState(null);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 768);
  const [formData, setFormData] = useState({
    temperature: '',
    humidity: '',
    vocs: '',
    nitrogen_dioxide: '',
    carbon_monoxide: '',
    pm25: '',
    pm10: ''
  });
  const [allDetections, setAllDetections] = useState([]);
  const [vehicleRanking, setVehicleRanking] = useState([]);
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [recordToDelete, setRecordToDelete] = useState(null);
  const [showSensorDetailModal, setShowSensorDetailModal] = useState(false);
  const [selectedSensorType, setSelectedSensorType] = useState(null);
  const [triggerTutorialOnLogin, setTriggerTutorialOnLogin] = useState(false);
  const [reportingSmoke, setReportingSmoke] = useState(null);
  
  const navigate = useNavigate();
  const { sensorConnected, lastSensorUpdate, updateLastSensorTime } = useSensorStatus();

  // Report smoke event function
  const reportSmokeEvent = async (detection) => {
    try {
      setReportingSmoke(detection.id);
      
      const token = localStorage.getItem('token');
      const headers = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const reportData = {
        detection_id: detection.id,
        timestamp: detection.timestamp,
        location: detection.location || 'Main Camera',
        smoke_level: detection.smoke_level || 'Unknown',
        confidence: detection.confidence,
        reported_by: localStorage.getItem('username') || 'User',
        report_time: new Date().toISOString()
      };

      const response = await fetchWithFallback('/api/smoke/report', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...headers
        },
        body: JSON.stringify(reportData)
      });

      if (response.status === 200 || response.status === 201) {
        showToast('Smoke event reported successfully', 'success');
      } else {
        showToast('Failed to report smoke event', 'error');
      }
    } catch (error) {
      console.error('Error reporting smoke event:', error);
      showToast('Error reporting smoke event', 'error');
    } finally {
      setReportingSmoke(null);
    }
  };

  // Fetch latest sensor data for sensors page
  const fetchLatestSensorData = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetchWithFallback('/api/sensors/latest', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.status === 401) {
        // Token expired or invalid
        localStorage.clear();
        navigate('/');
        return;
      }
      
      const result = await response.json();
      if (result.success && result.data) {
        setSensorData(prevData => {
          // Set previous data to the current data before updating
          setPreviousSensorData(prevData);
          return result.data;
        });
        
        // Calculate AQI if we have the required pollutants
        if (result.data.nitrogen_dioxide !== null || result.data.carbon_monoxide !== null || 
            result.data.pm25 !== null || result.data.pm10 !== null) {
          const pollutants = {
            no2: result.data.nitrogen_dioxide,
            co: result.data.carbon_monoxide,
            pm25: result.data.pm25,
            pm10: result.data.pm10
          };
          const aqiResult = calculateOverallAQI(pollutants);
          setAqiData(aqiResult);
        } else {
          setAqiData(null);
        }
        
        updateLastSensorTime(); // Update the last sensor update time
      }
    } catch (error) {
      console.error('Error fetching sensor data:', error);
    }
  };

  const fetchRecords = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetchWithFallback('/api/sensors/data?limit=50', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.status === 401) {
        localStorage.clear();
        navigate('/');
        return;
      }
      
      const result = await response.json();
      if (result.success) {
        setRecords(result.data);
        updateLastSensorTime(); // Update the last sensor update time
      }
    } catch (error) {
      console.error('Error fetching records:', error);
    }
  };

  const fetchGraphData = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetchWithFallback('/api/sensors/data?limit=500', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.status === 401) {
        localStorage.clear();
        navigate('/');
        return;
      }
      
      const result = await response.json();
      if (result.success) {
        // Format data for graphs (reverse to show oldest first)
        const formatted = result.data.reverse().map(item => {
          // Calculate AQI for each data point
          const pollutants = {
            no2: item.nitrogen_dioxide,
            co: item.carbon_monoxide,
            pm25: item.pm25,
            pm10: item.pm10
          };
          const aqiResult = calculateOverallAQI(pollutants);
          
          return {
            time: new Date(item.timestamp).toLocaleTimeString(),
            fullTimestamp: new Date(item.timestamp).toLocaleString(),
            temperature: item.temperature || 0,
            humidity: item.humidity || 0,
            pressure: item.pressure || 0,
            vocs: item.vocs || 0,
            no2: item.nitrogen_dioxide || 0,
            co: item.carbon_monoxide || 0,
            pm25: item.pm25 || 0,
            pm10: item.pm10 || 0,
            aqi: aqiResult.overallAQI || 0
          };
        });
        setGraphData(formatted);
        updateLastSensorTime(); // Update the last sensor update time
      }
    } catch (error) {
      console.error('Error fetching graph data:', error);
    }
  };

  const fetchCorrelationData = async () => {
    try {
      // Add cache-busting parameter to force fresh data
      const cacheBuster = Date.now();
      const response = await fetchWithFallback(`/api/correlation/pm-smoke?limit=50&_cb=${cacheBuster}`);
      
      const result = await response.json();
      if (result.success) {
        // Format data for correlation graph (keep chronological order)
        const formatted = result.data.map(item => {
          // Parse UTC timestamp correctly to avoid timezone conversion
          const date = new Date(item.timestamp);
          
          // For historical smoke events (March 27), force correct date display
          if (item.is_real_event && item.smoke_events === 1) {
            // These are March 27, 2026 smoke events - display as March 27
            const utcDate = new Date(item.timestamp);
            const march27Date = new Date('2026-03-27T' + utcDate.toISOString().split('T')[1]);
            
            return {
              time: march27Date.toLocaleTimeString(),
              date: '3/27/2026',
              fullTimestamp: `3/27/2026 ${march27Date.toLocaleTimeString()}`,
              dateTime: `3/27/2026 ${march27Date.toLocaleTimeString()}`,
              pm25: item.pm25 || 0,
              pm10: item.pm10 || 0,
              smoke_events: item.smoke_events || 0,
              combined_pm: item.combined_pm || 0,
              is_real_event: item.is_real_event || false
            };
          } else {
            // Regular date formatting for recent data
            return {
              time: date.toLocaleTimeString(),
              date: date.toLocaleDateString(),
              fullTimestamp: date.toLocaleString(),
              dateTime: `${date.toLocaleDateString()} ${date.toLocaleTimeString()}`,
              pm25: item.pm25 || 0,
              pm10: item.pm10 || 0,
              smoke_events: item.smoke_events || 0,
              combined_pm: item.combined_pm || 0,
              is_real_event: item.is_real_event || false
            };
          }
        });
        
        // Show all data points to display both historical events and trends
        setCorrelationData(formatted);
        
        console.log(`Correlation loaded: ${result.historical_smoke_events || 0} historical smoke events, ${result.recent_trend_points || 0} recent trend points`);
        console.log('First few data points:', formatted.slice(0, 3));
        console.log('Last few data points:', formatted.slice(-3));
      }
    } catch (error) {
      console.error('Error fetching correlation data:', error);
      // No fallback data - show empty state
      setCorrelationData([]);
    }
  };

  const calculateChange = (current, previous) => {
    // Always return a number - return 0 if no valid data
    if (typeof current !== 'number' || typeof previous !== 'number') return 0;
    if (previous === 0) return 0;
    const change = ((current - previous) / previous) * 100;
    return change;
  };

  // Handle window resize to detect mobile
  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth <= 768);
    };
    
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Detect login and trigger tutorial on Dashboard mount
  useEffect(() => {
    // Check if user just logged in (flag set by login page)
    const justLoggedIn = sessionStorage.getItem('justLoggedIn');
    if (justLoggedIn) {
      setTriggerTutorialOnLogin(true);
      sessionStorage.removeItem('justLoggedIn');
      // Reset the trigger after a short delay to allow the modal to show
      setTimeout(() => {
        setTriggerTutorialOnLogin(false);
      }, 100);
    }
  }, []);

  // Close dropdowns when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (!event.target.closest('.custom-dropdown')) {
        setSensorDropdownOpen(false);
        setGraphSensorDropdownOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Handle sidebar hover to show loading animation on graphs page
  useEffect(() => {
    let timeoutId;
    if (activePage === "graphs") {
      setShowGraphLoading(true);
      // Hide loading after sidebar animation completes
      timeoutId = setTimeout(() => {
        setShowGraphLoading(false);
      }, 1000);
    }
    return () => {
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [activePage]);

  // Fetch latest sensor data for sensors page
  useEffect(() => {
    if (activePage === "sensors") {
      fetchLatestSensorData();
      const interval = setInterval(fetchLatestSensorData, 5000); // Update every 5 seconds
      return () => clearInterval(interval);
    }
  }, [activePage]);

  // Fetch records for records page
  useEffect(() => {
    if (activePage === "records") {
      fetchRecords();
      const interval = setInterval(fetchRecords, 10000); // Update every 10 seconds
      return () => clearInterval(interval);
    }
  }, [activePage]);

  // Fetch graph data for graphs page
  useEffect(() => {
    if (activePage === "graphs") {
      fetchGraphData();
      fetchCorrelationData();
      const interval = setInterval(() => {
        fetchGraphData();
        fetchCorrelationData();
      }, 30000); // Update every 30 seconds
      return () => clearInterval(interval);
    }
  }, [activePage]);

  const fetchAllDetections = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      
      // Try to fetch from new detections endpoint (public)
      try {
        const response = await fetchWithFallback('/api/vehicles/detections/recent?limit=50');
        
        if (response.status === 200) {
          const result = await response.json();
          if (result.success && result.data && result.data.length > 0) {
            // Transform detection data to match frontend expectations
            const transformedDetections = [];
            
            result.data.forEach((detection) => {
              const timestamp = new Date(detection.timestamp);
              const metadata = detection.metadata || {};
              const detections = metadata.detections || [];
              
              // Process each individual detection in the metadata
              detections.forEach((det, index) => {
                const className = det.class_name || det.class || 'unknown';
                const confidence = det.confidence || det.conf || 0;
                
                let detectionType = 'Unknown';
                let smokeLevel = 'None';
                let licensePlate = 'N/A';
                
                // Determine detection type
                if (className.includes('smoke')) {
                  detectionType = 'Smoke';
                  smokeLevel = det.opacity_level || 'Medium';
                } else if (['passenger', 'puv', 'service', 'services', 'two_wheel'].includes(className)) {
                  detectionType = 'Vehicle';
                  licensePlate = det.plate_text || 'Not detected';
                } else if (className.includes('license') || className.includes('plate')) {
                  detectionType = 'License';
                  licensePlate = det.plate_text || 'Processing...';
                }
                
                transformedDetections.push({
                  id: `${detection.id}_${index}`,
                  timestamp: detection.timestamp,
                  detection_type: detectionType,
                  class_name: className,
                  confidence: (confidence * 100).toFixed(1),
                  license_plate: licensePlate,
                  smoke_level: smokeLevel,
                  location: detection.location || metadata.location || 'Main Camera',
                  camera_id: metadata.camera_id || 'unknown'
                });
              });
            });
            
            // Sort by timestamp (newest first)
            transformedDetections.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
            
            console.log(`[DETECTIONS] Loaded ${transformedDetections.length} detection records from API`);
            setAllDetections(transformedDetections);
            return;
          }
        }
      } catch (error) {
        console.log('New detections endpoint not available, trying legacy endpoints...');
      }
      
      // Fallback to legacy vehicle detections endpoint (public)
      try {
        const response = await fetchWithFallback('/api/vehicles/violations/recent?limit=50');
        
        if (response.status === 200) {
          const result = await response.json();
          if (result.success && result.data && result.data.length > 0) {
            setAllDetections(result.data);
            return;
          }
        }
      } catch (error) {
        console.log('Legacy detections endpoint not available, trying stream data...');
      }
      
      // Enhanced Fallback: Process live detection data
      try {
        const streamResponse = await fetchWithFallback('/api/stream/status');
        if (streamResponse.status === 200) {
          const streamData = await streamResponse.json();
          
          console.log('[DEBUG] Full stream response:', JSON.stringify(streamData, null, 2));
          console.log('[DEBUG] latest_detections field:', streamData.latest_detections);
          console.log('[DEBUG] detection_summary field:', streamData.detection_summary);
          
          // Process detection metadata
          if (streamData.latest_detections && Array.isArray(streamData.latest_detections) && streamData.latest_detections.length > 0) {
            const detections = streamData.latest_detections.filter(det => 
              det && 
              typeof det === 'object' && 
              (det.class || det.class_name) && 
              (det.conf !== undefined || det.confidence !== undefined)
            );
            
            console.log('[DEBUG] Filtered valid detections:', detections);
            
            if (detections.length === 0) {
              console.log('No valid detections found in stream data');
              setAllDetections([]);
              return;
            }
            
            // Only process if we have real detection data with valid classes
            const detectionRecords = detections.map((detection, index) => {
              try {
                console.log(`[DEBUG] Processing detection ${index}:`, detection);
                
                // Handle the exact field names from RPi: 'class' and 'conf'
                let className = detection.class || detection.class_name || '';
                let confidence = detection.conf || detection.confidence || 0;
                
                // Strict validation - only allow known valid class names
                const validClasses = [
                  'passenger', 'puv', 'services', 'two_wheel',  // vehicles
                  'smoke_black', 'smoke_white',                 // smoke
                  'license_plate'                               // plates
                ];
                
                // Skip if no valid class name or not in our valid list
                if (!className || 
                    className === 'unknown' || 
                    className === '' || 
                    typeof className !== 'string' ||
                    !validClasses.includes(className.toLowerCase())) {
                  console.log(`[DEBUG] Skipping invalid detection - className: "${className}"`);
                  return null;
                }
                
                let detectionType = 'Unknown';
                let plateNumber = 'N/A';
                let smokeLevel = 'None';
                
                console.log(`[DEBUG] Extracted - className: "${className}", confidence: ${confidence}`);
                
                // Ensure confidence is a number and above minimum threshold
                if (typeof confidence !== 'number' || isNaN(confidence) || confidence <= 0) {
                  console.log(`[DEBUG] Skipping detection with invalid confidence: ${confidence}`);
                  return null;
                }
                
                // Normalize confidence to 0-1 range if it's in 0-100 range
                if (confidence > 1) {
                  confidence = confidence / 100;
                }
                
                // Skip detections with very low confidence (less than 10%)
                if (confidence < 0.1) {
                  console.log(`[DEBUG] Skipping low confidence detection: ${confidence}`);
                  return null;
                }
                
                console.log(`[DEBUG] After processing - className: "${className}", confidence: ${confidence}`);
                
                // Use actual detection timestamp or current time
                const detectionTime = detection.timestamp ? new Date(detection.timestamp) : new Date();
                
                // Vehicle detection logic - exact class names from RPi
                const vehicleClasses = ['passenger', 'puv', 'services', 'two_wheel'];
                if (vehicleClasses.includes(className)) {
                  detectionType = 'Vehicle';
                  // Use actual license plate from detection metadata if available
                  plateNumber = detection.plate_text || 'Not detected';
                } 
                // Smoke detection logic - exact class names from RPi
                else if (className === 'smoke_black' || className === 'smoke_white') {
                  detectionType = 'Smoke';
                  smokeLevel = confidence > 0.7 ? 'High' : confidence > 0.4 ? 'Medium' : 'Low';
                } 
                // License plate detection logic - exact class name from RPi
                else if (className === 'license_plate') {
                  detectionType = 'License';
                }
                // If we reach here with a valid class name, something is wrong - skip it
                else {
                  console.log(`[DEBUG] Unhandled valid class name: "${className}" - skipping`);
                  return null;
                }
                
                console.log(`[DEBUG] Final classification - detectionType: "${detectionType}"`);
                
                const result = {
                  id: `detection_${index}_${detectionTime.getTime()}`,
                  timestamp: detectionTime.toISOString(),
                  detection_type: detectionType,
                  class_name: className,
                  confidence: (confidence * 100).toFixed(1),
                  license_plate: plateNumber,
                  smoke_level: smokeLevel,
                  location: streamData.camera_info?.location || 'Main Camera',
                  camera_id: streamData.camera_info?.camera_id || 'rpi_camera_01'
                };
                
                console.log(`[DEBUG] Final detection record:`, result);
                return result;
              } catch (error) {
                console.error('Error processing detection:', error, detection);
                return null;
              }
            }).filter(record => record !== null);
            
            // Sort by timestamp (newest first)
            detectionRecords.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
            
            console.log(`[DETECTIONS] Generated ${detectionRecords.length} detection records from live data`);
            console.log('[DEBUG] Detection records:', detectionRecords);
            setAllDetections(detectionRecords);
            return;
          } else {
            console.log('[DEBUG] No detections in stream data or empty array');
            console.log('[DEBUG] latest_detections:', streamData.latest_detections);
          }
        }
      } catch (error) {
        console.log('Stream processing failed:', error.message);
        console.log('[DEBUG] Stream error details:', error);
      }
      
      // If no real data is available, set empty array
      console.log('[DEBUG] No real detection data available - setting empty array');
      setAllDetections([]);
      
    } catch (error) {
      console.log('Detections fetch failed:', error.message);
      setAllDetections([]);
    }
  };

  const fetchVehicleRanking = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      
      // First, load locally approved violations from localStorage
      const localViolations = JSON.parse(localStorage.getItem('approved_violations') || '[]');
      
      // Convert local violations to ranking format
      const localRanking = {};
      localViolations.forEach(violation => {
        const plate = violation.license_plate;
        if (!localRanking[plate]) {
          localRanking[plate] = {
            license_plate: plate,
            violation_count: 0,
            total_emissions: 0,
            vehicle_type: violation.vehicle_type || 'unknown',
            last_violation: violation.timestamp,
            violations: []
          };
        }
        localRanking[plate].violation_count++;
        localRanking[plate].total_emissions += (violation.confidence || 0.5) * 100;
        localRanking[plate].violations.push(violation);
        
        // Update last violation if this one is more recent
        if (new Date(violation.timestamp) > new Date(localRanking[plate].last_violation)) {
          localRanking[plate].last_violation = violation.timestamp;
        }
      });
      
      // Convert to array and sort by violation count
      const localRankingArray = Object.values(localRanking)
        .sort((a, b) => b.violation_count - a.violation_count);
      
      // Try the ranking endpoint (public) with cache busting
      try {
        const cacheBuster = Date.now();
        const response = await fetchWithFallback(`/api/vehicles/ranking?_cb=${cacheBuster}`);
        
        if (response.status === 200) {
          const result = await response.json();
          if (result.success && result.data && result.data.length > 0) {
            // Merge API data with local data
            const mergedRanking = [...result.data];
            
            // Add local violations that aren't in API data
            localRankingArray.forEach(localItem => {
              const existingIndex = mergedRanking.findIndex(
                item => item.license_plate === localItem.license_plate
              );
              
              if (existingIndex >= 0) {
                // Merge with existing
                mergedRanking[existingIndex].violation_count += localItem.violation_count;
                mergedRanking[existingIndex].total_emissions += localItem.total_emissions;
              } else {
                // Add new
                mergedRanking.push(localItem);
              }
            });
            
            // Sort merged data
            mergedRanking.sort((a, b) => b.violation_count - a.violation_count);
            
            setVehicleRanking(mergedRanking);
            console.log(`[RANKING] Loaded ${mergedRanking.length} vehicles (${localRankingArray.length} from local storage)`);
            return;
          }
        }
      } catch (error) {
        console.log('Ranking endpoint not available, using local data only');
      }
      
      // Use only local data if API is not available
      if (localRankingArray.length > 0) {
        setVehicleRanking(localRankingArray);
        console.log(`[RANKING] Loaded ${localRankingArray.length} vehicles from local storage`);
      } else {
        console.log(`[RANKING] No ranking data available`);
        setVehicleRanking([]);
      }
      
    } catch (error) {
      console.log('Ranking fetch failed:', error.message);
      setVehicleRanking([]);
    }
  };

  // Fetch detections data when dashboard page is active
  useEffect(() => {
    if (activePage === "dashboard") {
      // Clear any existing data first
      setAllDetections([]);
      setVehicleRanking([]);
      
      fetchAllDetections();
      fetchVehicleRanking();
      const interval = setInterval(() => {
        fetchAllDetections();
        fetchVehicleRanking();
      }, 15000); // Update every 15 seconds
      return () => clearInterval(interval);
    }
  }, [activePage]);

  function handleLogout() {
    localStorage.removeItem('isLoggedIn');
    navigate('/');
  }

  const handleDeleteRecord = async (recordId) => {
    setRecordToDelete(recordId);
    setShowConfirmModal(true);
  };

  const confirmDeleteRecord = async () => {
    if (!recordToDelete) return;

    try {
      const token = localStorage.getItem('token');
      const response = await fetchWithFallback(`/api/sensors/data/${recordToDelete}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.status === 401 || response.status === 403) {
        showToast('error', 'You do not have permission to delete records.');
        setShowConfirmModal(false);
        setRecordToDelete(null);
        return;
      }
      
      if (response.ok) {
        setRecords(records.filter(r => r.id !== recordToDelete));
        showToast('success', 'Record deleted successfully');
        setShowConfirmModal(false);
        setRecordToDelete(null);
      } else {
        showToast('error', 'Failed to delete record');
        setShowConfirmModal(false);
        setRecordToDelete(null);
      }
    } catch (error) {
      console.error('Error deleting record:', error);
      showToast('error', 'Error deleting record');
      setShowConfirmModal(false);
      setRecordToDelete(null);
    }
  };

  const handleCreateRecord = async (e) => {
    e.preventDefault();
    try {
      const token = localStorage.getItem('token');
      
      const data = {
        temperature: formData.temperature ? parseFloat(formData.temperature) : null,
        humidity: formData.humidity ? parseFloat(formData.humidity) : null,
        vocs: formData.vocs ? parseFloat(formData.vocs) : null,
        nitrogen_dioxide: formData.nitrogen_dioxide ? parseFloat(formData.nitrogen_dioxide) : null,
        carbon_monoxide: formData.carbon_monoxide ? parseFloat(formData.carbon_monoxide) : null,
        pm25: formData.pm25 ? parseFloat(formData.pm25) : null,
        pm10: formData.pm10 ? parseFloat(formData.pm10) : null
      };

      const response = await fetchWithFallback('/api/sensors/data', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
      });
      
      if (response.ok) {
        showToast('success', 'Record created successfully');
        setShowCreateModal(false);
        setFormData({
          temperature: '', humidity: '', vocs: '', nitrogen_dioxide: '',
          carbon_monoxide: '', pm25: '', pm10: ''
        });
        fetchRecords();
      } else {
        showToast('error', 'Failed to create record');
      }
    } catch (error) {
      console.error('Error creating record:', error);
      showToast('error', 'Error creating record');
    }
  };

  const handleUpdateRecord = async (e) => {
    e.preventDefault();
    try {
      const token = localStorage.getItem('token');
      
      const data = {
        temperature: formData.temperature ? parseFloat(formData.temperature) : null,
        humidity: formData.humidity ? parseFloat(formData.humidity) : null,
        vocs: formData.vocs ? parseFloat(formData.vocs) : null,
        nitrogen_dioxide: formData.nitrogen_dioxide ? parseFloat(formData.nitrogen_dioxide) : null,
        carbon_monoxide: formData.carbon_monoxide ? parseFloat(formData.carbon_monoxide) : null,
        pm25: formData.pm25 ? parseFloat(formData.pm25) : null,
        pm10: formData.pm10 ? parseFloat(formData.pm10) : null
      };

      const response = await fetchWithFallback(`/api/sensors/data/${editingRecord.id}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
      });
      
      if (response.ok) {
        showToast('success', 'Record updated successfully');
        setShowEditModal(false);
        setEditingRecord(null);
        setFormData({
          temperature: '', humidity: '', vocs: '', nitrogen_dioxide: '',
          carbon_monoxide: '', pm25: '', pm10: ''
        });
        fetchRecords();
      } else {
        showToast('error', 'Failed to update record');
      }
    } catch (error) {
      console.error('Error updating record:', error);
      showToast('error', 'Error updating record');
    }
  };

  const openEditModal = (record) => {
    setEditingRecord(record);
    setFormData({
      temperature: record.temperature || '',
      humidity: record.humidity || '',
      vocs: record.vocs || '',
      nitrogen_dioxide: record.nitrogen_dioxide || '',
      carbon_monoxide: record.carbon_monoxide || '',
      pm25: record.pm25 || '',
      pm10: record.pm10 || ''
    });
    setShowEditModal(true);
  };

  const formatTimestamp = (timestamp) => {
    const date = new Date(timestamp);
    // Format as: YYYY-MM-DD HH:MM:SS AM/PM
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    
    let hours = date.getHours();
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const seconds = String(date.getSeconds()).padStart(2, '0');
    const ampm = hours >= 12 ? 'PM' : 'AM';
    
    hours = hours % 12;
    hours = hours ? hours : 12; // 0 should be 12
    const hoursStr = String(hours).padStart(2, '0');
    
    // Format: YYYY-MM-DD HH:MM:SS AM/PM (with space before AM/PM to prevent Excel auto-conversion)
    const formatted = `${year}-${month}-${day} ${hoursStr}:${minutes}:${seconds} ${ampm}`;
    return formatted;
  };

  const calculateAQI = (record) => {
    // AQI calculation based on Philippine DENR standards
    // Using NO₂ (PPM), CO (PPM), PM2.5 (µg/m³), PM10 (µg/m³)
    
    const pollutants = {
      no2: record.nitrogen_dioxide,
      co: record.carbon_monoxide,
      pm25: record.pm25,
      pm10: record.pm10
    };
    
    // Use our Philippine AQI calculator
    const aqiResult = calculateOverallAQI(pollutants);
    
    if (aqiResult.overallAQI === 0) {
      return { value: 0, category: 'No Data', color: '#9e9e9e', pollutant: 'N/A' };
    }
    
    return { 
      value: aqiResult.overallAQI, 
      category: aqiResult.category.level,
      color: aqiResult.category.color,
      pollutant: aqiResult.dominantPollutant ? getPollutantDisplayName(aqiResult.dominantPollutant) : 'N/A'
    };
  };

  // Helper function to get selected sensor names for display
  const getSelectedSensorNames = (sensorTypes) => {
    const sensorLabels = {
      temperature: 'Temp',
      humidity: 'Humidity',
      vocs: 'VOCs',
      no2: 'NO₂',
      co: 'CO',
      pm25: 'PM2.5',
      pm10: 'PM10',
      pressure: 'Pressure'
    };
    
    const selected = Object.keys(sensorTypes).filter(key => sensorTypes[key]);
    
    if (selected.length === 0) {
      return 'None selected';
    } else if (selected.length === Object.keys(sensorTypes).length) {
      return 'All sensors';
    } else if (selected.length <= 3) {
      return selected.map(key => sensorLabels[key]).join(', ');
    } else {
      return `${selected.length} sensors`;
    }
  };

  const handleClearFilters = () => {
    const defaultSensors = {
      temperature: true,
      humidity: true,
      vocs: true,
      no2: true,
      co: true,
      pm25: true,
      pm10: true,
      pressure: true
    };
    setFilterSensorTypes(defaultSensors);
    setAppliedSensorTypes(defaultSensors);
    setFilterDate("all");
    setAppliedDate("all");
    fetchRecords();
  };

  const handleSubmit = () => {
    setAppliedSensorTypes(filterSensorTypes);
    setAppliedDate(filterDate);
    fetchRecords();
  };

  const toggleSensorType = (sensor) => {
    const updated = {
      ...filterSensorTypes,
      [sensor]: !filterSensorTypes[sensor]
    };
    setFilterSensorTypes(updated);
    setAppliedSensorTypes(updated);
    fetchRecords();
  };

  const toggleGraphSensorType = (sensor) => {
    const updated = {
      ...graphFilterSensorTypes,
      [sensor]: !graphFilterSensorTypes[sensor]
    };
    setGraphFilterSensorTypes(updated);
    setAppliedGraphSensorTypes(updated);
    fetchGraphData();
  };

  const handleClearGraphFilters = () => {
    const defaultSensors = {
      temperature: true,
      humidity: true,
      vocs: true,
      no2: true,
      co: true,
      pm25: true,
      pm10: true,
      pressure: true
    };
    setGraphFilterSensorTypes(defaultSensors);
    setAppliedGraphSensorTypes(defaultSensors);
    setGraphFilterDate("all");
    setAppliedGraphDate("all");
    fetchGraphData();
  };

  const handleGraphSubmit = () => {
    setAppliedGraphSensorTypes(graphFilterSensorTypes);
    setAppliedGraphDate(graphFilterDate);
    fetchGraphData();
  };

  const downloadDataAsCSV = () => {
    try {
      const token = localStorage.getItem('token');
      
      // Fetch all data with a very large limit
      fetchWithFallback('/api/sensors/data?limit=999999', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })
      .then(response => {
        if (response.status === 401) {
          localStorage.clear();
          navigate('/');
          return;
        }
        return response.json();
      })
      .then(result => {
        if (!result.success || !result.data || result.data.length === 0) {
          showToast('error', 'No records to download');
          return;
        }

        const allRecords = result.data;

        // Define CSV headers
        const headers = [
          'Timestamp',
          'Temperature (C)',
          'Humidity (%)',
          'Pressure (hPa)',
          'VOCs (kOhm)',
          'NO2 (PPM)',
          'CO (PPM)',
          'PM2.5 (ug/m3)',
          'PM10 (ug/m3)',
          'AQI',
          'Status'
        ];

        // Build CSV rows
        const rows = allRecords.map(record => {
          const aqi = calculateAQI(record);
          
          // Determine status based on AQI category, not individual thresholds
          let status = 'safe';
          if (aqi.category === 'Emergency' || aqi.category === 'Acutely Unhealthy') {
            status = 'danger';
          } else if (aqi.category === 'Very Unhealthy' || aqi.category === 'Unhealthy for Sensitive') {
            status = 'warning';
          } else {
            status = 'safe'; // Good or Fair
          }

          return [
            formatTimestamp(record.timestamp),
            record.temperature?.toFixed(1) || 'N/A',
            record.humidity?.toFixed(1) || 'N/A',
            record.pressure?.toFixed(2) || 'N/A',
            record.vocs?.toFixed(1) || 'N/A',
            record.nitrogen_dioxide?.toFixed(2) || 'N/A',
            record.carbon_monoxide?.toFixed(2) || 'N/A',
            record.pm25?.toFixed(1) || 'N/A',
            record.pm10?.toFixed(1) || 'N/A',
            aqi.value,
            status
          ];
        });

        // Create CSV content
        const headerRow = headers.map(header => `"${header}"`).join(',');
        const dataRows = rows.map(row => row.map((cell, index) => {
          // For timestamp column (index 0), add single quote prefix to force text format in Excel
          if (index === 0) {
            return `"'${cell}"`;
          }
          return `"${cell}"`;
        }).join(','));
        
        const csvContent = [headerRow, ...dataRows].join('\n');

        // Create blob and download
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);
        
        link.setAttribute('href', url);
        link.setAttribute('download', `sensor-data-${new Date().toISOString().split('T')[0]}.csv`);
        link.style.visibility = 'hidden';
        
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        showToast('success', `Downloaded ${allRecords.length} records`);
      })
      .catch(error => {
        console.error('Error downloading CSV:', error);
        showToast('error', 'Failed to download CSV');
      });
    } catch (error) {
      console.error('Error downloading CSV:', error);
      showToast('error', 'Failed to download CSV');
    }
  };

  const getFilteredGraphData = () => {
    let filtered = [...graphData];

    // Filter by date using applied date
    if (appliedGraphDate !== "all") {
      const now = new Date();
      filtered = filtered.filter(item => {
        // Parse the time string back to date
        const itemDate = new Date();
        const [time] = item.time.split(' ');
        const [hours, minutes, seconds] = time.split(':');
        itemDate.setHours(parseInt(hours), parseInt(minutes), parseInt(seconds));
        
        const diffTime = Math.abs(now - itemDate);
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
        
        if (appliedGraphDate === "today") {
          return itemDate.toDateString() === now.toDateString();
        } else if (appliedGraphDate === "7days") {
          return diffDays <= 7;
        } else if (appliedGraphDate === "30days") {
          return diffDays <= 30;
        }
        return true;
      });
    }

    // Limit to only 10 data points for better visibility
    const maxPoints = 10;
    if (filtered.length > maxPoints) {
      const step = Math.ceil(filtered.length / maxPoints);
      filtered = filtered.filter((_, index) => index % step === 0);
    }

    // Ensure we have exactly 10 points or less
    if (filtered.length > maxPoints) {
      filtered = filtered.slice(-maxPoints);
    }

    return filtered;
  };

  // Helper function to get peak value for a sensor type
  const getPeakValue = (sensorType) => {
    const filtered = getFilteredGraphData();
    if (filtered.length === 0) return null;
    
    const values = filtered.map(item => item[sensorType]).filter(val => val !== null && val !== undefined);
    if (values.length === 0) return null;
    
    return Math.max(...values);
  };

  // Helper function to get average value for a sensor type
  const getAverageValue = (sensorType) => {
    const filtered = getFilteredGraphData();
    if (filtered.length === 0) return null;
    
    const values = filtered.map(item => item[sensorType]).filter(val => val !== null && val !== undefined);
    if (values.length === 0) return null;
    
    const sum = values.reduce((acc, val) => acc + val, 0);
    return sum / values.length;
  };

  const getFilteredRecords = () => {
    let filtered = [...records];

    // Filter by date using applied date
    if (appliedDate !== "all") {
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      
      filtered = filtered.filter(record => {
        const recordDate = new Date(record.timestamp);
        const recordDay = new Date(recordDate.getFullYear(), recordDate.getMonth(), recordDate.getDate());
        const diffTime = today - recordDay;
        const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
        
        if (appliedDate === "today") {
          return diffDays === 0;
        } else if (appliedDate === "7days") {
          return diffDays >= 0 && diffDays < 7;
        } else if (appliedDate === "30days") {
          return diffDays >= 0 && diffDays < 30;
        }
        return true;
      });
    }

    return filtered;
  };

  const getChartHeight = () => {
    return isMobile ? '220px' : '280px';
  };

  return (
    <div className={`dashboard ${darkMode ? 'dark-mode' : ''}`}>
      <Toast />
      <TutorialModal triggerOnLogin={triggerTutorialOnLogin} />
      <ConfirmModal 
        isOpen={showConfirmModal}
        title="Delete Record"
        message="Are you sure you want to delete this record? This action cannot be undone."
        confirmText="Delete"
        cancelText="Cancel"
        isDangerous={true}
        onConfirm={confirmDeleteRecord}
        onCancel={() => {
          setShowConfirmModal(false);
          setRecordToDelete(null);
        }}
      />
      <SensorDetailModal
        isOpen={showSensorDetailModal}
        sensorType={selectedSensorType}
        sensorValue={sensorData ? sensorData[selectedSensorType] : null}
        timestamp={sensorData?.timestamp}
        onClose={() => {
          setShowSensorDetailModal(false);
          setSelectedSensorType(null);
        }}
      />
      <NotificationRibbon />
      <SensorStatusRibbon 
        sensorConnected={sensorConnected} 
        lastSensorUpdate={lastSensorUpdate}
      />
      
      {/* Top Header - Mobile Only */}
      <header className="mobile-top-header">
        <h1>SMOKi</h1>
        <button className="user-btn" onClick={() => setShowUserMenu(!showUserMenu)}>
          <UserIcon size={24} />
        </button>
        
        {/* User Menu Dropdown */}
        {showUserMenu && (
          <div className="user-menu-dropdown">
            <div className="user-menu-header">
              <div className="user-menu-icon"><UserIcon size={24} /></div>
              <div className="user-menu-info">
                <div className="user-menu-name">{localStorage.getItem('username') || 'User'}</div>
                <div className="user-menu-role">{localStorage.getItem('role') === 'superadmin' ? 'SuperAdmin' : 'Admin'}</div>
              </div>
            </div>
            <button className="user-menu-logout" onClick={handleLogout}>
              <LogOut size={24} />
              <span>Sign out</span>
            </button>
          </div>
        )}
      </header>

      {/* Overlay for user menu */}
      {showUserMenu && (
        <div className="user-menu-overlay" onClick={() => setShowUserMenu(false)}></div>
      )}

      {/* Mobile Menu Button - Hidden on mobile with bottom nav */}
      <button className="mobile-menu-btn desktop-only" onClick={() => setMobileMenuOpen(!mobileMenuOpen)}>
        <Menu />
      </button>

      {/* Sidebar Overlay */}
      <div 
        className={`sidebar-overlay ${mobileMenuOpen ? 'active' : ''}`}
        onClick={() => setMobileMenuOpen(false)}
      ></div>

      {/* Sidebar - Hidden on mobile */}
      <aside 
        className={`sidebar desktop-sidebar ${mobileMenuOpen ? 'mobile-open' : ''}`}
        onMouseEnter={() => setSidebarHovered(true)}
        onMouseLeave={() => setSidebarHovered(false)}
      >
        <div className="sidebar-header">
          <h1>
            <span className="menu-icon"><Menu /></span>
            <span className="menu-text">SMOKi</span>
          </h1>
        </div>

        <nav className="sidebar-nav">
          <button 
            onClick={() => {
              setActivePage("dashboard");
              setMobileMenuOpen(false);
            }}
            className={`nav-item ${activePage === "dashboard" ? "active" : ""}`}
          >
            <span className="nav-icon"><Home /></span>
            <span className="nav-text">Dashboard</span>
          </button>

          <button 
            onClick={() => {
              setActivePage("records");
              setMobileMenuOpen(false);
            }}
            className={`nav-item ${activePage === "records" ? "active" : ""}`}
          >
            <span className="nav-icon"><FileText /></span>
            <span className="nav-text">Records</span>
          </button>

          <button 
            onClick={() => {
              setActivePage("graphs");
              setMobileMenuOpen(false);
            }}
            className={`nav-item ${activePage === "graphs" ? "active" : ""}`}
          >
            <span className="nav-icon"><TrendingUp /></span>
            <span className="nav-text">Graphs</span>
          </button>

          <button 
            onClick={() => {
              setActivePage("sensors");
              setMobileMenuOpen(false);
            }}
            className={`nav-item ${activePage === "sensors" ? "active" : ""}`}
          >
            <span className="nav-icon"><Zap /></span>
            <span className="nav-text">Sensors</span>
          </button>

          <button 
            onClick={() => {
              setActivePage("info");
              setMobileMenuOpen(false);
            }}
            className={`nav-item ${activePage === "info" ? "active" : ""}`}
          >
            <span className="nav-icon"><FileText /></span>
            <span className="nav-text">Info</span>
          </button>

          <button 
            onClick={() => setDarkMode(!darkMode)}
            className="nav-item"
          >
            <span className="nav-icon">{darkMode ? <Sun /> : <Moon />}</span>
            <span className="nav-text">{darkMode ? 'Light Mode' : 'Dark Mode'}</span>
          </button>
        </nav>

        <div className="sidebar-footer">
          <div className="user-info">
            <UserIcon size={20} />
            <div className="user-details">
              <div className="user-name">{(localStorage.getItem('username') || 'User').charAt(0).toUpperCase() + (localStorage.getItem('username') || 'User').slice(1)}</div>
              <div className="user-email">{localStorage.getItem('role') === 'superadmin' ? 'Super Admin' : localStorage.getItem('role') === 'admin' ? 'Admin' : (localStorage.getItem('role') || 'Admin').charAt(0).toUpperCase() + (localStorage.getItem('role') || 'Admin').slice(1)}</div>
            </div>
          </div>
          <button className="sign-out-btn" onClick={handleLogout}>
            <span><LogOut /></span>
            <span>Sign out</span>
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="main-content">
          {activePage === "dashboard" && (
            <div className="dashboard-page-container">
              <div className="dashboard-layout">
                <div className="dashboard-camera-section">
                  <div className="camera-feed-box">
                    <WebRTCViewer />
                  </div>
                </div>
                
                <div className="dashboard-violators-column">
                  {/* All Detections Table */}
                  <div className="dashboard-section-compact">
                    <div className="section-header-compact">
                      <div className="section-title-row">
                        <div>
                          <h2>Live Detections</h2>
                          <p className="section-subtitle">Near real-time AI detection results (~2-5s latency)</p>
                        </div>
                      </div>
                    </div>
                    <div className="detections-table-container">
                      <div className="detections-table-header">
                        <div className="detection-col timestamp">Time</div>
                        <div className="detection-col type">Type</div>
                        <div className="detection-col object">Object</div>
                        <div className="detection-col confidence">Confidence</div>
                        <div className="detection-col details">Details</div>
                        <div className="detection-col report">Report</div>
                      </div>
                      <div className="detections-table-body">
                        {(() => {
                          // Show only real detection data with validation
                          const realDetectionsFormatted = allDetections.length > 0 ? allDetections
                            .filter(detection => {
                              // Filter out invalid/undefined detections
                              return detection && 
                                     detection.detection_type && 
                                     detection.detection_type !== 'Unknown' &&
                                     detection.class_name && 
                                     detection.class_name !== 'Unknown' &&
                                     detection.confidence && 
                                     detection.confidence !== '0.0' &&
                                     parseFloat(detection.confidence) > 0;
                            })
                            .slice(0, 10)
                            .map((detection) => ({
                              id: detection.id,
                              time: new Date(detection.timestamp).toLocaleTimeString(),
                              type: detection.detection_type || 'Unknown',
                              object: detection.class_name || 'Unknown',
                              confidence: detection.confidence || '0.0',
                              plate: detection.license_plate || 'Not detected',
                              level: detection.smoke_level || 'None',
                              isReal: true
                            })) : [];
                          
                          // Show message if no real data
                          if (realDetectionsFormatted.length === 0) {
                            return (
                              <div className="no-data-message">
                                <p>No recent detections available</p>
                              </div>
                            );
                          }
                          
                          return realDetectionsFormatted.map((detection) => (
                            <div key={detection.id} className="detection-row real-detection">
                              <div className="detection-col timestamp">
                                {detection.time}
                              </div>
                              <div className="detection-col type">
                                <span className={`detection-type-badge ${detection.type.toLowerCase().replace(' ', '-')}`}>
                                  {detection.type}
                                </span>
                              </div>
                              <div className="detection-col object">
                                {detection.object}
                              </div>
                              <div className="detection-col confidence">
                                {detection.confidence}%
                              </div>
                              <div className="detection-col details">
                                {detection.type === 'Vehicle' && detection.plate && detection.plate !== 'N/A' && (
                                  <span className="license-plate">{detection.plate}</span>
                                )}
                                {detection.type === 'Smoke' && (
                                  <div className="smoke-details">
                                    <span className={`smoke-level ${detection.level.toLowerCase()}`}>
                                      {detection.level} Level
                                    </span>
                                  </div>
                                )}
                                {detection.type === 'License' && (
                                  <span className="plate-detected">Plate Detected</span>
                                )}
                              </div>
                              <div className="detection-col report">
                                {detection.type === 'Smoke' ? (
                                  <button 
                                    className="report-smoke-btn"
                                    onClick={async () => {
                                      try {
                                        setReportingSmoke(detection.id);
                                        
                                        // Generate HTML report for this specific detection time
                                        const response = await fetch('https://smoki-backend-rpi.onrender.com/api/stream/generate-report', {
                                          method: 'POST',
                                          headers: {
                                            'Content-Type': 'application/json',
                                          },
                                          body: JSON.stringify({
                                            report_type: 'smoke_detection',
                                            detection_timestamp: detection.timestamp,
                                            detection_id: detection.id,
                                            detection_data: {
                                              time: detection.time,
                                              type: detection.type,
                                              object: detection.object,
                                              confidence: detection.confidence,
                                              details: detection.details
                                            }
                                          })
                                        });
                                        
                                        if (response.ok) {
                                          const result = await response.json();
                                          if (result.success) {
                                            // Open the enhanced report with evidence gallery in a new tab
                                            const reportUrl = `https://smoki-backend-rpi.onrender.com/api/stream/reports/${result.report_id}`;
                                            window.open(reportUrl, '_blank');
                                            
                                            showToast(`Smoke report opened: ${result.report_id}`, 'success');
                                          } else {
                                            throw new Error(result.message || 'Report generation failed');
                                          }
                                        } else {
                                          throw new Error(`Report generation failed: ${response.status}`);
                                        }
                                      } catch (error) {
                                        console.error('Error generating smoke report:', error);
                                        showToast('Failed to generate smoke report', 'error');
                                      } finally {
                                        setReportingSmoke(null);
                                      }
                                    }}
                                    disabled={reportingSmoke === detection.id}
                                    title="Generate HTML report for this smoke detection"
                                  >
                                    {reportingSmoke === detection.id ? 'Reporting...' : 'Report'}
                                  </button>
                                ) : (
                                  <span className="no-report">—</span>
                                )}
                              </div>
                            </div>
                          ));
                        })()}
                      </div>
                    </div>
                  </div>

                  {/* Detection Summary Section */}
                  <div className="dashboard-section-compact">
                    <div className="section-header-compact">
                      <h2>Detection Summary</h2>
                      <p className="section-subtitle">Current session statistics</p>
                    </div>
                    <div className="detection-summary-grid">
                      <div className="summary-card">
                        <div className="summary-number">
                          {allDetections.length > 0 ? allDetections.filter(d => d.detection_type === 'Vehicle').length : 0}
                        </div>
                        <div className="summary-label">Vehicles</div>
                      </div>
                      <div className="summary-card">
                        <div className="summary-number">
                          {allDetections.length > 0 ? allDetections.filter(d => d.detection_type === 'Smoke').length : 0}
                        </div>
                        <div className="summary-label">Smoke Events</div>
                      </div>
                      <div className="summary-card">
                        <div className="summary-number">
                          {allDetections.length > 0 ? allDetections.filter(d => d.detection_type === 'License').length : 0}
                        </div>
                        <div className="summary-label">Plates Read</div>
                      </div>
                      <div className="summary-card">
                        <div className="summary-number">
                          {allDetections.length > 0 ? allDetections.length : 0}
                        </div>
                        <div className="summary-label">Total Detections</div>
                      </div>
                    </div>
                  </div>

                  {/* Vehicle Ranking Section */}
                  <div className="dashboard-section-compact">
                    <div className="section-header-compact">
                      <h2>Vehicle Ranking</h2>
                      <p className="section-subtitle">Top violators by emissions</p>
                    </div>
                    <div className="ranking-list">
                      {(() => {
                        // Show only real vehicle ranking data
                        const hasRealData = vehicleRanking && vehicleRanking.length > 0;
                        
                        if (!hasRealData) {
                          return (
                            <div className="no-data-message">
                              <p>No vehicle violations recorded</p>
                            </div>
                          );
                        }
                        
                        const realRankingFormatted = vehicleRanking.slice(0, 5).map((vehicle, index) => ({
                          id: `real_${vehicle.id || vehicle.license_plate}`,
                          plate: vehicle.license_plate,
                          violations: vehicle.violation_count || (Array.isArray(vehicle.violations) ? vehicle.violations.length : vehicle.violations) || 0,
                          status: (vehicle.violation_count || 0) > 10 ? 'critical' : (vehicle.violation_count || 0) > 5 ? 'warning' : 'caution',
                          lastSeen: vehicle.last_detected ? new Date(vehicle.last_detected).toLocaleTimeString() : (vehicle.last_violation ? new Date(vehicle.last_violation).toLocaleTimeString() : 'Unknown'),
                          vehicleType: vehicle.vehicle_type || 'Vehicle',
                          smokeLevel: vehicle.smoke_detected ? 'High' : 'Low',
                          latest_violation_id: vehicle.latest_violation_id,
                          isReal: true
                        }));
                        
                        return realRankingFormatted.map((vehicle, index) => (
                          <div key={vehicle.id} className="ranking-item real-ranking">
                            <div className="ranking-position">#{index + 1}</div>
                            <div className="ranking-details">
                              <div className="ranking-plate">{vehicle.plate}</div>
                              <div className="ranking-info">
                                <span className="violations-count">
                                  {typeof vehicle.violations === 'number' ? vehicle.violations : 0} violations
                                </span>
                                <span className="vehicle-type">{vehicle.vehicleType}</span>
                                <span className="last-seen">{vehicle.lastSeen}</span>
                              </div>
                            </div>
                            <div className="ranking-status">
                              <div className={`status-indicator ${vehicle.status}`}></div>
                              <span className={`status-text ${vehicle.status}`}>
                                {vehicle.status === 'critical' ? 'Critical' : 
                                 vehicle.status === 'warning' ? 'Warning' : 
                                 vehicle.status === 'caution' ? 'Caution' : 'Safe'}
                              </span>
                              <div className={`smoke-indicator ${vehicle.smokeLevel.toLowerCase()}`}>
                                Smoke: {vehicle.smokeLevel}
                              </div>
                            </div>
                            <div className="ranking-actions">
                              <button 
                                className="report-btn"
                                onClick={async () => {
                                  try {
                                    // Generate HTML report with violation-specific frame using enhanced report generator
                                    const response = await fetch('https://smoki-backend-rpi.onrender.com/api/stream/generate-report', {
                                      method: 'POST',
                                      headers: {
                                        'Content-Type': 'application/json',
                                      },
                                      body: JSON.stringify({
                                        report_type: 'vehicle_violation',
                                        violation_id: vehicle.latest_violation_id ? vehicle.latest_violation_id.toString() : null,
                                        vehicle_data: {
                                          plate: vehicle.plate,
                                          vehicleType: vehicle.vehicleType,
                                          violations: vehicle.violations,
                                          status: vehicle.status,
                                          smokeLevel: vehicle.smokeLevel,
                                          lastSeen: vehicle.lastSeen
                                        }
                                      })
                                    });
                                    
                                    if (response.ok) {
                                      const result = await response.json();
                                      if (result.success) {
                                        // Open the enhanced report with evidence gallery in a new tab
                                        const reportUrl = `https://smoki-backend-rpi.onrender.com/api/stream/reports/${result.report_id}`;
                                        window.open(reportUrl, '_blank');
                                        
                                        showToast(`Vehicle report opened: ${vehicle.plate}`, 'success');
                                      } else {
                                        throw new Error(result.message || 'Report generation failed');
                                      }
                                    } else {
                                      throw new Error(`Report generation failed: ${response.status}`);
                                    }
                                  } catch (error) {
                                    console.error('Error generating vehicle report:', error);
                                    showToast('Failed to generate vehicle report', 'error');
                                  }
                                }}
                                title="Generate and view enhanced HTML report with evidence gallery for this vehicle"
                              >
                                Report
                              </button>
                            </div>
                          </div>
                        ));
                      })()}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {activePage === "sensors" && (
            <section className="sensors-page-container-new">
              {!selectedSensor ? (
                // Camera + Sensor Cards View
                <div className="sensors-layout">
                  <div className="sensors-camera-section">
                    <div className="camera-feed-box">
                      <WebRTCViewer />
                    </div>
                  </div>
                  
                  <div className="sensors-cards-column">
                    {/* AQI Card */}
                    {aqiData && (
                      <div className="aqi-card-compact">
                        <div className="aqi-card-header">
                          <div className="aqi-icon-small">
                            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
                              <polyline points="14,2 14,8 20,8"/>
                              <line x1="16" y1="13" x2="8" y2="13"/>
                              <line x1="16" y1="17" x2="8" y2="17"/>
                              <polyline points="10,9 9,9 8,9"/>
                            </svg>
                          </div>
                          <h3>Air Quality Index</h3>
                        </div>
                        <div className="aqi-value-compact" style={{
                          backgroundColor: aqiData.category.color,
                          color: aqiData.category.textColor
                        }}>
                          {aqiData.overallAQI}
                        </div>
                        <div className="aqi-category-compact" style={{
                          color: aqiData.category.color
                        }}>
                          {aqiData.category.level}
                        </div>
                        <div className="aqi-description-compact">
                          {aqiData.category.description}
                        </div>
                        {aqiData.dominantPollutant && (
                          <div className="aqi-dominant-compact">
                            Primary: {getPollutantDisplayName(aqiData.dominantPollutant)}
                          </div>
                        )}
                      </div>
                    )}
                    
                    <div className="sensor-card-compact" onClick={() => setSelectedSensor(true)}>
                      <div className="sensor-card-compact-header">
                        <div className="sensor-icon-small"><Thermometer size={24} /></div>
                        <h3>Temperature</h3>
                      </div>
                      <div className="sensor-value-compact">
                        {sensorData?.temperature ? `${sensorData.temperature.toFixed(1)}°C` : '--°C'}
                      </div>
                      <div className="sensor-status-compact">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div className="sensor-card-compact" onClick={() => setSelectedSensor(true)}>
                      <div className="sensor-card-compact-header">
                        <div className="sensor-icon-small"><Droplet size={24} /></div>
                        <h3>Humidity</h3>
                      </div>
                      <div className="sensor-value-compact">
                        {sensorData?.humidity ? `${sensorData.humidity.toFixed(1)}%` : '--%'}
                      </div>
                      <div className="sensor-status-compact">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div className="sensor-card-compact" onClick={() => setSelectedSensor(true)}>
                      <div className="sensor-card-compact-header">
                        <div className="sensor-icon-small"><Zap size={24} /></div>
                        <h3>Pressure</h3>
                      </div>
                      <div className="sensor-value-compact">
                        {sensorData?.pressure ? `${sensorData.pressure.toFixed(1)} hPa` : '-- hPa'}
                      </div>
                      <div className="sensor-status-compact">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div className="sensor-card-compact" onClick={() => setSelectedSensor(true)}>
                      <div className="sensor-card-compact-header">
                        <div className="sensor-icon-small"><Activity size={24} /></div>
                        <h3>VOCs</h3>
                      </div>
                      <div className="sensor-value-compact">
                        {sensorData?.vocs ? `${sensorData.vocs.toFixed(1)} kΩ` : '-- kΩ'}
                      </div>
                      <div className="sensor-status-compact">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div className="sensor-card-compact" onClick={() => setSelectedSensor(true)}>
                      <div className="sensor-card-compact-header">
                        <div className="sensor-icon-small"><Wind size={24} /></div>
                        <h3>Nitrogen Dioxide</h3>
                      </div>
                      <div className="sensor-value-compact">
                        {sensorData?.nitrogen_dioxide ? `${sensorData.nitrogen_dioxide.toFixed(2)} PPM` : '-- PPM'}
                      </div>
                      <div className="sensor-status-compact">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div className="sensor-card-compact" onClick={() => setSelectedSensor(true)}>
                      <div className="sensor-card-compact-header">
                        <div className="sensor-icon-small"><Flame size={24} /></div>
                        <h3>Carbon Monoxide</h3>
                      </div>
                      <div className="sensor-value-compact">
                        {sensorData?.carbon_monoxide ? `${sensorData.carbon_monoxide.toFixed(2)} PPM` : '-- PPM'}
                      </div>
                      <div className="sensor-status-compact">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div className="sensor-card-compact" onClick={() => setSelectedSensor(true)}>
                      <div className="sensor-card-compact-header">
                        <div className="sensor-icon-small"><Circle size={24} /></div>
                        <h3>PM 2.5</h3>
                      </div>
                      <div className="sensor-value-compact">
                        {sensorData?.pm25 ? `${sensorData.pm25.toFixed(1)} µg/m³` : '-- µg/m³'}
                      </div>
                      <div className="sensor-status-compact">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div className="sensor-card-compact" onClick={() => setSelectedSensor(true)}>
                      <div className="sensor-card-compact-header">
                        <div className="sensor-icon-small"><Circle size={24} /></div>
                        <h3>PM 10</h3>
                      </div>
                      <div className="sensor-value-compact">
                        {sensorData?.pm10 ? `${sensorData.pm10.toFixed(1)} µg/m³` : '-- µg/m³'}
                      </div>
                      <div className="sensor-status-compact">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                // Detailed Sensor View - Show All Sensors
                <div className="sensor-detail-view">
                  <button className="back-button" onClick={() => setSelectedSensor(null)}>
                    ← Back to Sensors
                  </button>
                  
                  <div className="sensors-grid">
                    <div 
                      className="sensor-card"
                      onClick={() => {
                        setSelectedSensorType('temperature');
                        setShowSensorDetailModal(true);
                      }}
                    >
                      <div className="sensor-card-header">
                        <div className="sensor-icon"><Thermometer /></div>
                        <h3>Temperature</h3>
                      </div>
                      <div className={`sensor-change ${calculateChange(sensorData?.temperature, previousSensorData?.temperature) >= 0 ? 'positive' : 'negative'}`}>
                        {calculateChange(sensorData?.temperature, previousSensorData?.temperature) >= 0 ? '↑' : '↓'} {Math.abs(calculateChange(sensorData?.temperature, previousSensorData?.temperature)).toFixed(1)}%
                      </div>
                      <div className="sensor-value">
                        {sensorData?.temperature ? `${sensorData.temperature.toFixed(1)}°C` : '--°C'}
                      </div>
                      <div className="sensor-status">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>
                    
                    <div 
                      className="sensor-card"
                      onClick={() => {
                        setSelectedSensorType('humidity');
                        setShowSensorDetailModal(true);
                      }}
                    >
                      <div className="sensor-card-header">
                        <div className="sensor-icon"><Droplet /></div>
                        <h3>Humidity</h3>
                      </div>
                      <div className={`sensor-change ${calculateChange(sensorData?.humidity, previousSensorData?.humidity) >= 0 ? 'positive' : 'negative'}`}>
                        {calculateChange(sensorData?.humidity, previousSensorData?.humidity) >= 0 ? '↑' : '↓'} {Math.abs(calculateChange(sensorData?.humidity, previousSensorData?.humidity)).toFixed(1)}%
                      </div>
                      <div className="sensor-value">
                        {sensorData?.humidity ? `${sensorData.humidity.toFixed(1)}%` : '--%'}
                      </div>
                      <div className="sensor-status">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div 
                      className="sensor-card"
                      onClick={() => {
                        setSelectedSensorType('pressure');
                        setShowSensorDetailModal(true);
                      }}
                    >
                      <div className="sensor-card-header">
                        <div className="sensor-icon"><Zap /></div>
                        <h3>Pressure</h3>
                      </div>
                      <div className={`sensor-change ${calculateChange(sensorData?.pressure, previousSensorData?.pressure) >= 0 ? 'positive' : 'negative'}`}>
                        {calculateChange(sensorData?.pressure, previousSensorData?.pressure) >= 0 ? '↑' : '↓'} {Math.abs(calculateChange(sensorData?.pressure, previousSensorData?.pressure)).toFixed(1)}%
                      </div>
                      <div className="sensor-value">
                        {sensorData?.pressure ? `${sensorData.pressure.toFixed(1)} hPa` : '-- hPa'}
                      </div>
                      <div className="sensor-status">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>
                    
                    <div 
                      className="sensor-card"
                      onClick={() => {
                        setSelectedSensorType('vocs');
                        setShowSensorDetailModal(true);
                      }}
                    >
                      <div className="sensor-card-header">
                        <div className="sensor-icon"><Activity /></div>
                        <h3>VOCs</h3>
                      </div>
                      <div className={`sensor-change ${calculateChange(sensorData?.vocs, previousSensorData?.vocs) >= 0 ? 'positive' : 'negative'}`}>
                        {calculateChange(sensorData?.vocs, previousSensorData?.vocs) >= 0 ? '↑' : '↓'} {Math.abs(calculateChange(sensorData?.vocs, previousSensorData?.vocs)).toFixed(1)}%
                      </div>
                      <div className="sensor-value">
                        {sensorData?.vocs ? `${sensorData.vocs.toFixed(1)} kΩ` : '-- kΩ'}
                      </div>
                      <div className="sensor-status">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div 
                      className="sensor-card"
                      onClick={() => {
                        setSelectedSensorType('nitrogen_dioxide');
                        setShowSensorDetailModal(true);
                      }}
                    >
                      <div className="sensor-card-header">
                        <div className="sensor-icon"><Wind /></div>
                        <h3>Nitrogen Dioxide</h3>
                      </div>
                      <div className={`sensor-change ${calculateChange(sensorData?.nitrogen_dioxide, previousSensorData?.nitrogen_dioxide) >= 0 ? 'positive' : 'negative'}`}>
                        {calculateChange(sensorData?.nitrogen_dioxide, previousSensorData?.nitrogen_dioxide) >= 0 ? '↑' : '↓'} {Math.abs(calculateChange(sensorData?.nitrogen_dioxide, previousSensorData?.nitrogen_dioxide)).toFixed(1)}%
                      </div>
                      <div className="sensor-value">
                        {sensorData?.nitrogen_dioxide ? `${sensorData.nitrogen_dioxide.toFixed(2)} PPM` : '-- PPM'}
                      </div>
                      <div className="sensor-status">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>
                    
                    <div 
                      className="sensor-card"
                      onClick={() => {
                        setSelectedSensorType('carbon_monoxide');
                        setShowSensorDetailModal(true);
                      }}
                    >
                      <div className="sensor-card-header">
                        <div className="sensor-icon"><Flame /></div>
                        <h3>Carbon Monoxide</h3>
                      </div>
                      <div className={`sensor-change ${calculateChange(sensorData?.carbon_monoxide, previousSensorData?.carbon_monoxide) >= 0 ? 'positive' : 'negative'}`}>
                        {calculateChange(sensorData?.carbon_monoxide, previousSensorData?.carbon_monoxide) >= 0 ? '↑' : '↓'} {Math.abs(calculateChange(sensorData?.carbon_monoxide, previousSensorData?.carbon_monoxide)).toFixed(1)}%
                      </div>
                      <div className="sensor-value">
                        {sensorData?.carbon_monoxide ? `${sensorData.carbon_monoxide.toFixed(2)} PPM` : '-- PPM'}
                      </div>
                      <div className="sensor-status">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>

                    <div 
                      className="sensor-card"
                      onClick={() => {
                        setSelectedSensorType('pm25');
                        setShowSensorDetailModal(true);
                      }}
                    >
                      <div className="sensor-card-header">
                        <div className="sensor-icon"><Circle /></div>
                        <h3>PM 2.5</h3>
                      </div>
                      <div className={`sensor-change ${calculateChange(sensorData?.pm25, previousSensorData?.pm25) >= 0 ? 'positive' : 'negative'}`}>
                        {calculateChange(sensorData?.pm25, previousSensorData?.pm25) >= 0 ? '↑' : '↓'} {Math.abs(calculateChange(sensorData?.pm25, previousSensorData?.pm25)).toFixed(1)}%
                      </div>
                      <div className="sensor-value">
                        {sensorData?.pm25 ? `${sensorData.pm25.toFixed(1)} µg/m³` : '-- µg/m³'}
                      </div>
                      <div className="sensor-status">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>
                    
                    <div 
                      className="sensor-card"
                      onClick={() => {
                        setSelectedSensorType('pm10');
                        setShowSensorDetailModal(true);
                      }}
                    >
                      <div className="sensor-card-header">
                        <div className="sensor-icon"><Circle /></div>
                        <h3>PM 10</h3>
                      </div>
                      <div className={`sensor-change ${calculateChange(sensorData?.pm10, previousSensorData?.pm10) >= 0 ? 'positive' : 'negative'}`}>
                        {calculateChange(sensorData?.pm10, previousSensorData?.pm10) >= 0 ? '↑' : '↓'} {Math.abs(calculateChange(sensorData?.pm10, previousSensorData?.pm10)).toFixed(1)}%
                      </div>
                      <div className="sensor-value">
                        {sensorData?.pm10 ? `${sensorData.pm10.toFixed(1)} µg/m³` : '-- µg/m³'}
                      </div>
                      <div className="sensor-status">
                        {sensorData ? formatTimestamp(sensorData.timestamp) : 'Waiting for data...'}
                      </div>
                    </div>
                  </div>
                </div>
              )}
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
              {/* Disclaimer */}
              <div className="data-disclaimer">
                <div className="disclaimer-icon"><InfoIcon /></div>
                <div className="disclaimer-content">
                  <strong>Note:</strong> Air quality sensors used in records and graphs pages are not reference grade. Hence the data provided is for indicative measurements only and should be interpreted accordingly.
                </div>
              </div>

              {/* Filters Section */}
              <div className="filters-container">
                <div className="filters-header">
                  <svg className="filter-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="4" y1="6" x2="20" y2="6"></line>
                    <line x1="8" y1="12" x2="16" y2="12"></line>
                    <line x1="10" y1="18" x2="14" y2="18"></line>
                  </svg>
                  Filters
                </div>
                <div className="filters-content">
                  <div className="filter-group">
                    <label>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style={{display: 'inline', marginRight: '6px', verticalAlign: 'middle'}}>
                        <path d="M8.464 15.536a5 5 0 0 1 0-7.072m-2.828 9.9a9 9 0 0 1 0-12.728m9.9 9.9a5 5 0 0 0 0-7.072m2.828 9.9a9 9 0 0 0 0-12.728M13 12a1 1 0 1 1-2 0 1 1 0 0 1 2 0" stroke="#5b6b8d" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                      Sensor Types
                    </label>
                    <div className="custom-dropdown">
                      <div 
                        className="dropdown-header"
                        onClick={() => setSensorDropdownOpen(!sensorDropdownOpen)}
                      >
                        <span>{getSelectedSensorNames(filterSensorTypes)}</span>
                        <svg className="dropdown-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <polyline points={sensorDropdownOpen ? "18 15 12 9 6 15" : "6 9 12 15 18 9"}></polyline>
                        </svg>
                      </div>
                      {sensorDropdownOpen && (
                        <div className="dropdown-menu">
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={filterSensorTypes.temperature}
                              onChange={() => toggleSensorType('temperature')}
                            />
                            Temperature
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={filterSensorTypes.humidity}
                              onChange={() => toggleSensorType('humidity')}
                            />
                            Humidity
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={filterSensorTypes.pressure}
                              onChange={() => toggleSensorType('pressure')}
                            />
                            Pressure
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={filterSensorTypes.vocs}
                              onChange={() => toggleSensorType('vocs')}
                            />
                            VOCs
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={filterSensorTypes.no2}
                              onChange={() => toggleSensorType('no2')}
                            />
                            NO₂
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={filterSensorTypes.co}
                              onChange={() => toggleSensorType('co')}
                            />
                            CO
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={filterSensorTypes.pm25}
                              onChange={() => toggleSensorType('pm25')}
                            />
                            PM2.5
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={filterSensorTypes.pm10}
                              onChange={() => toggleSensorType('pm10')}
                            />
                            PM10
                          </label>
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="filter-group">
                    <label>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{display: 'inline', marginRight: '6px', verticalAlign: 'middle'}}>
                        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                        <line x1="16" y1="2" x2="16" y2="6"></line>
                        <line x1="8" y1="2" x2="8" y2="6"></line>
                        <line x1="3" y1="10" x2="21" y2="10"></line>
                      </svg>
                      Date
                    </label>
                    <select 
                      className="filter-select"
                      value={filterDate}
                      onChange={(e) => {
                        setFilterDate(e.target.value);
                        setAppliedDate(e.target.value);
                        fetchRecords();
                      }}
                    >
                      <option value="all">All Dates</option>
                      <option value="today">Today</option>
                      <option value="7days">Last 7 Days</option>
                      <option value="30days">Last 30 Days</option>
                    </select>
                  </div>
                  <button className="submit-filters-btn" onClick={handleClearFilters}>Clear Filters</button>
                </div>
              </div>

              {/* Data Logs Section */}
              <div className="data-logs-container">
                <div className="data-logs-header">
                  <div className="data-logs-title">
                    <h2>Data Logs</h2>
                    <p>Near real-time and historical sensor measurements</p>
                  </div>
                  <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                    {userRole === 'superadmin' && (
                      <button
                        className="create-action-btn"
                        onClick={() => setShowCreateModal(true)}
                        title="Create new record"
                        style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 14px', fontSize: '14px' }}
                      >
                        <PlusIcon />
                        <span>New</span>
                      </button>
                    )}
                    <button 
                      className="download-csv-btn"
                      onClick={downloadDataAsCSV}
                      title="Download all data as CSV"
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                        <polyline points="7 10 12 15 17 10"></polyline>
                        <line x1="12" y1="15" x2="12" y2="3"></line>
                      </svg>
                      Download CSV
                    </button>
                  </div>
                </div>
                
                {records.length === 0 ? (
                  <p className="no-records">No sensor data recorded yet. Waiting for ESP32 data...</p>
                ) : (() => {
                  const filteredRecords = getFilteredRecords();
                  return filteredRecords.length === 0 ? (
                    <p className="no-records">No records match the selected filters.</p>
                  ) : (
                    <div className="records-table-wrapper">
                      <table className="records-table">
                        <thead>
                          <tr>
                            <th>Time Stamp</th>
                            {appliedSensorTypes.temperature && <th>Temp (°C)</th>}
                            {appliedSensorTypes.humidity && <th>Humidity (%)</th>}
                            {appliedSensorTypes.pressure && <th>Pressure (hPa)</th>}
                            {appliedSensorTypes.vocs && <th>VOCs (kΩ)</th>}
                            {appliedSensorTypes.no2 && <th>NO₂ (PPM)</th>}
                            {appliedSensorTypes.co && <th>CO (PPM)</th>}
                            {appliedSensorTypes.pm25 && <th>PM2.5 (µg/m³)</th>}
                            {appliedSensorTypes.pm10 && <th>PM10 (µg/m³)</th>}
                            <th>AQI (PH BASED)</th>
                            <th>Status</th>
                            {userRole === 'superadmin' && (
                              <th style={{ minWidth: '100px', textAlign: 'center' }}>
                                Actions
                              </th>
                            )}
                          </tr>
                        </thead>
                        <tbody>
                          {filteredRecords.map((record, index) => {
                          // Calculate AQI first
                          const aqi = calculateAQI(record);
                          
                          // Determine status based on standard EPA AQI ranges
                          let status = 'good';
                          if (aqi.value >= 301) {
                            status = 'hazardous';  // Hazardous
                          } else if (aqi.value >= 201) {
                            status = 'very-unhealthy';  // Very Unhealthy
                          } else if (aqi.value >= 151) {
                            status = 'unhealthy'; // Unhealthy
                          } else if (aqi.value >= 101) {
                            status = 'unhealthy-sensitive'; // Unhealthy for Sensitive Groups
                          } else if (aqi.value >= 51) {
                            status = 'moderate'; // Moderate
                          } else {
                            status = 'good';    // Good (0-50)
                          }
                          
                          return (
                            <tr key={record.id}>
                              <td>{formatTimestamp(record.timestamp)}</td>
                              {appliedSensorTypes.temperature && <td>{record.temperature?.toFixed(1) || 'N/A'}</td>}
                              {appliedSensorTypes.humidity && <td>{record.humidity?.toFixed(1) || 'N/A'}</td>}
                              {appliedSensorTypes.pressure && <td>{record.pressure?.toFixed(2) || 'N/A'}</td>}
                              {appliedSensorTypes.vocs && <td>{record.vocs?.toFixed(1) || 'N/A'}</td>}
                              {appliedSensorTypes.no2 && <td>{record.nitrogen_dioxide?.toFixed(2) || 'N/A'}</td>}
                              {appliedSensorTypes.co && <td>{record.carbon_monoxide?.toFixed(2) || 'N/A'}</td>}
                              {appliedSensorTypes.pm25 && <td>{record.pm25?.toFixed(1) || 'N/A'}</td>}
                              {appliedSensorTypes.pm10 && <td>{record.pm10?.toFixed(1) || 'N/A'}</td>}
                              <td>
                                <span className="aqi-badge" style={{backgroundColor: aqi.color, color: aqi.textColor}}>
                                  {aqi.value}
                                </span>
                              </td>
                              <td>
                                <span className={`status-badge status-${status}`}>
                                  {status === 'good' ? 'Good' : 
                                   status === 'moderate' ? 'Moderate' :
                                   status === 'unhealthy-sensitive' ? 'Unhealthy for Sensitive' :
                                   status === 'unhealthy' ? 'Unhealthy' :
                                   status === 'very-unhealthy' ? 'Very Unhealthy' :
                                   status === 'hazardous' ? 'Hazardous' : status}
                                </span>
                              </td>
                              {userRole === 'superadmin' && (
                                <td style={{ whiteSpace: 'nowrap', width: '90px', minWidth: '90px', padding: '8px 6px' }}>
                                  <div style={{ display: 'flex', flexDirection: 'row', gap: '6px', alignItems: 'center', justifyContent: 'center', flexWrap: 'nowrap' }}>
                                    <button 
                                      onClick={() => openEditModal(record)}
                                      title="Edit record"
                                      style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: '32px', height: '32px', background: '#2196F3', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', flexShrink: 0 }}
                                    >
                                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                                      </svg>
                                    </button>
                                    <button 
                                      onClick={() => handleDeleteRecord(record.id)}
                                      title="Delete record"
                                      style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: '32px', height: '32px', background: '#f44336', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', flexShrink: 0 }}
                                    >
                                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                        <polyline points="3 6 5 6 21 6"></polyline>
                                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                                        <line x1="10" y1="11" x2="10" y2="17"></line>
                                        <line x1="14" y1="11" x2="14" y2="17"></line>
                                      </svg>
                                    </button>
                                  </div>
                                </td>
                              )}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )})()}
              </div>

              {/* Create Modal */}
              {showCreateModal && (
                <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
                  <div className="modal-content" onClick={(e) => e.stopPropagation()}>
                    <h2>Create New Sensor Record</h2>
                    <form onSubmit={handleCreateRecord}>
                      <div className="form-grid">
                        <div className="form-group">
                          <label>Temperature (°C)</label>
                          <input type="number" step="0.1" value={formData.temperature} 
                            onChange={(e) => setFormData({...formData, temperature: e.target.value})} />
                        </div>
                        <div className="form-group">
                          <label>Humidity (%)</label>
                          <input type="number" step="0.1" value={formData.humidity}
                            onChange={(e) => setFormData({...formData, humidity: e.target.value})} />
                        </div>
                        <div className="form-group">
                          <label>VOCs (kΩ)</label>
                          <input type="number" step="0.1" value={formData.vocs}
                            onChange={(e) => setFormData({...formData, vocs: e.target.value})} />
                        </div>
                        <div className="form-group">
                          <label>NO₂ (PPM)</label>
                          <input type="number" step="0.01" value={formData.nitrogen_dioxide}
                            onChange={(e) => setFormData({...formData, nitrogen_dioxide: e.target.value})} />
                        </div>
                        <div className="form-group">
                          <label>CO (PPM)</label>
                          <input type="number" step="0.01" value={formData.carbon_monoxide}
                            onChange={(e) => setFormData({...formData, carbon_monoxide: e.target.value})} />
                        </div>
                        <div className="form-group">
                          <label>PM2.5 (µg/m³)</label>
                          <input type="number" step="0.1" value={formData.pm25}
                            onChange={(e) => setFormData({...formData, pm25: e.target.value})} />
                        </div>
                        <div className="form-group">
                          <label>PM10 (µg/m³)</label>
                          <input type="number" step="0.1" value={formData.pm10}
                            onChange={(e) => setFormData({...formData, pm10: e.target.value})} />
                        </div>
                      </div>
                      <div className="modal-actions">
                        <button type="button" className="cancel-btn" onClick={() => setShowCreateModal(false)}>Cancel</button>
                        <button type="submit" className="submit-btn">Create</button>
                      </div>
                    </form>
                  </div>
                </div>
              )}

              {/* Edit Modal */}
              {showEditModal && (
                <div className="modal-overlay" onClick={() => setShowEditModal(false)}>
                  <div className="modal-content" onClick={(e) => e.stopPropagation()}>
                    <h2>Edit Sensor Record</h2>
                    <form onSubmit={handleUpdateRecord}>
                      <div className="form-grid">
                        <div className="form-group">
                          <label>Temperature (°C)</label>
                          <input type="number" step="0.1" value={formData.temperature}
                            onChange={(e) => setFormData({...formData, temperature: e.target.value})} />
                        </div>
                        <div className="form-group">
                          <label>Humidity (%)</label>
                          <input type="number" step="0.1" value={formData.humidity}
                            onChange={(e) => setFormData({...formData, humidity: e.target.value})} />
                        </div>
                        <div className="form-group">
                          <label>VOCs (kΩ)</label>
                          <input type="number" step="0.1" value={formData.vocs}
                            onChange={(e) => setFormData({...formData, vocs: e.target.value})} />
                        </div>
                        <div className="form-group">
                          <label>NO₂ (PPM)</label>
                          <input type="number" step="0.01" value={formData.nitrogen_dioxide}
                            onChange={(e) => setFormData({...formData, nitrogen_dioxide: e.target.value})} />
                        </div>
                        <div className="form-group">
                          <label>CO (PPM)</label>
                          <input type="number" step="0.01" value={formData.carbon_monoxide}
                            onChange={(e) => setFormData({...formData, carbon_monoxide: e.target.value})} />
                        </div>
                        <div className="form-group">
                          <label>PM2.5 (µg/m³)</label>
                          <input type="number" step="0.1" value={formData.pm25}
                            onChange={(e) => setFormData({...formData, pm25: e.target.value})} />
                        </div>
                        <div className="form-group">
                          <label>PM10 (µg/m³)</label>
                          <input type="number" step="0.1" value={formData.pm10}
                            onChange={(e) => setFormData({...formData, pm10: e.target.value})} />
                        </div>
                      </div>
                      <div className="modal-actions">
                        <button type="button" className="cancel-btn" onClick={() => setShowEditModal(false)}>Cancel</button>
                        <button type="submit" className="submit-btn">Update</button>
                      </div>
                    </form>
                  </div>
                </div>
              )}
            </section>
          )}

          {activePage === "graphs" && (
            <section className="graphs-page-container">
              {showGraphLoading && (
                <div className="graph-loading-overlay">
                  <TriangleLoader />
                </div>
              )}

              {/* Disclaimer */}
              <div className="data-disclaimer">
                <div className="disclaimer-icon"><InfoIcon /></div>
                <div className="disclaimer-content">
                  <strong>Note:</strong> Air quality sensors used in records and graphs pages are not reference grade. Hence the data provided is for indicative measurements only and should be interpreted accordingly.
                </div>
              </div>

              {/* Filters Section */}
              <div className="filters-container">
                <div className="filters-header">
                  <span className="filter-icon">▼</span> Filters
                </div>
                <div className="filters-content">
                  <div className="filter-group">
                    <label>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style={{display: 'inline', marginRight: '6px', verticalAlign: 'middle'}}>
                        <path d="M8.464 15.536a5 5 0 0 1 0-7.072m-2.828 9.9a9 9 0 0 1 0-12.728m9.9 9.9a5 5 0 0 0 0-7.072m2.828 9.9a9 9 0 0 0 0-12.728M13 12a1 1 0 1 1-2 0 1 1 0 0 1 2 0" stroke="#5b6b8d" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                      Sensor Types
                    </label>
                    <div className="custom-dropdown">
                      <div 
                        className="dropdown-header"
                        onClick={() => setGraphSensorDropdownOpen(!graphSensorDropdownOpen)}
                      >
                        <span>{getSelectedSensorNames(graphFilterSensorTypes)}</span>
                        <svg className="dropdown-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <polyline points={graphSensorDropdownOpen ? "18 15 12 9 6 15" : "6 9 12 15 18 9"}></polyline>
                        </svg>
                      </div>
                      {graphSensorDropdownOpen && (
                        <div className="dropdown-menu">
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={graphFilterSensorTypes.temperature}
                              onChange={() => toggleGraphSensorType('temperature')}
                            />
                            Temperature
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={graphFilterSensorTypes.humidity}
                              onChange={() => toggleGraphSensorType('humidity')}
                            />
                            Humidity
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={graphFilterSensorTypes.pressure}
                              onChange={() => toggleGraphSensorType('pressure')}
                            />
                            Pressure
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={graphFilterSensorTypes.vocs}
                              onChange={() => toggleGraphSensorType('vocs')}
                            />
                            VOCs
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={graphFilterSensorTypes.no2}
                              onChange={() => toggleGraphSensorType('no2')}
                            />
                            NO₂
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={graphFilterSensorTypes.co}
                              onChange={() => toggleGraphSensorType('co')}
                            />
                            CO
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={graphFilterSensorTypes.pm25}
                              onChange={() => toggleGraphSensorType('pm25')}
                            />
                            PM2.5
                          </label>
                          <label className="dropdown-item">
                            <input 
                              type="checkbox" 
                              checked={graphFilterSensorTypes.pm10}
                              onChange={() => toggleGraphSensorType('pm10')}
                            />
                            PM10
                          </label>
                          <div className="dropdown-divider"></div>
                          <label className="dropdown-item clear-item">
                            <input 
                              type="checkbox" 
                              checked={clearGraphFilters}
                              onChange={(e) => setClearGraphFilters(e.target.checked)}
                            />
                            🔄 Clear all filters
                          </label>
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="filter-group">
                    <label>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{display: 'inline', marginRight: '6px', verticalAlign: 'middle'}}>
                        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                        <line x1="16" y1="2" x2="16" y2="6"></line>
                        <line x1="8" y1="2" x2="8" y2="6"></line>
                        <line x1="3" y1="10" x2="21" y2="10"></line>
                      </svg>
                      Date
                    </label>
                    <select 
                      className="filter-select"
                      value={graphFilterDate}
                      onChange={(e) => {
                        setGraphFilterDate(e.target.value);
                        setAppliedGraphDate(e.target.value);
                        fetchGraphData();
                      }}
                    >
                      <option value="all">All Dates</option>
                      <option value="today">Today</option>
                      <option value="7days">Last 7 Days</option>
                      <option value="30days">Last 30 Days</option>
                    </select>
                  </div>
                  <button className="submit-filters-btn" onClick={handleClearGraphFilters}>Clear Filters</button>
                </div>
              </div>

              {!showGraphLoading && (
                <div className="graphs-content">
                  {graphData.length === 0 ? (
                    <p className="no-data">No data available yet. Waiting for sensor readings...</p>
                  ) : getFilteredGraphData().length === 0 ? (
                    <p className="no-data">No data matches the selected filters.</p>
                  ) : (
                  <div className="graphs-grid">
                    {/* Temperature Graph */}
                    {appliedGraphSensorTypes.temperature && (
                      <div className="graph-card">
                        <div className="graph-header">
                          <div className="graph-value">
                            {(() => {
                              const peak = getPeakValue('temperature');
                              const average = getAverageValue('temperature');
                              return peak !== null && average !== null ? (
                                <>
                                  <span className="current-value">{peak.toFixed(1)} °C</span>
                                  <span className="value-change">Peak</span>
                                  <span className="average-value">{average.toFixed(1)} °C avg</span>
                                </>
                              ) : '--';
                            })()}
                          </div>
                          <h3><Thermometer size={20} /> Temperature</h3>
                        </div>
                        <div style={{ width: '100%', height: '280px' }}>
                          <ResponsiveContainer debounce={300}>
                            <LineChart data={getFilteredGraphData()} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                              <XAxis 
                                dataKey="time" 
                                stroke="#999" 
                                tick={{ fontSize: 11, fill: '#999' }}
                                axisLine={false}
                                tickLine={false}
                              />
                              <YAxis 
                                stroke="#999" 
                                tick={{ fontSize: 11, fill: '#999' }}
                                axisLine={false}
                                tickLine={false}
                                domain={['auto', 'auto']}
                              />
                              <Tooltip 
                                contentStyle={{ 
                                  backgroundColor: 'rgba(255,255,255,0.95)', 
                                  border: '1px solid #ddd',
                                  borderRadius: '8px',
                                  padding: '10px'
                                }}
                                labelStyle={{ fontWeight: 'bold', marginBottom: '5px' }}
                                formatter={(value) => [value.toFixed(2), 'Temperature']}
                                labelFormatter={(label, payload) => {
                                  if (payload && payload[0]) {
                                    return payload[0].payload.fullTimestamp || label;
                                  }
                                  return label;
                                }}
                              />
                              <Line 
                                type="monotone" 
                                dataKey="temperature" 
                                stroke="#5b6b8d" 
                                strokeWidth={3}
                                dot={{ fill: '#5b6b8d', r: 5, strokeWidth: 0 }}
                                activeDot={{ r: 8, fill: '#5b6b8d' }}
                                isAnimationActive={false}
                              />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                      </div>
                    )}

                    {/* Humidity Graph */}
                    {appliedGraphSensorTypes.humidity && (
                      <div className="graph-card">
                        <div className="graph-header">
                          <div className="graph-value">
                            {(() => {
                              const peak = getPeakValue('humidity');
                              const average = getAverageValue('humidity');
                              return peak !== null && average !== null ? (
                                <>
                                  <span className="current-value">{peak.toFixed(1)} %</span>
                                  <span className="value-change">Peak</span>
                                  <span className="average-value">{average.toFixed(1)} % avg</span>
                                </>
                              ) : '--';
                            })()}
                          </div>
                          <h3><Droplet size={20} /> Humidity</h3>
                        </div>
                        <div style={{ width: '100%', height: '280px' }}>
                          <ResponsiveContainer debounce={300}>
                            <LineChart data={getFilteredGraphData()} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                              <XAxis 
                                dataKey="time" 
                                stroke="#999" 
                                tick={{ fontSize: 11, fill: '#999' }}
                                axisLine={false}
                                tickLine={false}
                              />
                              <YAxis 
                                stroke="#999" 
                                tick={{ fontSize: 11, fill: '#999' }}
                                axisLine={false}
                                tickLine={false}
                                domain={[0, 'auto']}
                              />
                              <Tooltip 
                                contentStyle={{ 
                                  backgroundColor: 'rgba(255,255,255,0.95)', 
                                  border: '1px solid #ddd',
                                  borderRadius: '8px',
                                  padding: '10px'
                                }}
                                labelStyle={{ fontWeight: 'bold', marginBottom: '5px' }}
                                formatter={(value) => [value.toFixed(2), 'Humidity']}
                                labelFormatter={(label, payload) => {
                                  if (payload && payload[0]) {
                                    return payload[0].payload.fullTimestamp || label;
                                  }
                                  return label;
                                }}
                              />
                              <Line 
                                type="monotone" 
                                dataKey="humidity" 
                                stroke="#5b6b8d" 
                                strokeWidth={3}
                                dot={{ fill: '#5b6b8d', r: 5, strokeWidth: 0 }}
                                activeDot={{ r: 8, fill: '#5b6b8d' }}
                                isAnimationActive={false}
                              />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                      </div>
                    )}

                    {/* Pressure Graph */}
                    {appliedGraphSensorTypes.pressure && (
                    <div className="graph-card">
                      <div className="graph-header">
                        <div className="graph-value">
                          {(() => {
                            const peak = getPeakValue('pressure');
                            const average = getAverageValue('pressure');
                            return peak !== null && average !== null ? (
                              <>
                                <span className="current-value">{peak.toFixed(2)} hPa</span>
                                <span className="value-change">Peak</span>
                                <span className="average-value">{average.toFixed(2)} hPa avg</span>
                              </>
                            ) : '--';
                          })()}
                        </div>
                        <h3><Zap size={20} /> Pressure</h3>
                      </div>
                      <div style={{ width: '100%', height: getChartHeight() }}>
                        <ResponsiveContainer debounce={300}>
                          <LineChart data={getFilteredGraphData()} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                            <XAxis 
                              dataKey="time" 
                              stroke="#999" 
                              tick={{ fontSize: isMobile ? 9 : 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                            />
                            <YAxis 
                              stroke="#999" 
                              tick={{ fontSize: isMobile ? 9 : 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                              domain={['auto', 'auto']}
                            />
                            <Tooltip 
                              contentStyle={{ 
                                backgroundColor: 'rgba(255,255,255,0.95)', 
                                border: '1px solid #ddd',
                                borderRadius: '8px',
                                padding: '10px'
                              }}
                              labelStyle={{ fontWeight: 'bold', marginBottom: '5px' }}
                              formatter={(value) => [value.toFixed(2), 'Pressure']}
                              labelFormatter={(label, payload) => {
                                if (payload && payload[0]) {
                                  return payload[0].payload.fullTimestamp || label;
                                }
                                return label;
                              }}
                            />
                            <Line 
                              type="monotone" 
                              dataKey="pressure" 
                              stroke="#5b6b8d" 
                              strokeWidth={3}
                              dot={{ fill: '#5b6b8d', r: 5, strokeWidth: 0 }}
                              activeDot={{ r: 8, fill: '#5b6b8d' }}
                              isAnimationActive={false}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                    )}

                    {/* VOCs Graph */}
                    {appliedGraphSensorTypes.vocs && (
                      <div className="graph-card">
                        <div className="graph-header">
                          <div className="graph-value">
                            {(() => {
                              const peak = getPeakValue('vocs');
                              return peak !== null ? (
                                <>
                                  <span className="current-value">{peak.toFixed(1)} kΩ</span>
                                  <span className="value-change">Peak</span>
                                </>
                              ) : '--';
                            })()}
                          </div>
                          <h3><Activity size={20} /> VOCs</h3>
                        </div>
                        <div style={{ width: '100%', height: '280px' }}>
                          <ResponsiveContainer debounce={300}>
                            <LineChart data={getFilteredGraphData()} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                              <XAxis 
                                dataKey="time" 
                                stroke="#999" 
                                tick={{ fontSize: 11, fill: '#999' }}
                                axisLine={false}
                                tickLine={false}
                              />
                              <YAxis 
                                stroke="#999" 
                                tick={{ fontSize: 11, fill: '#999' }}
                                axisLine={false}
                                tickLine={false}
                                domain={['auto', 'auto']}
                              />
                              <Tooltip 
                                contentStyle={{ 
                                  backgroundColor: 'rgba(255,255,255,0.95)', 
                                  border: '1px solid #ddd',
                                  borderRadius: '8px',
                                  padding: '10px'
                                }}
                                labelStyle={{ fontWeight: 'bold', marginBottom: '5px' }}
                                formatter={(value) => [value.toFixed(2), 'VOCs']}
                                labelFormatter={(label, payload) => {
                                  if (payload && payload[0]) {
                                    return payload[0].payload.fullTimestamp || label;
                                  }
                                  return label;
                                }}
                              />
                              <Line 
                                type="monotone" 
                                dataKey="vocs" 
                                stroke="#5b6b8d" 
                                strokeWidth={3}
                                dot={{ fill: '#5b6b8d', r: 5, strokeWidth: 0 }}
                                activeDot={{ r: 8, fill: '#5b6b8d' }}
                                isAnimationActive={false}
                              />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                      </div>
                    )}

                    {/* NO2 Graph */}
                    {appliedGraphSensorTypes.no2 && (
                    <div className="graph-card">
                      <div className="graph-header">
                        <div className="graph-value">
                          {(() => {
                            const peak = getPeakValue('no2');
                            return peak !== null ? (
                              <>
                                <span className="current-value">{peak.toFixed(2)} PPM</span>
                                <span className="value-change">Peak</span>
                              </>
                            ) : '--';
                          })()}
                        </div>
                        <h3><Wind size={20} /> Nitrogen Dioxide</h3>
                      </div>
                      <div style={{ width: '100%', height: '280px' }}>
                        <ResponsiveContainer debounce={300}>
                          <LineChart data={getFilteredGraphData()} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                            <XAxis 
                              dataKey="time" 
                              stroke="#999" 
                              tick={{ fontSize: 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                            />
                            <YAxis 
                              stroke="#999" 
                              tick={{ fontSize: 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                              domain={['auto', 'auto']}
                            />
                            <Tooltip 
                              contentStyle={{ 
                                backgroundColor: 'rgba(255,255,255,0.95)', 
                                border: '1px solid #ddd',
                                borderRadius: '8px',
                                padding: '10px'
                              }}
                              labelStyle={{ fontWeight: 'bold', marginBottom: '5px' }}
                              formatter={(value) => [value.toFixed(4), 'NO2']}
                              labelFormatter={(label, payload) => {
                                if (payload && payload[0]) {
                                  return payload[0].payload.fullTimestamp || label;
                                }
                                return label;
                              }}
                            />
                            <Line 
                              type="monotone" 
                              dataKey="no2" 
                              stroke="#5b6b8d" 
                              strokeWidth={3}
                              dot={{ fill: '#5b6b8d', r: 5, strokeWidth: 0 }}
                              activeDot={{ r: 8, fill: '#5b6b8d' }}
                              isAnimationActive={false}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                    )}

                    {/* CO Graph */}
                    {appliedGraphSensorTypes.co && (
                    <div className="graph-card">
                      <div className="graph-header">
                        <div className="graph-value">
                          {(() => {
                            const peak = getPeakValue('co');
                            return peak !== null ? (
                              <>
                                <span className="current-value">{peak.toFixed(2)} PPM</span>
                                <span className="value-change">Peak</span>
                              </>
                            ) : '--';
                          })()}
                        </div>
                        <h3><Flame size={20} /> Carbon Monoxide</h3>
                      </div>
                      <div style={{ width: '100%', height: '280px' }}>
                        <ResponsiveContainer debounce={300}>
                          <LineChart data={getFilteredGraphData()} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                            <XAxis 
                              dataKey="time" 
                              stroke="#999" 
                              tick={{ fontSize: 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                            />
                            <YAxis 
                              stroke="#999" 
                              tick={{ fontSize: 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                              domain={[(dataMin) => {
                                // Start from 80% of minimum value or 0
                                const minValue = Math.max(0, dataMin * 0.8);
                                return Math.floor(minValue * 1000) / 1000;
                              }, (dataMax) => {
                                // Add 20% padding to max value for better visibility
                                const maxValue = dataMax * 1.2;
                                return Math.ceil(maxValue * 1000) / 1000;
                              }]}
                            />
                            <Tooltip 
                              contentStyle={{ 
                                backgroundColor: 'rgba(255,255,255,0.95)', 
                                border: '1px solid #ddd',
                                borderRadius: '8px',
                                padding: '10px'
                              }}
                              labelStyle={{ fontWeight: 'bold', marginBottom: '5px' }}
                              formatter={(value) => [value.toFixed(4), 'CO']}
                              labelFormatter={(label, payload) => {
                                if (payload && payload[0]) {
                                  return payload[0].payload.fullTimestamp || label;
                                }
                                return label;
                              }}
                            />
                            <Line 
                              type="monotone" 
                              dataKey="co" 
                              stroke="#5b6b8d" 
                              strokeWidth={3}
                              dot={{ fill: '#5b6b8d', r: 5, strokeWidth: 0 }}
                              activeDot={{ r: 8, fill: '#5b6b8d' }}
                              isAnimationActive={false}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                    )}

                    {/* PM2.5 Graph */}
                    {appliedGraphSensorTypes.pm25 && (
                    <div className="graph-card">
                      <div className="graph-header">
                        <div className="graph-value">
                          {(() => {
                            const peak = getPeakValue('pm25');
                            return peak !== null ? (
                              <>
                                <span className="current-value">{peak.toFixed(1)} µg/m³</span>
                                <span className="value-change">Peak</span>
                              </>
                            ) : '--';
                          })()}
                        </div>
                        <h3><Circle size={20} /> PM 2.5</h3>
                      </div>
                      <div style={{ width: '100%', height: '280px' }}>
                        <ResponsiveContainer debounce={300}>
                          <LineChart data={getFilteredGraphData()} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                            <XAxis 
                              dataKey="time" 
                              stroke="#999" 
                              tick={{ fontSize: 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                            />
                            <YAxis 
                              stroke="#999" 
                              tick={{ fontSize: 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                              domain={['auto', 'auto']}
                            />
                            <Tooltip 
                              contentStyle={{ 
                                backgroundColor: 'rgba(255,255,255,0.95)', 
                                border: '1px solid #ddd',
                                borderRadius: '8px',
                                padding: '10px'
                              }}
                              labelStyle={{ fontWeight: 'bold', marginBottom: '5px' }}
                              formatter={(value) => [value.toFixed(2), 'PM2.5']}
                              labelFormatter={(label, payload) => {
                                if (payload && payload[0]) {
                                  return payload[0].payload.fullTimestamp || label;
                                }
                                return label;
                              }}
                            />
                            <Line 
                              type="monotone" 
                              dataKey="pm25" 
                              stroke="#5b6b8d" 
                              strokeWidth={3}
                              dot={{ fill: '#5b6b8d', r: 5, strokeWidth: 0 }}
                              activeDot={{ r: 8, fill: '#5b6b8d' }}
                              isAnimationActive={false}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                    )}

                    {/* PM10 Graph */}
                    {appliedGraphSensorTypes.pm10 && (
                    <div className="graph-card">
                      <div className="graph-header">
                        <div className="graph-value">
                          {(() => {
                            const peak = getPeakValue('pm10');
                            return peak !== null ? (
                              <>
                                <span className="current-value">{peak.toFixed(1)} µg/m³</span>
                                <span className="value-change">Peak</span>
                              </>
                            ) : '--';
                          })()}
                        </div>
                        <h3><Circle size={20} /> PM 10</h3>
                      </div>
                      <div style={{ width: '100%', height: '280px' }}>
                        <ResponsiveContainer debounce={300}>
                          <LineChart data={getFilteredGraphData()} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                            <XAxis 
                              dataKey="time" 
                              stroke="#999" 
                              tick={{ fontSize: 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                            />
                            <YAxis 
                              stroke="#999" 
                              tick={{ fontSize: 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                              domain={['auto', 'auto']}
                            />
                            <Tooltip 
                              contentStyle={{ 
                                backgroundColor: 'rgba(255,255,255,0.95)', 
                                border: '1px solid #ddd',
                                borderRadius: '8px',
                                padding: '10px'
                              }}
                              labelStyle={{ fontWeight: 'bold', marginBottom: '5px' }}
                              formatter={(value) => [value.toFixed(2), 'PM10']}
                              labelFormatter={(label, payload) => {
                                if (payload && payload[0]) {
                                  return payload[0].payload.fullTimestamp || label;
                                }
                                return label;
                              }}
                            />
                            <Line 
                              type="monotone" 
                              dataKey="pm10" 
                              stroke="#5b6b8d" 
                              strokeWidth={3}
                              dot={{ fill: '#5b6b8d', r: 5, strokeWidth: 0 }}
                              activeDot={{ r: 8, fill: '#5b6b8d' }}
                              isAnimationActive={false}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                    )}
                    
                    {/* PM2.5/PM10 vs Smoke Events Correlation Graph */}
                    <div className="graph-card correlation-graph">
                      <div className="graph-header">
                        <div className="graph-value">
                          <span className="current-value">Correlation</span>
                          <span className="value-change">PM vs Smoke</span>
                        </div>
                      </div>
                      <div style={{ width: '100%', height: '280px' }}>
                        <ResponsiveContainer debounce={300}>
                          <LineChart data={correlationData} margin={{ top: 10, right: 20, left: 0, bottom: 60 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                            <XAxis 
                              dataKey="dateTime" 
                              stroke="#999" 
                              tick={{ fontSize: 9, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                              angle={-45}
                              textAnchor="end"
                              height={60}
                            />
                            <YAxis 
                              yAxisId="pm"
                              stroke="#999" 
                              tick={{ fontSize: 11, fill: '#999' }}
                              axisLine={false}
                              tickLine={false}
                              domain={['auto', 'auto']}
                              label={{ value: 'PM (µg/m³)', angle: -90, position: 'insideLeft' }}
                            />
                            <YAxis 
                              yAxisId="smoke"
                              orientation="right"
                              stroke="#ff6b35" 
                              tick={{ fontSize: 11, fill: '#ff6b35' }}
                              axisLine={false}
                              tickLine={false}
                              domain={[0, 'auto']}
                              label={{ value: 'Smoke Events', angle: 90, position: 'insideRight' }}
                            />
                            <Tooltip 
                              contentStyle={{ 
                                backgroundColor: 'rgba(255,255,255,0.95)', 
                                border: '1px solid #ddd',
                                borderRadius: '8px',
                                padding: '10px'
                              }}
                              labelStyle={{ fontWeight: 'bold', marginBottom: '5px' }}
                              formatter={(value, name) => {
                                if (name === 'PM2.5') return [value.toFixed(2), 'PM2.5 (µg/m³)'];
                                if (name === 'PM10') return [value.toFixed(2), 'PM10 (µg/m³)'];
                                if (name === 'Smoke Events') return [value, 'Smoke Events'];
                                return [value, name];
                              }}
                              labelFormatter={(label, payload) => {
                                if (payload && payload[0]) {
                                  const data = payload[0].payload;
                                  return `${data.date} ${data.time}${data.is_real_event ? ' (Historical Smoke Event)' : ' (Current Trend)'}`;
                                }
                                return label;
                              }}
                            />
                            <Legend />
                            <Line 
                              yAxisId="pm"
                              type="monotone" 
                              dataKey="pm25" 
                              stroke="#5b6b8d" 
                              strokeWidth={2}
                              dot={{ fill: '#5b6b8d', r: 3, strokeWidth: 0 }}
                              activeDot={{ r: 6, fill: '#5b6b8d' }}
                              name="PM2.5"
                              isAnimationActive={false}
                            />
                            <Line 
                              yAxisId="pm"
                              type="monotone" 
                              dataKey="pm10" 
                              stroke="#4caf50" 
                              strokeWidth={2}
                              dot={{ fill: '#4caf50', r: 3, strokeWidth: 0 }}
                              activeDot={{ r: 6, fill: '#4caf50' }}
                              name="PM10"
                              isAnimationActive={false}
                            />
                            <Line 
                              yAxisId="smoke"
                              type="monotone" 
                              dataKey="smoke_events" 
                              stroke="#ff6b35" 
                              strokeWidth={3}
                              dot={{ fill: '#ff6b35', r: 4, strokeWidth: 0 }}
                              activeDot={{ r: 8, fill: '#ff6b35' }}
                              name="Smoke Events"
                              isAnimationActive={false}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  </div>
                )}
              </div>
              )}
            </section>
          )}

          {activePage === "info" && (
            <section className="info-page-container">
              <div className="info-content">
                <h1 className="info-title">About SMOKi Air Quality Monitor</h1>
              
                <div className="info-section">
                  <h2>Monitored Parameters</h2>
                  
                  <div className="parameter-card">
                    <div className="parameter-header">
                      <Thermometer size={24} />
                      <h3>Temperature</h3>
                    </div>
                    <p>Measures ambient temperature in degrees Celsius. Optimal indoor temperature ranges from 20-24°C for comfort and health.</p>
                  </div>

                  <div className="parameter-card">
                    <div className="parameter-header">
                      <Droplet size={24} />
                      <h3>Humidity</h3>
                    </div>
                    <p>Tracks relative humidity percentage. Ideal indoor humidity should be between 30-50% to prevent mold growth and respiratory issues.</p>
                  </div>

                  <div className="parameter-card">
                    <div className="parameter-header">
                      <Activity size={24} />
                      <h3>VOCs (Volatile Organic Compounds)</h3>
                    </div>
                    <p>Detects harmful organic chemicals in the air from paints, cleaners, and building materials. Lower resistance values indicate higher VOC concentrations.</p>
                  </div>

                  <div className="parameter-card">
                    <div className="parameter-header">
                      <Wind size={24} />
                      <h3>Nitrogen Dioxide (NO₂)</h3>
                    </div>
                    <p>Monitors NO₂ levels in PPM. This gas comes from combustion processes. Safe levels are below 0.053 PPM; levels above 0.1 PPM are hazardous.</p>
                  </div>

                  <div className="parameter-card">
                    <div className="parameter-header">
                      <Flame size={24} />
                      <h3>Carbon Monoxide (CO)</h3>
                    </div>
                    <p>Tracks CO concentration in PPM. This odorless, colorless gas is deadly at high concentrations. Safe levels are below 4.4 PPM.</p>
                  </div>

                  <div className="parameter-card">
                    <div className="parameter-header">
                      <Circle size={24} />
                      <h3>PM2.5 (Fine Particulate Matter)</h3>
                    </div>
                    <p>Measures particles smaller than 2.5 micrometers. These can penetrate deep into lungs. Safe levels are below 12 µg/m³; above 35 µg/m³ is unhealthy.</p>
                  </div>

                  <div className="parameter-card">
                    <div className="parameter-header">
                      <Circle size={24} />
                      <h3>PM10 (Coarse Particulate Matter)</h3>
                    </div>
                    <p>Tracks particles smaller than 10 micrometers from dust, pollen, and mold. Safe levels are below 54 µg/m³; above 154 µg/m³ is unhealthy.</p>
                  </div>
                </div>

                <div className="info-section">
                  <h2>Air Quality Index (AQI)</h2>
                  <p>
                    The system calculates indicative AQI based on DENR-EMB computation standards. AQI is a standardized indicator 
                    of air quality that considers all monitored pollutants and reports the worst value:
                  </p>
                  <div className="aqi-legend">
                    <div className="aqi-item" style={{ backgroundColor: '#4caf50' }}>
                      <strong>0-50: Good</strong>
                      <span>Air quality is satisfactory</span>
                    </div>
                    <div className="aqi-item" style={{ backgroundColor: '#ffc107' }}>
                      <strong>51-100: Moderate</strong>
                      <span>Acceptable for most people</span>
                    </div>
                    <div className="aqi-item" style={{ backgroundColor: '#ff9800' }}>
                      <strong>101-150: Unhealthy for Sensitive</strong>
                      <span>May affect sensitive groups</span>
                    </div>
                    <div className="aqi-item" style={{ backgroundColor: '#f44336', color: 'white' }}>
                      <strong>151-200: Unhealthy</strong>
                      <span>Everyone may experience effects</span>
                    </div>
                    <div className="aqi-item" style={{ backgroundColor: '#9c27b0', color: 'white' }}>
                      <strong>201-300: Very Unhealthy</strong>
                      <span>Health alert for everyone</span>
                    </div>
                    <div className="aqi-item" style={{ backgroundColor: '#7b1fa2', color: 'white' }}>
                      <strong>301-500: Hazardous</strong>
                      <span>Emergency conditions</span>
                    </div>
                  </div>
                </div>

                <div className="info-section">
                  <h2>Need Help?</h2>
                  <p>
                    If you have any questions, issues, or need technical support with your SMOKi air quality 
                    monitoring system, our team is here to help.
                  </p>
                  <a href="mailto:support@smoki.com?subject=SMOKi Support Request" className="contact-button">
                    <span>📧</span>
                    <span>Email Us for Support</span>
                  </a>
                  <p className="contact-note">
                    Please include details about your issue and any error messages you're seeing.
                  </p>
                </div>
              </div>
            </section>
          )}
      </main>

      {/* Bottom Navigation - Mobile Only */}
      <nav className="bottom-nav">
        <button 
          onClick={(e) => {
            const target = e.currentTarget;
            target.classList.remove('clicked', 'loading');
            void target.offsetWidth;
            
            target.classList.add('loading');
            setTimeout(() => {
              target.classList.remove('loading');
              target.classList.add('clicked');
              setTimeout(() => {
                target.classList.remove('clicked');
              }, 400);
            }, 10);
            setActivePage("dashboard");
          }}
          className={`bottom-nav-item ${activePage === "dashboard" ? "active" : ""}`}
        >
          <Home size={24} />
          <span>Dashboard</span>
        </button>

        <button 
          onClick={(e) => {
            const target = e.currentTarget;
            target.classList.remove('clicked', 'loading');
            void target.offsetWidth;
            
            target.classList.add('loading');
            setTimeout(() => {
              target.classList.remove('loading');
              target.classList.add('clicked');
              setTimeout(() => {
                target.classList.remove('clicked');
              }, 400);
            }, 10);
            setActivePage("records");
          }}
          className={`bottom-nav-item ${activePage === "records" ? "active" : ""}`}
        >
          <FileText size={24} />
          <span>Records</span>
        </button>

        <button 
          onClick={(e) => {
            const target = e.currentTarget;
            target.classList.remove('clicked', 'loading');
            void target.offsetWidth;
            
            target.classList.add('loading');
            setTimeout(() => {
              target.classList.remove('loading');
              target.classList.add('clicked');
              setTimeout(() => {
                target.classList.remove('clicked');
              }, 400);
            }, 10);
            setActivePage("graphs");
          }}
          className={`bottom-nav-item ${activePage === "graphs" ? "active" : ""}`}
        >
          <TrendingUp size={24} />
          <span>Graphs</span>
        </button>

        <button 
          onClick={(e) => {
            const target = e.currentTarget;
            target.classList.remove('clicked', 'loading');
            void target.offsetWidth;
            
            target.classList.add('loading');
            setTimeout(() => {
              target.classList.remove('loading');
              target.classList.add('clicked');
              setTimeout(() => {
                target.classList.remove('clicked');
              }, 400);
            }, 10);
            setActivePage("sensors");
          }}
          className={`bottom-nav-item ${activePage === "sensors" ? "active" : ""}`}
        >
          <Zap size={24} />
          <span>Sensors</span>
        </button>

        <button 
          onClick={(e) => {
            const target = e.currentTarget;
            target.classList.remove('clicked', 'loading');
            void target.offsetWidth;
            
            target.classList.add('loading');
            setTimeout(() => {
              target.classList.remove('loading');
              target.classList.add('clicked');
              setTimeout(() => {
                target.classList.remove('clicked');
              }, 400);
            }, 10);
            setActivePage("info");
          }}
          className={`bottom-nav-item ${activePage === "info" ? "active" : ""}`}
        >
          <FileText size={24} />
          <span>Info</span>
        </button>
      </nav>
    </div>
  )
}

export default Dashboard







