#!/usr/bin/env python3
"""
HTML Report Generator for SMOKi Detection System
Generates detailed HTML reports with current frame and detection data
"""
import os
import base64
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional
import requests
from pathlib import Path
from frame_storage import frame_storage

class SMOKiReportGenerator:
    """Generate HTML reports for SMOKi detection events"""
    
    def __init__(self, api_base_url: str = "https://smoki-backend-rpi.onrender.com"):
        self.api_base_url = api_base_url
        # Save reports in a more accessible location
        self.reports_dir = Path("reports")
        self.reports_dir.mkdir(exist_ok=True)
        
        # Also create a local copy in the current directory for easy access
        self.local_reports_dir = Path("./generated_reports")
        self.local_reports_dir.mkdir(exist_ok=True)
    
    def get_current_frame_and_data(self) -> Dict:
        """Get current frame and detection data from the local stream manager"""
        try:
            # Import here to avoid circular imports
            try:
                from stream import stream_manager
            except ImportError:
                from backend.stream import stream_manager
            
            # Get current frame from local stream manager
            frame_data = None
            latest_frame = stream_manager.get_latest_frame()
            if latest_frame:
                frame_data = base64.b64encode(latest_frame).decode('utf-8')
            
            # Get latest violations from stream manager
            latest_violations = stream_manager.get_latest_violations()
            
            print(f"[REPORT DEBUG] Retrieved {len(latest_violations)} violations from stream manager")
            
            # Get current detection data from stream manager
            detection_data = {
                'status': 'active',
                'fps': getattr(stream_manager, 'fps', 1),
                'buffered_frames': len(getattr(stream_manager, 'frames', [])),
                'latest_frame_size': len(latest_frame) if latest_frame else 0,
                'latest_detections': getattr(stream_manager, 'latest_detections', []),
                'detection_summary': self._calculate_detection_summary(getattr(stream_manager, 'latest_detections', [])),
                'camera_info': {
                    'camera_id': 'SMOKi_Camera_01',
                    'location': 'Main Camera Station',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            }
            
            return {
                'frame_data': frame_data,
                'detection_data': detection_data,
                'violations': latest_violations,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            print(f"Error fetching current data from stream manager: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to API call
            return self._get_data_from_api()
    
    def _get_data_from_api(self) -> Dict:
        """Fallback method to get data from API"""
        try:
            # Get current frame
            frame_response = requests.get(f"{self.api_base_url}/api/stream/latest.jpg", timeout=10)
            frame_data = None
            if frame_response.status_code == 200:
                frame_data = base64.b64encode(frame_response.content).decode('utf-8')
            
            # Get current detection status
            status_response = requests.get(f"{self.api_base_url}/api/stream/status", timeout=10)
            detection_data = {}
            if status_response.status_code == 200:
                detection_data = status_response.json()
            
            return {
                'frame_data': frame_data,
                'detection_data': detection_data,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            print(f"Error fetching current data from API: {e}")
            return {
                'frame_data': None,
                'detection_data': {},
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': str(e)
            }
    
    def _calculate_detection_summary(self, detections: list) -> Dict:
        """Calculate detection summary from detections list"""
        summary = {
            'total_detections': len(detections),
            'smoke_detections': 0,
            'vehicle_detections': 0,
            'plate_detections': 0,
            'violation_detections': 0
        }
        
        for detection in detections:
            class_name = detection.get('class_name', '').lower()
            model_name = detection.get('model_name', '').lower()
            
            if 'smoke' in class_name or 'smoke' in model_name:
                summary['smoke_detections'] += 1
            elif class_name in ['passenger', 'puv', 'services', 'two_wheel'] or 'vehicle' in model_name:
                summary['vehicle_detections'] += 1
            elif 'license' in class_name or 'plate' in class_name or 'plate' in model_name:
                summary['plate_detections'] += 1
        
        # Also check for violations in the data
        violations = self._get_recent_violations()
        summary['violation_detections'] = len(violations)
        
        return summary
    
    def _get_recent_violations(self) -> List[Dict]:
        """Get recent violations from evidence directory"""
        try:
            evidence_dirs = [
                Path("D:/embed/SMOKI/esp32/evidence"),
                Path("esp32/evidence"),
                Path("../esp32/evidence"),
                Path("backend/detection_frames/evidence")
            ]
            
            violations = []
            
            for evidence_dir in evidence_dirs:
                if not evidence_dir.exists():
                    continue
                
                # Get violation evidence files from the last 24 hours
                from datetime import datetime, timedelta
                cutoff_time = datetime.now() - timedelta(hours=24)
                
                for evidence_file in evidence_dir.glob("violation_evidence_*.jpg"):
                    try:
                        # Check file modification time
                        file_time = datetime.fromtimestamp(evidence_file.stat().st_mtime)
                        if file_time > cutoff_time:
                            # Read metadata if available
                            metadata_file = evidence_file.with_suffix('.json')
                            if metadata_file.exists():
                                with open(metadata_file, 'r') as f:
                                    metadata = json.load(f)
                                    violations.append(metadata)
                    except Exception as e:
                        continue
                
                # Only use the first directory that has files
                if violations:
                    break
            
            return violations
            
        except Exception as e:
            print(f"[REPORT] Error getting recent violations: {e}")
            return []
    
    def generate_html_report(self, report_data: Dict, report_type: str = "general", vehicle_data: Optional[Dict] = None) -> str:
        """Generate HTML report with current frame, detection data, and violation evidence"""
        
        timestamp = datetime.now(timezone.utc)
        report_id = f"SMOKi_Report_{timestamp.strftime('%Y%m%d_%H%M%S')}"
        
        # Extract detection information
        detections = report_data.get('detection_data', {}).get('latest_detections', [])
        detection_summary = report_data.get('detection_data', {}).get('detection_summary', {})
        camera_info = report_data.get('detection_data', {}).get('camera_info', {})
        
        # Use violations from report data
        violations = report_data.get('violations', [])
        
        # Count detections by type with proper logic
        smoke_count = detection_summary.get('smoke_detections', 0)
        vehicle_count = detection_summary.get('vehicle_detections', 0) 
        plate_count = detection_summary.get('plate_detections', 0)
        violation_count = detection_summary.get('violation_detections', len(violations))
        
        # If we have violations data, use that count
        if violations:
            violation_count = len(violations)
        
        # Get total evidence files for more accurate reporting
        evidence_stats = self._get_evidence_statistics()
        total_evidence_files = evidence_stats.get('total_files', 0)
        recent_violations = evidence_stats.get('recent_violations', 0)
        
        # Determine report severity
        severity = "LOW"
        severity_color = "#28a745"
        if violation_count > 0:
            severity = "HIGH"
            severity_color = "#dc3545"
        elif smoke_count > 0:
            severity = "MEDIUM"
            severity_color = "#ffc107"
        elif vehicle_count > 0:
            severity = "LOW"
            severity_color = "#28a745"
        
        # Evidence gallery removed — evidence is reviewed via the local frontend modal
        evidence_gallery_html = ""
        
        # Generate violation evidence HTML
        violation_evidence_html = ""
        if violations:
            violation_evidence_html = "<h3>🚨 Violation Evidence</h3><div class='violation-grid'>"
            for i, violation in enumerate(violations):
                evidence_path = violation.get('evidence_path', '')
                license_plate = violation.get('license_plate', 'Unknown')
                vehicle_type = violation.get('vehicle_type', 'Unknown')
                smoke_type = violation.get('smoke_type', 'Unknown')
                distance = violation.get('distance', 0)
                has_readable_plate = violation.get('has_readable_plate', False)
                
                # Try to read and encode the evidence image
                evidence_image_html = ""
                if evidence_path and os.path.exists(evidence_path):
                    try:
                        with open(evidence_path, 'rb') as img_file:
                            img_data = base64.b64encode(img_file.read()).decode('utf-8')
                            evidence_image_html = f"""
                            <div class="evidence-image">
                                <img src="data:image/jpeg;base64,{img_data}" 
                                     alt="Violation evidence for {license_plate}" 
                                     class="violation-frame">
                            </div>
                            """
                    except Exception as e:
                        evidence_image_html = f"<p class='error'>Could not load evidence image: {e}</p>"
                else:
                    evidence_image_html = "<p class='no-evidence'>Evidence image not available</p>"
                
                plate_status = "✅ Readable" if has_readable_plate else "⚠️ Unreadable"
                plate_class = "readable" if has_readable_plate else "unreadable"
                
                violation_evidence_html += f"""
                <div class="violation-item">
                    <div class="violation-header">
                        <h4>Violation #{i+1}: {license_plate}</h4>
                        <span class="plate-status {plate_class}">{plate_status}</span>
                    </div>
                    {evidence_image_html}
                    <div class="violation-details">
                        <p><strong>Vehicle:</strong> {vehicle_type}</p>
                        <p><strong>Smoke Type:</strong> {smoke_type}</p>
                        <p><strong>Distance:</strong> {distance:.1f}px</p>
                        <p><strong>License Plate:</strong> {license_plate}</p>
                    </div>
                </div>
                """
            violation_evidence_html += "</div>"
        
        # Generate detection details HTML
        detection_details_html = ""
        if detections:
            detection_details_html = "<h3>Detection Details</h3><div class='detection-grid'>"
            for i, detection in enumerate(detections[:10]):  # Limit to 10 detections
                class_name = detection.get('class_name', 'Unknown')
                confidence = detection.get('confidence', 0)
                detection_type = "Unknown"
                
                if 'smoke' in class_name.lower():
                    detection_type = "Smoke Detection"
                    icon = "🔥"
                elif class_name.lower() in ['passenger', 'puv', 'services', 'two_wheel']:
                    detection_type = "Vehicle Detection"
                    icon = "🚗"
                elif 'license' in class_name.lower() or 'plate' in class_name.lower():
                    detection_type = "License Plate"
                    icon = "🔢"
                else:
                    icon = "📍"
                
                detection_details_html += f"""
                <div class="detection-item">
                    <div class="detection-icon">{icon}</div>
                    <div class="detection-info">
                        <strong>{detection_type}</strong><br>
                        <span class="detection-class">{class_name}</span><br>
                        <span class="detection-confidence">Confidence: {confidence:.1%}</span>
                    </div>
                </div>
                """
            detection_details_html += "</div>"
        else:
            detection_details_html = "<p>No active detections at the time of report generation.</p>"
        
        # Generate frame HTML
        frame_html = ""
        if report_data.get('frame_data'):
            # Determine frame title and context based on report type
            frame_title = "Current Frame"
            frame_context = ""
            
            if report_data.get('detection_specific'):
                frame_title = "Detection Frame"
                detection_time = report_data.get('detection_data', {}).get('original_detection_time', 'Unknown')
                detection_type = report_data.get('detection_data', {}).get('detection_type', 'Unknown')
                is_live = report_data.get('detection_data', {}).get('is_live_detection', False)
                time_since = report_data.get('detection_data', {}).get('time_since_detection', 'Unknown')
                
                if is_live:
                    frame_context = f"<p class='detection-context'><strong>Live {detection_type} Detection</strong> at {detection_time} ({time_since})</p>"
                else:
                    frame_context = f"<p class='detection-context'><strong>Historical {detection_type} Detection</strong> at {detection_time} ({time_since})</p>"
            elif report_data.get('violations') and len(report_data['violations']) > 0:
                frame_title = "Violation Frame"
                violation_time = report_data['violations'][0].get('created_at', 'Unknown')
                frame_context = f"<p class='violation-context'>Frame from violation at: {violation_time}</p>"
            
            frame_html = f"""
            <div class="frame-container">
                <h3>{frame_title}</h3>
                {frame_context}
                <img src="data:image/jpeg;base64,{report_data['frame_data']}" 
                     alt="{frame_title.lower()} with detections" 
                     class="camera-frame">
                <p class="frame-caption">
                    Frame captured at {timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')} 
                    from {camera_info.get('location', 'Main Camera Station')}
                </p>
            </div>
            """
        else:
            frame_title = "Detection Frame" if report_data.get('detection_specific') else "Current Frame"
            frame_html = f"""
            <div class="frame-container">
                <h3>{frame_title}</h3>
                <div class="no-frame">
                    <p>⚠️ Frame not available at the time of report generation</p>
                </div>
            </div>
            """
        
        # Generate HTML report
        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SMOKi Detection Report - {report_id}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
            color: #333;
        }}
        .report-container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .report-header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        .report-header h1 {{
            margin: 0;
            font-size: 2.5em;
            font-weight: 300;
        }}
        .report-header .subtitle {{
            margin: 10px 0 0 0;
            font-size: 1.2em;
            opacity: 0.9;
        }}
        .report-content {{
            padding: 30px;
        }}
        .report-meta {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .meta-card {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }}
        .meta-card h3 {{
            margin: 0 0 10px 0;
            color: #667eea;
            font-size: 1.1em;
        }}
        .meta-card p {{
            margin: 5px 0;
            font-size: 0.95em;
        }}
        .severity-badge {{
            display: inline-block;
            padding: 8px 16px;
            border-radius: 20px;
            color: white;
            font-weight: bold;
            font-size: 0.9em;
            background-color: {severity_color};
        }}
        .frame-container {{
            margin: 30px 0;
            text-align: center;
        }}
        .camera-frame {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            border: 2px solid #e9ecef;
        }}
        .frame-caption {{
            margin: 15px 0 0 0;
            color: #6c757d;
            font-size: 0.9em;
        }}
        .no-frame {{
            padding: 40px;
            background: #f8f9fa;
            border-radius: 8px;
            border: 2px dashed #dee2e6;
            color: #6c757d;
        }}
        .detection-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }}
        .detection-item {{
            display: flex;
            align-items: center;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 8px;
            border-left: 4px solid #28a745;
        }}
        .detection-icon {{
            font-size: 2em;
            margin-right: 15px;
        }}
        .detection-info {{
            flex: 1;
        }}
        .detection-class {{
            color: #6c757d;
            font-size: 0.9em;
        }}
        .detection-confidence {{
            color: #28a745;
            font-weight: bold;
            font-size: 0.9em;
        }}
        .violation-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .violation-item {{
            background: #fff5f5;
            border: 2px solid #fed7d7;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .violation-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid #fed7d7;
        }}
        .violation-header h4 {{
            margin: 0;
            color: #c53030;
            font-size: 1.2em;
        }}
        .plate-status {{
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.8em;
            font-weight: bold;
        }}
        .plate-status.readable {{
            background: #c6f6d5;
            color: #22543d;
        }}
        .plate-status.unreadable {{
            background: #fed7d7;
            color: #c53030;
        }}
        .evidence-image {{
            text-align: center;
            margin: 15px 0;
        }}
        .violation-frame {{
            max-width: 100%;
            height: auto;
            border-radius: 6px;
            border: 2px solid #e53e3e;
            box-shadow: 0 2px 8px rgba(229, 62, 62, 0.2);
        }}
        .violation-details {{
            background: #f7fafc;
            padding: 15px;
            border-radius: 6px;
            margin-top: 15px;
        }}
        .violation-details p {{
            margin: 8px 0;
            font-size: 0.9em;
        }}
        .violation-details strong {{
            color: #2d3748;
        }}
        .no-evidence {{
            text-align: center;
            padding: 20px;
            color: #718096;
            font-style: italic;
        }}
        .error {{
            color: #e53e3e;
            font-size: 0.9em;
            text-align: center;
            padding: 10px;
        }}
        .evidence-gallery-section {{
            margin: 30px 0;
            padding: 25px;
            background: #f8f9fa;
            border-radius: 10px;
            border-left: 5px solid #28a745;
        }}
        .gallery-description {{
            background: #e3f2fd;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            border-left: 4px solid #2196f3;
        }}
        .gallery-description p {{
            margin: 8px 0;
            color: #1565c0;
        }}
        .gallery-description strong {{
            color: #0d47a1;
        }}
        .evidence-header {{
            text-align: center;
            margin-bottom: 25px;
        }}
        .evidence-stats {{
            display: flex;
            justify-content: center;
            gap: 20px;
            margin: 20px 0;
            flex-wrap: wrap;
        }}
        .stat-item {{
            background: white;
            padding: 15px 20px;
            border-radius: 10px;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            border: 2px solid #e9ecef;
            transition: all 0.3s ease;
        }}
        .stat-item:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.15);
        }}
        .stat-number {{
            display: block;
            font-size: 2em;
            font-weight: bold;
            color: #007bff;
        }}
        .stat-label {{
            font-size: 0.9em;
            color: #6c757d;
            margin-top: 5px;
        }}
        .evidence-controls {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            border: 1px solid #dee2e6;
        }}
        .selection-controls {{
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }}
        .control-btn {{
            padding: 10px 16px;
            border: 2px solid #007bff;
            background: white;
            color: #007bff;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.9em;
            font-weight: 600;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            gap: 5px;
        }}
        .control-btn:hover {{
            background: #007bff;
            color: white;
            transform: translateY(-1px);
        }}
        .control-btn.select-all {{
            border-color: #28a745;
            color: #28a745;
        }}
        .control-btn.select-all:hover {{
            background: #28a745;
            color: white;
        }}
        .control-btn.deselect-all {{
            border-color: #dc3545;
            color: #dc3545;
        }}
        .control-btn.deselect-all:hover {{
            background: #dc3545;
            color: white;
        }}
        .selection-info {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            border: 1px solid #e9ecef;
        }}
        .selection-counter {{
            font-weight: 600;
            color: #495057;
            font-size: 1.1em;
            margin-bottom: 5px;
        }}
        .selection-details {{
            font-size: 0.9em;
            color: #6c757d;
        }}
        .evidence-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            gap: 25px;
            margin: 25px 0;
        }}
        .evidence-card {{
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            border: 2px solid #e9ecef;
            transition: all 0.3s ease;
        }}
        .evidence-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 8px 15px rgba(0,0,0,0.2);
        }}
        .evidence-card.selected {{
            border-color: #007bff;
            background: #f8f9ff;
            box-shadow: 0 8px 15px rgba(0,123,255,0.2);
        }}
        .evidence-selector {{
            padding: 15px;
            background: #f8f9fa;
            border-bottom: 1px solid #e9ecef;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .evidence-checkbox {{
            transform: scale(1.3);
            margin-right: 5px;
        }}
        .checkbox-label {{
            font-weight: 600;
            color: #495057;
            cursor: pointer;
            font-size: 0.95em;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .checkbox-icon {{
            font-size: 1.2em;
            transition: all 0.3s ease;
        }}
        .evidence-card.selected .checkbox-icon {{
            color: #007bff;
        }}
        .checkbox-text {{
            transition: all 0.3s ease;
        }}
        .evidence-card.selected .checkbox-text {{
            color: #007bff;
            font-weight: 700;
        }}
        .evidence-image-container {{
            position: relative;
            height: 220px;
            overflow: hidden;
        }}
        .evidence-image {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            cursor: pointer;
            transition: transform 0.3s ease;
        }}
        .evidence-image:hover {{
            transform: scale(1.05);
        }}
        .evidence-overlay {{
            position: absolute;
            top: 12px;
            left: 12px;
            right: 12px;
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
        }}
        .evidence-plate-badge {{
            background: #ffc107;
            color: #212529;
            padding: 6px 12px;
            border-radius: 6px;
            font-family: 'Courier New', monospace;
            font-weight: bold;
            font-size: 0.9em;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }}
        .evidence-badges {{
            display: flex;
            flex-direction: column;
            gap: 6px;
            align-items: flex-end;
        }}
        .recent-badge {{
            background: #28a745;
            color: white;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 0.7em;
            font-weight: bold;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }}
        .confidence-badge {{
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 0.7em;
            font-weight: bold;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }}
        .confidence-badge.high {{
            background: #28a745;
            color: white;
        }}
        .confidence-badge.medium {{
            background: #ffc107;
            color: #212529;
        }}
        .confidence-badge.low {{
            background: #dc3545;
            color: white;
        }}
        .evidence-status-bar {{
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            background: linear-gradient(transparent, rgba(0,0,0,0.8));
            padding: 12px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .plate-status {{
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 0.75em;
            font-weight: bold;
        }}
        .plate-status.readable {{
            background: #c6f6d5;
            color: #22543d;
        }}
        .plate-status.unreadable {{
            background: #fed7d7;
            color: #c53030;
        }}
        .confidence-indicator {{
            color: white;
            font-size: 0.75em;
            font-weight: bold;
            background: rgba(0,0,0,0.6);
            padding: 4px 8px;
            border-radius: 4px;
        }}
        .evidence-actions {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            display: flex;
            gap: 10px;
            opacity: 0;
            transition: opacity 0.3s ease;
        }}
        .evidence-card:hover .evidence-actions {{
            opacity: 1;
        }}
        .action-btn {{
            padding: 8px 12px;
            border: none;
            border-radius: 6px;
            font-size: 0.8em;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }}
        .preview-btn {{
            background: #007bff;
            color: white;
        }}
        .preview-btn:hover {{
            background: #0056b3;
        }}
        .info-btn {{
            background: #6c757d;
            color: white;
        }}
        .info-btn:hover {{
            background: #545b62;
        }}
        .evidence-details {{
            padding: 18px;
        }}
        .evidence-title {{
            font-size: 1.2em;
            font-weight: bold;
            color: #212529;
            margin-bottom: 5px;
            text-align: center;
        }}
        .evidence-subtitle {{
            font-size: 0.9em;
            color: #6c757d;
            text-align: center;
            margin-bottom: 15px;
            font-style: italic;
        }}
        .evidence-meta {{
            font-size: 0.85em;
            margin-bottom: 15px;
        }}
        .meta-row {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 6px;
            align-items: center;
        }}
        .meta-label {{
            color: #6c757d;
            font-weight: 600;
        }}
        .meta-value {{
            color: #495057;
            font-weight: 500;
        }}
        .evidence-quality {{
            text-align: center;
        }}
        .quality-indicator {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 0.8em;
            font-weight: 600;
        }}
        .quality-indicator.high {{
            background: #d4edda;
            color: #155724;
        }}
        .quality-indicator.medium {{
            background: #fff3cd;
            color: #856404;
        }}
        .quality-indicator.low {{
            background: #f8d7da;
            color: #721c24;
        }}
        .quality-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: currentColor;
        }}
        .report-actions {{
            background: white;
            padding: 30px;
            border-radius: 10px;
            margin-top: 30px;
            border: 2px solid #007bff;
        }}
        .report-header {{
            text-align: center;
            margin-bottom: 25px;
        }}
        .report-header h4 {{
            color: #007bff;
            margin-bottom: 10px;
            font-size: 1.4em;
        }}
        .report-tips {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin-top: 15px;
        }}
        .tip-item {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 8px;
            font-size: 0.9em;
        }}
        .tip-item:last-child {{
            margin-bottom: 0;
        }}
        .tip-icon {{
            font-size: 1.1em;
        }}
        .tip-text {{
            color: #495057;
        }}
        .report-buttons {{
            display: flex;
            gap: 15px;
            margin-bottom: 25px;
            flex-wrap: wrap;
            justify-content: center;
        }}
        .report-btn {{
            padding: 12px 20px;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            font-size: 14px;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }}
        .report-btn:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}
        .report-btn.large {{
            padding: 15px 25px;
            font-size: 16px;
        }}
        .report-btn.primary {{
            background: #007bff;
            color: white;
        }}
        .report-btn.primary:hover:not(:disabled) {{
            background: #0056b3;
            transform: translateY(-2px);
        }}
        .report-btn.secondary {{
            background: #6c757d;
            color: white;
        }}
        .report-btn.secondary:hover {{
            background: #545b62;
            transform: translateY(-2px);
        }}
        .report-btn.email {{
            background: #28a745;
            color: white;
        }}
        .report-btn.email:hover:not(:disabled) {{
            background: #1e7e34;
            transform: translateY(-2px);
        }}
        .report-btn.gmail {{
            background: #ea4335;
            color: white;
        }}
        .report-btn.gmail:hover:not(:disabled) {{
            background: #d33b2c;
            transform: translateY(-2px);
        }}
        .report-btn.outlook {{
            background: #0078d4;
            color: white;
        }}
        .report-btn.outlook:hover:not(:disabled) {{
            background: #106ebe;
            transform: translateY(-2px);
        }}
        .report-btn.download {{
            background: #17a2b8;
            color: white;
        }}
        .report-btn.download:hover:not(:disabled) {{
            background: #138496;
            transform: translateY(-2px);
        }}
        .report-btn.export {{
            background: #fd7e14;
            color: white;
        }}
        .report-btn.export:hover:not(:disabled) {{
            background: #e8650e;
            transform: translateY(-2px);
        }}
        .email-template {{
            background: #f8f9fa;
            padding: 25px;
            border-radius: 8px;
            border: 1px solid #dee2e6;
        }}
        .template-header {{
            text-align: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 1px solid #dee2e6;
        }}
        .template-header h5 {{
            color: #495057;
            margin-bottom: 5px;
        }}
        .template-header p {{
            color: #6c757d;
            font-size: 0.9em;
            margin: 0;
        }}
        .template-row {{
            margin-bottom: 15px;
        }}
        .template-row:last-child {{
            margin-bottom: 0;
        }}
        .template-row label {{
            display: block;
            font-weight: 600;
            color: #495057;
            margin-bottom: 5px;
        }}
        .email-input, .email-select {{
            width: 100%;
            padding: 10px;
            border: 1px solid #ced4da;
            border-radius: 5px;
            font-size: 14px;
            transition: border-color 0.3s ease;
        }}
        .email-input:focus, .email-select:focus {{
            outline: none;
            border-color: #007bff;
            box-shadow: 0 0 0 2px rgba(0,123,255,0.25);
        }}
        .email-textarea {{
            width: 100%;
            padding: 12px;
            border: 1px solid #ced4da;
            border-radius: 5px;
            font-size: 14px;
            font-family: inherit;
            resize: vertical;
            min-height: 120px;
            transition: border-color 0.3s ease;
        }}
        .email-textarea:focus {{
            outline: none;
            border-color: #007bff;
            box-shadow: 0 0 0 2px rgba(0,123,255,0.25);
        }}
        .modal {{
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.9);
        }}
        .modal-content {{
            margin: auto;
            display: block;
            width: 80%;
            max-width: 700px;
            max-height: 80%;
            object-fit: contain;
        }}
        .modal-close {{
            position: absolute;
            top: 15px;
            right: 35px;
            color: #f1f1f1;
            font-size: 40px;
            font-weight: bold;
            cursor: pointer;
        }}
        .modal-close:hover {{
            color: #bbb;
        }}
        .evidence-header {{
            text-align: center;
            margin-bottom: 25px;
        }}
        .evidence-stats {{
            display: flex;
            justify-content: center;
            gap: 20px;
            margin: 20px 0;
            flex-wrap: wrap;
        }}
        .stat-item {{
            background: white;
            padding: 15px 20px;
            border-radius: 10px;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            border: 2px solid #e9ecef;
        }}
        .stat-number {{
            display: block;
            font-size: 2em;
            font-weight: bold;
            color: #007bff;
        }}
        .stat-label {{
            font-size: 0.9em;
            color: #6c757d;
            margin-top: 5px;
        }}
        .evidence-controls {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            border: 1px solid #dee2e6;
        }}
        .selection-controls {{
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }}
        .control-btn {{
            padding: 8px 16px;
            border: 1px solid #007bff;
            background: white;
            color: #007bff;
            border-radius: 5px;
            cursor: pointer;
            font-size: 0.9em;
            transition: all 0.3s ease;
        }}
        .control-btn:hover {{
            background: #007bff;
            color: white;
        }}
        .selection-info {{
            font-weight: 600;
            color: #495057;
            text-align: center;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 5px;
        }}
        .evidence-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .evidence-card {{
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            border: 2px solid #e9ecef;
            transition: all 0.3s ease;
        }}
        .evidence-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 8px 15px rgba(0,0,0,0.2);
        }}
        .evidence-card.selected {{
            border-color: #007bff;
            background: #f8f9ff;
        }}
        .evidence-selector {{
            padding: 12px;
            background: #f8f9fa;
            border-bottom: 1px solid #e9ecef;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .evidence-checkbox {{
            transform: scale(1.2);
        }}
        .checkbox-label {{
            font-weight: 600;
            color: #495057;
            cursor: pointer;
            font-size: 0.9em;
        }}
        .evidence-image-container {{
            position: relative;
            height: 200px;
            overflow: hidden;
        }}
        .evidence-image {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            cursor: pointer;
            transition: transform 0.3s ease;
        }}
        .evidence-image:hover {{
            transform: scale(1.1);
        }}
        .evidence-overlay {{
            position: absolute;
            top: 10px;
            left: 10px;
            right: 10px;
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
        }}
        .evidence-plate-badge {{
            background: #ffc107;
            color: #212529;
            padding: 4px 8px;
            border-radius: 4px;
            font-family: 'Courier New', monospace;
            font-weight: bold;
            font-size: 0.8em;
        }}
        .recent-badge {{
            background: #28a745;
            color: white;
            padding: 2px 6px;
            border-radius: 10px;
            font-size: 0.7em;
            font-weight: bold;
        }}
        .evidence-status-bar {{
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            background: linear-gradient(transparent, rgba(0,0,0,0.8));
            padding: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .plate-status {{
            padding: 2px 6px;
            border-radius: 10px;
            font-size: 0.7em;
            font-weight: bold;
        }}
        .plate-status.readable {{
            background: #c6f6d5;
            color: #22543d;
        }}
        .plate-status.unreadable {{
            background: #fed7d7;
            color: #c53030;
        }}
        .confidence-indicator {{
            color: white;
            font-size: 0.7em;
            font-weight: bold;
        }}
        .confidence-indicator.high {{
            color: #28a745;
        }}
        .confidence-indicator.medium {{
            color: #ffc107;
        }}
        .confidence-indicator.low {{
            color: #dc3545;
        }}
        .evidence-details {{
            padding: 15px;
        }}
        .evidence-title {{
            font-size: 1.1em;
            font-weight: bold;
            color: #212529;
            margin-bottom: 10px;
            text-align: center;
        }}
        .evidence-meta {{
            font-size: 0.85em;
        }}
        .meta-row {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 5px;
        }}
        .meta-label {{
            color: #6c757d;
            font-weight: 600;
        }}
        .meta-value {{
            color: #495057;
        }}
        .report-actions {{
            background: white;
            padding: 25px;
            border-radius: 10px;
            margin-top: 30px;
            border: 2px solid #007bff;
        }}
        .report-header {{
            text-align: center;
            margin-bottom: 20px;
        }}
        .report-header h4 {{
            color: #007bff;
            margin-bottom: 10px;
        }}
        .report-buttons {{
            display: flex;
            gap: 15px;
            margin-bottom: 25px;
            flex-wrap: wrap;
            justify-content: center;
        }}
        .report-btn {{
            padding: 12px 20px;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            font-size: 14px;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }}
        .report-btn:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}
        .report-btn.primary {{
            background: #007bff;
            color: white;
        }}
        .report-btn.primary:hover:not(:disabled) {{
            background: #0056b3;
            transform: translateY(-2px);
        }}
        .report-btn.secondary {{
            background: #6c757d;
            color: white;
        }}
        .report-btn.secondary:hover {{
            background: #545b62;
            transform: translateY(-2px);
        }}
        .report-btn.email {{
            background: #28a745;
            color: white;
        }}
        .report-btn.email:hover:not(:disabled) {{
            background: #1e7e34;
            transform: translateY(-2px);
        }}
        .report-btn.download {{
            background: #17a2b8;
            color: white;
        }}
        .report-btn.download:hover:not(:disabled) {{
            background: #138496;
            transform: translateY(-2px);
        }}
        .email-template {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            border: 1px solid #dee2e6;
        }}
        .template-row {{
            margin-bottom: 15px;
        }}
        .template-row:last-child {{
            margin-bottom: 0;
        }}
        .template-row label {{
            display: block;
            font-weight: 600;
            color: #495057;
            margin-bottom: 5px;
        }}
        .no-evidence-message {{
            text-align: center;
            padding: 60px 20px;
            background: #f8f9fa;
            border-radius: 10px;
            border: 2px dashed #dee2e6;
        }}
        .no-evidence-icon {{
            font-size: 4em;
            margin-bottom: 20px;
        }}
        .no-evidence-message h4 {{
            color: #495057;
            margin-bottom: 15px;
        }}
        .no-evidence-message p {{
            color: #6c757d;
            margin-bottom: 10px;
        }}
        .evidence-help {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-top: 20px;
            text-align: left;
            max-width: 400px;
            margin-left: auto;
            margin-right: auto;
        }}
        .evidence-help h5 {{
            color: #495057;
            margin-bottom: 10px;
        }}
        .evidence-help ul {{
            color: #6c757d;
            padding-left: 20px;
        }}
        .production-note {{
            background: #fff3cd;
            padding: 15px;
            border-radius: 8px;
            margin-top: 15px;
            border-left: 4px solid #ffc107;
        }}
        .production-note h5 {{
            color: #856404;
            margin-bottom: 10px;
        }}
        .production-note p {{
            color: #856404;
            margin: 0;
            font-size: 0.9em;
        }}
        .error-message {{
            text-align: center;
            padding: 40px 20px;
            background: #f8d7da;
            border-radius: 10px;
            border: 2px solid #f5c6cb;
        }}
        .error-icon {{
            font-size: 3em;
            margin-bottom: 15px;
        }}
        .error-message h4 {{
            color: #721c24;
            margin-bottom: 15px;
        }}
        .error-message p {{
            color: #721c24;
            margin-bottom: 10px;
        }}
        .report-footer {{
            background: #f8f9fa;
            padding: 20px 30px;
            border-top: 1px solid #e9ecef;
            text-align: center;
            color: #6c757d;
            font-size: 0.9em;
        }}
        .action-buttons {{
            margin: 30px 0;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
            text-align: center;
            border: 1px solid #e9ecef;
        }}
        .action-btn {{
            display: inline-block;
            padding: 12px 24px;
            margin: 0 10px 10px 0;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 6px;
            font-weight: bold;
            transition: background-color 0.3s;
            border: none;
            cursor: pointer;
            font-size: 14px;
        }}
        .action-btn:hover {{
            background: #5a67d8;
        }}
        .action-btn.print {{
            background: #28a745;
        }}
        .action-btn.print:hover {{
            background: #218838;
        }}
        .action-btn.save {{
            background: #17a2b8;
        }}
        .action-btn.save:hover {{
            background: #138496;
        }}
        @media (max-width: 768px) {{
            body {{
                padding: 10px;
            }}
            .report-content {{
                padding: 20px;
            }}
            .report-meta {{
                grid-template-columns: 1fr;
            }}
        }}
        @media print {{
            .action-buttons {{
                display: none;
            }}
            body {{
                background-color: white;
            }}
            .report-container {{
                box-shadow: none;
            }}
        }}
    </style>
</head>
<body>
    <div class="report-container">
        <div class="report-header">
            <h1>SMOKi Detection Report</h1>
            <div class="subtitle">Automated Smoke & Vehicle Detection System</div>
        </div>
        
        <div class="report-content">
            <div class="report-meta">
                <div class="meta-card">
                    <h3>Report Information</h3>
                    <p><strong>Report ID:</strong> {report_id}</p>
                    <p><strong>Generated:</strong> {timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
                    <p><strong>Report Type:</strong> {report_type.title()}</p>
                    <p><strong>Severity:</strong> <span class="severity-badge">{severity}</span></p>
                </div>
                
                <div class="meta-card">
                    <h3>Camera Information</h3>
                    <p><strong>Location:</strong> {camera_info.get('location', 'Main Camera Station')}</p>
                    <p><strong>Camera ID:</strong> {camera_info.get('camera_id', 'SMOKi_Camera_01')}</p>
                    <p><strong>Status:</strong> {report_data.get('detection_data', {}).get('status', 'Active')}</p>
                    <p><strong>FPS:</strong> {report_data.get('detection_data', {}).get('fps', 'N/A')}</p>
                </div>
            </div>
            
            {frame_html}
            
            {evidence_gallery_html}
            
            {violation_evidence_html}
            
            {detection_details_html}
            
            <div class="action-buttons">
                <h3>📋 Report Actions</h3>
                <p>Use the buttons below to print, save, or share this report:</p>
                <button onclick="window.print()" class="action-btn print">🖨️ Print Report</button>
                <button onclick="saveReport()" class="action-btn save">💾 Save as PDF</button>
                <button onclick="copyReportLink()" class="action-btn">🔗 Copy Link</button>
                <button onclick="shareReport()" class="action-btn">📤 Share Report</button>
            </div>
        </div>
        
        <div class="report-footer">
            <p>This report was automatically generated by the SMOKi Detection System.</p>
            <p>For technical support, contact: support@smoki.gov</p>
            <p>© 2026 SMOKi - Smoke Detection & Monitoring System</p>
        </div>
    </div>
    
    <script>
        function saveReport() {{
            // Use browser's built-in print to PDF functionality
            window.print();
        }}
        
        function copyReportLink() {{
            const url = window.location.href;
            if (navigator.clipboard) {{
                navigator.clipboard.writeText(url).then(() => {{
                    alert('Report link copied to clipboard!');
                }}).catch(() => {{
                    fallbackCopyTextToClipboard(url);
                }});
            }} else {{
                fallbackCopyTextToClipboard(url);
            }}
        }}
        
        function fallbackCopyTextToClipboard(text) {{
            const textArea = document.createElement("textarea");
            textArea.value = text;
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();
            try {{
                document.execCommand('copy');
                alert('Report link copied to clipboard!');
            }} catch (err) {{
                alert('Could not copy link. Please copy manually: ' + text);
            }}
            document.body.removeChild(textArea);
        }}
        
        function shareReport() {{
            const reportData = {{
                title: 'SMOKi Detection Report - {report_id}',
                text: 'SMOKi Detection Report\\n\\nReport ID: {report_id}\\nGenerated: {timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}\\nSeverity: {severity}\\n\\nEvidence Files: {total_evidence_files}\\nRecent Violations: {recent_violations}',
                url: window.location.href
            }};
            
            if (navigator.share) {{
                navigator.share(reportData).catch(err => {{
                    console.log('Error sharing:', err);
                    fallbackShare();
                }});
            }} else {{
                fallbackShare();
            }}
        }}
        
        function fallbackShare() {{
            // Copy report link to clipboard instead of opening email
            const reportUrl = window.location.href;
            if (navigator.clipboard) {{
                navigator.clipboard.writeText(reportUrl).then(() => {{
                    alert('Report link copied to clipboard! You can now paste it in your email or message.');
                }}).catch(() => {{
                    // Show the link in a prompt for manual copying
                    prompt('Copy this report link:', reportUrl);
                }});
            }} else {{
                // Show the link in a prompt for manual copying
                prompt('Copy this report link:', reportUrl);
            }}
        }}
        
        // Auto-focus functionality
        document.addEventListener('DOMContentLoaded', function() {{
            console.log('SMOKi Report loaded successfully');
            
            // Add keyboard shortcuts
            document.addEventListener('keydown', function(e) {{
                if (e.ctrlKey || e.metaKey) {{
                    switch(e.key) {{
                        case 'p':
                            e.preventDefault();
                            window.print();
                            break;
                        case 's':
                            e.preventDefault();
                            saveReport();
                            break;
                    }}
                }}
            }});
            
            // Initialize evidence gallery
            updateSelectedEvidence();
        }});
        
        // Evidence Gallery Functions
        let selectedEvidence = [];
        
        function updateSelectedEvidence() {{
            const checkboxes = document.querySelectorAll('.evidence-checkbox');
            selectedEvidence = [];
            
            checkboxes.forEach(checkbox => {{
                const card = checkbox.closest('.evidence-card');
                if (checkbox.checked) {{
                    card.classList.add('selected');
                    selectedEvidence.push({{
                        filename: checkbox.dataset.filename,
                        plate: checkbox.dataset.plate,
                        vehicle: checkbox.dataset.vehicle,
                        smoke: checkbox.dataset.smoke,
                        timestamp: checkbox.dataset.timestamp,
                        element: checkbox
                    }});
                }} else {{
                    card.classList.remove('selected');
                }}
            }});
            
            // Update selected count
            const countElement = document.getElementById('selectedCount');
            if (countElement) {{
                countElement.textContent = selectedEvidence.length;
            }}
            
            // Enable/disable buttons based on selection
            const buttons = ['generateReportBtn', 'emailGmailBtn', 'emailOutlookBtn', 'downloadBtn'];
            buttons.forEach(btnId => {{
                const btn = document.getElementById(btnId);
                if (btn) {{
                    btn.disabled = selectedEvidence.length === 0;
                }}
            }});
        }}
        
        function selectAllEvidence() {{
            const checkboxes = document.querySelectorAll('.evidence-checkbox');
            checkboxes.forEach(cb => cb.checked = true);
            updateSelectedEvidence();
        }}
        
        function deselectAllEvidence() {{
            const checkboxes = document.querySelectorAll('.evidence-checkbox');
            checkboxes.forEach(cb => cb.checked = false);
            updateSelectedEvidence();
        }}
        
        function selectReadableOnly() {{
            const checkboxes = document.querySelectorAll('.evidence-checkbox');
            checkboxes.forEach(cb => {{
                const card = cb.closest('.evidence-card');
                cb.checked = card.dataset.readable === 'True';
            }});
            updateSelectedEvidence();
        }}
        
        function selectRecentOnly() {{
            const checkboxes = document.querySelectorAll('.evidence-checkbox');
            checkboxes.forEach(cb => {{
                const card = cb.closest('.evidence-card');
                cb.checked = card.dataset.recent === 'True';
            }});
            updateSelectedEvidence();
        }}
        
        function openImageModal(filename, imageData, licensePlate, timestamp) {{
            // Create modal if it doesn't exist
            let modal = document.getElementById('imageModal');
            if (!modal) {{
                modal = document.createElement('div');
                modal.id = 'imageModal';
                modal.className = 'modal';
                modal.innerHTML = `
                    <span class="modal-close" onclick="closeImageModal()">&times;</span>
                    <img class="modal-content" id="modalImage">
                    <div style="text-align: center; color: white; margin-top: 20px;">
                        <h3 id="modalTitle"></h3>
                        <p id="modalInfo"></p>
                    </div>
                `;
                document.body.appendChild(modal);
            }}
            
            // Show the modal
            const modalImg = document.getElementById('modalImage');
            const modalTitle = document.getElementById('modalTitle');
            const modalInfo = document.getElementById('modalInfo');
            
            modalImg.src = imageData;
            modalTitle.textContent = `License Plate: ${{licensePlate}}`;
            modalInfo.textContent = `Detection Time: ${{timestamp}} | File: ${{filename}}`;
            modal.style.display = 'block';
            
            // Close modal when clicking outside the image
            modal.onclick = function(event) {{
                if (event.target === modal) {{
                    closeImageModal();
                }}
            }};
        }}
        
        function closeImageModal() {{
            const modal = document.getElementById('imageModal');
            if (modal) {{
                modal.style.display = 'none';
            }}
        }}
        
        function generateSelectedReport() {{
            if (selectedEvidence.length === 0) {{
                alert('Please select at least one evidence image to include in the report.');
                return;
            }}
            
            // Create a summary of selected evidence
            let summary = `Selected Evidence Report\\n\\n`;
            summary += `Total Selected: ${{selectedEvidence.length}} images\\n\\n`;
            
            selectedEvidence.forEach((evidence, index) => {{
                summary += `${{index + 1}}. License Plate: ${{evidence.plate}}\\n`;
                summary += `   Vehicle: ${{evidence.vehicle}} | Smoke: ${{evidence.smoke}}\\n`;
                summary += `   File: ${{evidence.filename}}\\n`;
                summary += `   Time: ${{evidence.timestamp}}\\n\\n`;
            }});
            
            summary += `Files are located in: D:\\\\embed\\\\SMOKI\\\\esp32\\\\evidence\\\\`;
            
            // Show the summary
            alert(summary);
            
            // You could also generate a new HTML report here
            console.log('Selected evidence for report:', selectedEvidence);
        }}
        
        function generateFullReport() {{
            // Generate report with all evidence
            alert('Generating full evidence report with all available images...');
            window.print(); // Print current page as full report
        }}
        
        function sendEmailReport(provider) {{
            if (selectedEvidence.length === 0) {{
                alert('Please select at least one evidence image to include in the email.');
                return;
            }}
            
            const subject = document.getElementById('emailSubject')?.value || 'SMOKi Violation Evidence Report';
            const recipient = document.getElementById('emailRecipient')?.value || '';
            const body = document.getElementById('emailBody')?.value || 'Please find attached evidence of smoking violations.';
            
            // Create email content with selected evidence
            let emailBody = body + '\\n\\nSelected Evidence Files:\\n';
            selectedEvidence.forEach((evidence, index) => {{
                emailBody += `${{index + 1}}. ${{evidence.filename}} - License Plate: ${{evidence.plate}} (${{evidence.vehicle}}, ${{evidence.smoke}})\\n`;
            }});
            
            emailBody += '\\n\\nEvidence files are located in: D:\\\\embed\\\\SMOKI\\\\esp32\\\\evidence\\\\';
            emailBody += '\\n\\nPlease manually attach the selected files to this email.';
            
            // Encode for URL
            const encodedSubject = encodeURIComponent(subject);
            const encodedBody = encodeURIComponent(emailBody);
            const encodedRecipient = encodeURIComponent(recipient);
            
            let emailUrl = '';
            
            if (provider === 'gmail') {{
                emailUrl = `https://mail.google.com/mail/?view=cm&fs=1&to=${{encodedRecipient}}&su=${{encodedSubject}}&body=${{encodedBody}}`;
            }} else if (provider === 'outlook') {{
                emailUrl = `https://outlook.live.com/mail/0/deeplink/compose?to=${{encodedRecipient}}&subject=${{encodedSubject}}&body=${{encodedBody}}`;
            }}
            
            if (emailUrl) {{
                // Open email client
                window.open(emailUrl, '_blank');
                
                // Show file list for manual attachment
                let fileList = 'Files to attach manually:\\n\\n';
                selectedEvidence.forEach(evidence => {{
                    fileList += `${{evidence.filename}}\\n`;
                }});
                fileList += '\\nLocation: D:\\\\embed\\\\SMOKI\\\\esp32\\\\evidence\\\\';
                
                setTimeout(() => {{
                    alert(fileList);
                }}, 1000);
            }}
        }}
        
        function downloadSelectedEvidence() {{
            if (selectedEvidence.length === 0) {{
                alert('Please select at least one evidence image to download.');
                return;
            }}
            
            // Create download instructions
            let instructions = 'Selected Evidence Files for Download:\\n\\n';
            selectedEvidence.forEach((evidence, index) => {{
                instructions += `${{index + 1}}. ${{evidence.filename}}\\n`;
            }});
            instructions += '\\nFiles are located in:\\nD:\\\\embed\\\\SMOKI\\\\esp32\\\\evidence\\\\';
            instructions += '\\n\\nCopy these files to create your evidence package.';
            
            alert(instructions);
            
            // Copy filenames to clipboard if possible
            const filenames = selectedEvidence.map(e => e.filename).join('\\n');
            if (navigator.clipboard) {{
                navigator.clipboard.writeText(filenames).then(() => {{
                    console.log('Filenames copied to clipboard');
                }}).catch(err => {{
                    console.log('Could not copy to clipboard:', err);
                }});
            }}
        }}
        
        // Keyboard shortcuts for evidence gallery
        document.addEventListener('keydown', function(e) {{
            if (e.ctrlKey || e.metaKey) {{
                switch(e.key) {{
                    case 'a':
                        e.preventDefault();
                        // Select all evidence
                        const checkboxes = document.querySelectorAll('.evidence-checkbox');
                        checkboxes.forEach(cb => {{
                            cb.checked = true;
                        }});
                        updateSelectedEvidence();
                        break;
                    case 'd':
                        e.preventDefault();
                        // Deselect all evidence
                        const allCheckboxes = document.querySelectorAll('.evidence-checkbox');
                        allCheckboxes.forEach(cb => {{
                            cb.checked = false;
                        }});
                        updateSelectedEvidence();
                        break;
                }}
            }}
        }});
        
        // Missing JavaScript functions implementation
        function selectHighConfidenceOnly() {{
            const checkboxes = document.querySelectorAll('.evidence-checkbox');
            checkboxes.forEach(cb => {{
                const card = cb.closest('.evidence-card');
                const confidence = card.dataset.confidence;
                cb.checked = confidence === 'high';
            }});
            updateSelectedEvidence();
        }}
        
        function showEvidenceInfo(filename, evidenceData) {{
            try {{
                const evidence = typeof evidenceData === 'string' ? JSON.parse(evidenceData) : evidenceData;
                
                let infoText = `Evidence Details for: ${{filename}}\\n\\n`;
                infoText += `License Plate: ${{evidence.license_plate}}\\n`;
                infoText += `Vehicle Type: ${{evidence.vehicle_type}}\\n`;
                infoText += `Smoke Type: ${{evidence.smoke_type}}\\n`;
                infoText += `Timestamp: ${{evidence.timestamp}}\\n`;
                infoText += `File Size: ${{(evidence.file_size / 1024).toFixed(1)}} KB\\n`;
                infoText += `Vehicle Confidence: ${{(evidence.vehicle_confidence * 100).toFixed(1)}}%\\n`;
                infoText += `Smoke Confidence: ${{(evidence.smoke_confidence * 100).toFixed(1)}}%\\n`;
                if (evidence.ocr_confidence > 0) {{
                    infoText += `OCR Confidence: ${{(evidence.ocr_confidence * 100).toFixed(1)}}%\\n`;
                }}
                infoText += `Readable Plate: ${{evidence.has_readable_plate ? 'Yes' : 'No'}}\\n`;
                infoText += `Distance: ${{evidence.distance.toFixed(1)}}px\\n`;
                infoText += `File Path: ${{evidence.path}}`;
                
                alert(infoText);
            }} catch (error) {{
                console.error('Error showing evidence info:', error);
                alert('Error displaying evidence information: ' + error.message);
            }}
        }}
        
        function exportToCSV() {{
            if (selectedEvidence.length === 0) {{
                alert('Please select at least one evidence image to export.');
                return;
            }}
            
            try {{
                // Create CSV header
                let csvContent = 'Filename,License Plate,Vehicle Type,Smoke Type,Timestamp,Vehicle Confidence,Smoke Confidence,OCR Confidence,Readable Plate,File Size (KB),Distance (px)\\n';
                
                // Add selected evidence data
                selectedEvidence.forEach(evidence => {{
                    const row = [
                        evidence.filename,
                        evidence.plate,
                        evidence.vehicle,
                        evidence.smoke,
                        evidence.timestamp,
                        evidence.element.dataset.confidence || '0',
                        evidence.element.dataset.smokeConfidence || '0',
                        evidence.element.dataset.ocrConfidence || '0',
                        evidence.element.closest('.evidence-card').dataset.readable || 'False',
                        evidence.element.dataset.fileSize || '0',
                        evidence.element.dataset.distance || '0'
                    ].map(field => `"${{field}}"`).join(',');
                    csvContent += row + '\\n';
                }});
                
                // Create and download CSV file
                const blob = new Blob([csvContent], {{ type: 'text/csv;charset=utf-8;' }});
                const link = document.createElement('a');
                const url = URL.createObjectURL(blob);
                link.setAttribute('href', url);
                link.setAttribute('download', `smoki_evidence_export_${{new Date().toISOString().slice(0, 10)}}.csv`);
                link.style.visibility = 'hidden';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                
                alert(`CSV export completed! ${{selectedEvidence.length}} evidence records exported.`);
            }} catch (error) {{
                console.error('Error exporting CSV:', error);
                alert('Error exporting CSV: ' + error.message);
            }}
        }}
    </script>
</body>
</html>
        """
        
        # Save HTML report to both locations
        report_filename = f"{report_id}.html"
        report_path = self.reports_dir / report_filename
        local_report_path = self.local_reports_dir / report_filename
        
        # Save to backend reports directory
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # Save to local directory for easy access
        with open(local_report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"[REPORT] HTML report saved to:")
        print(f"  - Backend: {report_path}")
        print(f"  - Local: {local_report_path}")
        
        return str(report_path)
    
    def generate_report(self, report_type: str = "general", violation_id: Optional[str] = None, vehicle_data: Optional[Dict] = None, detection_timestamp: Optional[str] = None, detection_data: Optional[Dict] = None) -> Dict:
        """Generate a complete report with current data or detection-specific data"""
        try:
            if report_type == "violation_verification" and violation_id:
                # Generate violation verification report
                return self.generate_violation_verification_report(violation_id)
            elif violation_id:
                # Generate report for a specific violation using its original frame
                return self.generate_violation_specific_report(violation_id, report_type, vehicle_data)
            elif detection_timestamp:
                # Generate report for a specific detection time
                return self.generate_detection_specific_report(detection_timestamp, report_type, detection_data)
            else:
                # Get current frame and detection data
                current_data = self.get_current_frame_and_data()
                
                # Generate HTML report
                report_path = self.generate_html_report(current_data, report_type, vehicle_data)
                
                return {
                    'success': True,
                    'report_path': report_path,
                    'report_id': os.path.basename(report_path).replace('.html', ''),
                    'timestamp': current_data['timestamp'],
                    'detection_summary': current_data.get('detection_data', {}).get('detection_summary', {}),
                    'message': f'Report generated successfully: {report_path}'
                }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'Failed to generate report: {e}'
            }
    
    def generate_violation_specific_report(self, violation_id: str, report_type: str = "general", vehicle_data: Optional[Dict] = None) -> Dict:
        """Generate a report using the original frame from when the violation occurred"""
        try:
            # Import database functions
            import sys
            sys.path.insert(0, '../postgre')
            from database import get_violation_details, get_vehicle_by_id
            
            # Get violation details from database
            violation_details = get_violation_details(violation_id)
            if not violation_details:
                raise Exception(f"Violation {violation_id} not found")
            
            # Get vehicle details
            vehicle_details = get_vehicle_by_id(violation_details['vehicle_id'])
            
            # Get the original violation frame and detection data
            violation_frame_data = self._get_violation_frame_data(violation_id, violation_details)
            
            # Prepare report data using violation frame instead of current frame
            report_data = {
                'frame_data': violation_frame_data.get('frame_data'),
                'detection_data': violation_frame_data.get('detection_data', {}),
                'timestamp': violation_frame_data.get('timestamp', violation_details.get('created_at')),
                'violations': [violation_details],  # Include the specific violation
                'vehicle_data': vehicle_data or {
                    'plate': vehicle_details.get('license_plate', 'Unknown'),
                    'vehicleType': vehicle_details.get('vehicle_type', 'Unknown'),
                    'violations': violation_details.get('severity', 'Unknown'),
                    'status': violation_details.get('status', 'Unknown')
                }
            }
            
            # Add violation-specific context to detection data
            report_data['detection_data'].update({
                'violation_context': True,
                'violation_id': violation_id,
                'violation_timestamp': violation_details.get('created_at'),
                'violation_type': violation_details.get('violation_type'),
                'violation_severity': violation_details.get('severity'),
                'violation_description': violation_details.get('description')
            })
            
            # Generate HTML report with violation-specific data
            report_path = self.generate_html_report(report_data, report_type, vehicle_data)
            
            return {
                'success': True,
                'report_path': report_path,
                'report_id': os.path.basename(report_path).replace('.html', ''),
                'timestamp': report_data['timestamp'],
                'violation_id': violation_id,
                'message': f'Violation-specific report generated: {report_path}'
            }
            
        except Exception as e:
            print(f"[REPORT ERROR] Failed to generate violation-specific report: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e),
                'message': f'Failed to generate violation-specific report: {e}'
            }
    
    def generate_detection_specific_report(self, detection_timestamp: str, report_type: str = "general", detection_data: Optional[Dict] = None) -> Dict:
        """Generate a report using the frame from when a specific detection occurred"""
        try:
            from datetime import datetime
            
            # Parse the detection timestamp
            if isinstance(detection_timestamp, str):
                # Handle ISO format timestamp
                if 'T' in detection_timestamp:
                    timestamp_dt = datetime.fromisoformat(detection_timestamp.replace('Z', '+00:00'))
                else:
                    timestamp_dt = datetime.fromisoformat(detection_timestamp)
            else:
                timestamp_dt = detection_timestamp
            
            print(f"[REPORT] Generating detection-specific report for timestamp: {timestamp_dt}")
            
            # Check if this is a recent detection (within last 5 minutes)
            now = datetime.now(timestamp_dt.tzinfo or timezone.utc)
            time_diff = abs((now - timestamp_dt).total_seconds())
            
            if time_diff <= 300:  # Within 5 minutes - use current frame with detection context
                print(f"[REPORT] Recent detection ({time_diff:.0f}s ago), using current frame with detection context")
                
                # Get current frame and data
                current_data = self.get_current_frame_and_data()
                
                # Prepare report data with detection-specific context
                report_data = {
                    'frame_data': current_data.get('frame_data'),
                    'detection_data': current_data.get('detection_data', {}),
                    'timestamp': timestamp_dt.isoformat(),
                    'violations': [],
                    'detection_specific': True
                }
                
                # Add detection-specific context
                report_data['detection_data'].update({
                    'detection_context': True,
                    'detection_timestamp': timestamp_dt.isoformat(),
                    'detection_type': detection_data.get('type', 'Unknown') if detection_data else 'Unknown',
                    'detection_object': detection_data.get('object', 'Unknown') if detection_data else 'Unknown',
                    'detection_confidence': detection_data.get('confidence', 'Unknown') if detection_data else 'Unknown',
                    'detection_details': detection_data.get('details', 'Unknown') if detection_data else 'Unknown',
                    'original_detection_time': detection_data.get('time', 'Unknown') if detection_data else 'Unknown',
                    'is_live_detection': True,
                    'time_since_detection': f"{time_diff:.0f} seconds ago"
                })
                
            else:
                print(f"[REPORT] Historical detection ({time_diff:.0f}s ago), searching for historical frame")
                
                # Get the frame from the detection timestamp
                detection_frame_data = self._get_frame_from_timestamp(timestamp_dt)
                
                if not detection_frame_data:
                    print(f"[REPORT] No historical frame found for timestamp {timestamp_dt}, using current frame")
                    # Fallback to current frame if no historical frame found
                    current_data = self.get_current_frame_and_data()
                    detection_frame_data = {
                        'frame_data': current_data.get('frame_data'),
                        'timestamp': timestamp_dt.isoformat(),
                        'detection_data': current_data.get('detection_data', {}),
                        'message': f'Historical frame not available for {timestamp_dt}, using current frame'
                    }
                
                # Prepare report data using detection-specific frame
                report_data = {
                    'frame_data': detection_frame_data.get('frame_data'),
                    'detection_data': detection_frame_data.get('detection_data', {}),
                    'timestamp': detection_frame_data.get('timestamp', timestamp_dt.isoformat()),
                    'violations': [],
                    'detection_specific': True
                }
                
                # Add detection-specific context
                report_data['detection_data'].update({
                    'detection_context': True,
                    'detection_timestamp': timestamp_dt.isoformat(),
                    'detection_type': detection_data.get('type', 'Unknown') if detection_data else 'Unknown',
                    'detection_object': detection_data.get('object', 'Unknown') if detection_data else 'Unknown',
                    'detection_confidence': detection_data.get('confidence', 'Unknown') if detection_data else 'Unknown',
                    'detection_details': detection_data.get('details', 'Unknown') if detection_data else 'Unknown',
                    'original_detection_time': detection_data.get('time', 'Unknown') if detection_data else 'Unknown',
                    'is_live_detection': False,
                    'time_since_detection': f"{time_diff:.0f} seconds ago"
                })
            
            # Generate HTML report with detection-specific data
            report_path = self.generate_html_report(report_data, report_type)
            
            return {
                'success': True,
                'report_path': report_path,
                'report_id': os.path.basename(report_path).replace('.html', ''),
                'timestamp': report_data['timestamp'],
                'detection_timestamp': timestamp_dt.isoformat(),
                'is_live_detection': time_diff <= 300,
                'message': f'Detection-specific report generated: {report_path}'
            }
            
        except Exception as e:
            print(f"[REPORT ERROR] Failed to generate detection-specific report: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e),
                'message': f'Failed to generate detection-specific report: {e}'
            }
    
    def generate_violation_verification_report(self, violation_id: str) -> Dict:
        """Generate a detailed verification report for a specific violation"""
        try:
            # Import database functions
            import sys
            sys.path.insert(0, '../postgre')
            from database import get_violation_details, get_vehicle_by_id
            
            # Get violation details from database
            violation_details = get_violation_details(violation_id)
            if not violation_details:
                raise Exception(f"Violation {violation_id} not found")
            
            # Get vehicle details
            vehicle_details = get_vehicle_by_id(violation_details['vehicle_id'])
            
            # Get the original violation frame and detection data
            violation_frame_data = self._get_violation_frame_data(violation_id, violation_details)
            
            # Check for violation evidence (cropped images)
            evidence_files = self._find_violation_evidence(violation_id)
            
            # Generate report ID
            timestamp = datetime.now()
            report_id = f"violation_verification_{violation_id}_{timestamp.strftime('%Y%m%d_%H%M%S')}"
            
            # Generate HTML content with violation-specific frame
            html_content = self._generate_violation_verification_html(
                violation_details, vehicle_details, evidence_files, report_id, violation_frame_data
            )
            
            # Save report
            report_path = self.reports_dir / f"{report_id}.html"
            local_report_path = self.local_reports_dir / f"{report_id}.html"
            
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            with open(local_report_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            print(f"[REPORT] Generated violation verification report: {report_path}")
            
            return {
                'success': True,
                'report_path': str(report_path),
                'report_id': report_id,
                'violation_id': violation_id,
                'timestamp': timestamp.isoformat(),
                'message': f'Violation verification report generated: {report_id}'
            }
            
        except Exception as e:
            print(f"[REPORT ERROR] Failed to generate violation verification report: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e),
                'message': f'Failed to generate violation verification report: {e}'
            }
    
    def generate_evidence_based_report(self, license_plate: str = None, timestamp: str = None) -> Dict:
        """Generate a report using evidence frames from esp32/evidence directory"""
        try:
            from datetime import datetime
            import json
            
            # Search for evidence files
            evidence_dirs = [
                Path("esp32/evidence"),
                Path("../esp32/evidence"),
                Path("D:/embed/SMOKI/esp32/evidence"),
                Path("backend/detection_frames/evidence")
            ]
            
            evidence_files = []
            metadata_files = []
            
            for evidence_dir in evidence_dirs:
                if not evidence_dir.exists():
                    continue
                
                print(f"[REPORT] Searching for evidence in {evidence_dir}")
                
                # Look for violation evidence files
                pattern = f"violation_evidence_{license_plate}_*" if license_plate else "violation_evidence_*"
                for evidence_file in evidence_dir.glob(f"{pattern}.jpg"):
                    evidence_files.append(evidence_file)
                    
                    # Check for corresponding metadata file
                    metadata_file = evidence_file.with_suffix('.json')
                    if metadata_file.exists():
                        metadata_files.append(metadata_file)
            
            if not evidence_files:
                return {
                    'success': False,
                    'error': 'No evidence files found',
                    'message': f'No evidence files found for license plate: {license_plate or "any"}'
                }
            
            # Use the most recent evidence file
            latest_evidence = max(evidence_files, key=lambda f: f.stat().st_mtime)
            latest_metadata = None
            
            # Find corresponding metadata
            metadata_path = latest_evidence.with_suffix('.json')
            if metadata_path.exists():
                with open(metadata_path, 'r') as f:
                    latest_metadata = json.load(f)
            
            # Read the evidence image
            import base64
            with open(latest_evidence, 'rb') as f:
                evidence_image_data = base64.b64encode(f.read()).decode('utf-8')
            
            # Prepare report data
            report_data = {
                'frame_data': evidence_image_data,
                'detection_data': {
                    'camera_id': 'SMOKi_Camera_01',
                    'location': 'Main Camera Station',
                    'detections': [],
                    'detection_summary': {
                        'smoke_detections': 1 if latest_metadata and latest_metadata.get('smoke_type') else 0,
                        'vehicle_detections': 1 if latest_metadata and latest_metadata.get('vehicle_type') else 0,
                        'plate_detections': 1 if latest_metadata and latest_metadata.get('license_plate') else 0
                    }
                },
                'timestamp': latest_metadata.get('timestamp', datetime.now().isoformat()) if latest_metadata else datetime.now().isoformat(),
                'violations': [latest_metadata] if latest_metadata else [],
                'evidence_based': True,
                'evidence_file': str(latest_evidence)
            }
            
            # Generate HTML report
            report_path = self.generate_html_report(report_data, "evidence_verification")
            
            return {
                'success': True,
                'report_path': report_path,
                'report_id': os.path.basename(report_path).replace('.html', ''),
                'timestamp': report_data['timestamp'],
                'evidence_file': str(latest_evidence),
                'license_plate': latest_metadata.get('license_plate') if latest_metadata else 'Unknown',
                'message': f'Evidence-based report generated: {report_path}'
            }
            
        except Exception as e:
            print(f"[REPORT ERROR] Failed to generate evidence-based report: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e),
                'message': f'Failed to generate evidence-based report: {e}'
            }
    
    def _get_violation_frame_data(self, violation_id: str, violation_details: Dict) -> Dict:
        """Get the original frame data from when the violation occurred"""
        try:
            # Try to get frame data from detection record
            detection_id = violation_details.get('detection_id')
            if detection_id:
                # Get frame from detection record
                frame_data = self._get_frame_from_detection(detection_id)
                if frame_data:
                    return frame_data
            
            # Try to get frame from violation timestamp
            violation_timestamp = violation_details.get('created_at')
            if violation_timestamp:
                frame_data = self._get_frame_from_timestamp(violation_timestamp)
                if frame_data:
                    return frame_data
            
            # Fallback: try to find saved violation frame files
            frame_data = self._get_frame_from_files(violation_id)
            if frame_data:
                return frame_data
            
            print(f"[REPORT] No violation frame found for violation {violation_id}, using placeholder")
            return {
                'frame_data': None,
                'timestamp': violation_details.get('created_at', datetime.now().isoformat()),
                'detection_data': {},
                'message': 'Original violation frame not available'
            }
            
        except Exception as e:
            print(f"[REPORT] Error getting violation frame data: {e}")
            return {
                'frame_data': None,
                'timestamp': violation_details.get('created_at', datetime.now().isoformat()),
                'detection_data': {},
                'message': f'Error retrieving violation frame: {e}'
            }
    
    def _get_frame_from_detection(self, detection_id: int) -> Optional[Dict]:
        """Get frame data from detection record"""
        try:
            import sys
            sys.path.insert(0, '../postgre')
            from database import get_connection_string
            import psycopg
            
            with psycopg.connect(get_connection_string()) as conn:
                with conn.cursor() as cursor:
                    # Try to get detection record from detections table
                    cursor.execute("""
                        SELECT timestamp, detections_json, camera_id, location
                        FROM detections 
                        WHERE id = %s;
                    """, (detection_id,))
                    
                    result = cursor.fetchone()
                    if result:
                        timestamp, detections_json, camera_id, location = result
                        
                        return {
                            'frame_data': None,  # No frame data in detections table
                            'timestamp': timestamp.isoformat() if timestamp else None,
                            'detection_data': {
                                'camera_id': camera_id,
                                'location': location,
                                'detections': detections_json or []
                            },
                            'detections': detections_json or [],
                            'source': 'detection_record',
                            'message': 'Detection record found but no frame data available'
                        }
            
            return None
            
        except Exception as e:
            print(f"[REPORT] Error getting frame from detection {detection_id}: {e}")
            return None
            print(f"[REPORT] Error getting frame from detection {detection_id}: {e}")
            return None
    
    def _get_frame_from_timestamp(self, timestamp) -> Optional[Dict]:
        """Get frame data closest to violation timestamp"""
        try:
            # First try local frame storage (most recent and accurate)
            print(f"[REPORT] Searching local frame storage for timestamp: {timestamp}")
            local_frame = frame_storage.get_frame_by_timestamp(timestamp, tolerance_seconds=300)
            
            if local_frame:
                print(f"[REPORT] Found local frame {local_frame['time_diff_seconds']:.1f}s from target timestamp")
                return {
                    'frame_data': local_frame['frame_data'],
                    'timestamp': local_frame['timestamp'],
                    'detection_data': {
                        'camera_id': 'SMOKi_Camera_01',
                        'location': 'Main Camera Station',
                        'detections': local_frame['detections'],
                        'detection_counts': local_frame['detection_counts']
                    },
                    'detections': local_frame['detections'],
                    'source': 'local_frame_storage',
                    'time_diff_seconds': local_frame['time_diff_seconds'],
                    'message': f'Found local frame {local_frame["time_diff_seconds"]:.1f}s from detection time'
                }
            
            print(f"[REPORT] No local frame found, trying laptop violation frames...")
            
            # Try laptop violation frames directory
            laptop_frame = self._get_laptop_violation_frame(timestamp)
            if laptop_frame:
                return laptop_frame
            
            print(f"[REPORT] No laptop frames found, trying database...")
            
            # Fallback to database search
            import sys
            sys.path.insert(0, '../postgre')
            from database import get_connection_string
            import psycopg
            
            with psycopg.connect(get_connection_string()) as conn:
                with conn.cursor() as cursor:
                    # First try the detections table
                    cursor.execute("""
                        SELECT id, timestamp, detections_json, camera_id, location
                        FROM detections 
                        WHERE timestamp <= %s
                        ORDER BY ABS(EXTRACT(EPOCH FROM (timestamp - %s)))
                        LIMIT 1;
                    """, (timestamp, timestamp))
                    
                    result = cursor.fetchone()
                    if result:
                        det_id, det_timestamp, detections_json, camera_id, location = result
                        
                        # Check if this result is reasonably close (within 1 hour)
                        time_diff = abs((det_timestamp - timestamp).total_seconds())
                        if time_diff <= 3600:  # Within 1 hour
                            return {
                                'frame_data': None,  # No frame data in detections table
                                'timestamp': det_timestamp.isoformat() if det_timestamp else None,
                                'detection_data': {
                                    'camera_id': camera_id,
                                    'location': location,
                                    'detections': detections_json or []
                                },
                                'detections': detections_json or [],
                                'source': 'detections_table',
                                'detection_id': det_id,
                                'message': f'Found detection record closest to {timestamp}'
                            }
                    
                    # If no close match in detections table, try vehicle_detections table
                    print(f"[REPORT] No close match in detections table, trying vehicle_detections...")
                    cursor.execute("""
                        SELECT id, timestamp, metadata, image_path, location
                        FROM vehicle_detections 
                        WHERE timestamp <= %s
                        ORDER BY ABS(EXTRACT(EPOCH FROM (timestamp - %s)))
                        LIMIT 1;
                    """, (timestamp, timestamp))
                    
                    result = cursor.fetchone()
                    if result:
                        det_id, det_timestamp, metadata, image_path, location = result
                        
                        # Parse metadata
                        detection_metadata = {}
                        detections_list = []
                        if metadata:
                            if isinstance(metadata, str):
                                import json
                                detection_metadata = json.loads(metadata)
                            else:
                                detection_metadata = metadata
                            detections_list = detection_metadata.get('detections', [])
                        
                        # Try to get frame data from image_path or images table
                        frame_data = None
                        if image_path and image_path.isdigit():
                            # image_path contains image ID, try to get image data
                            cursor.execute("""
                                SELECT image_data FROM images WHERE id = %s;
                            """, (int(image_path),))
                            
                            image_result = cursor.fetchone()
                            if image_result and image_result[0]:
                                import base64
                                if isinstance(image_result[0], bytes):
                                    frame_data = base64.b64encode(image_result[0]).decode('utf-8')
                                else:
                                    frame_data = image_result[0]
                        
                        return {
                            'frame_data': frame_data,
                            'timestamp': det_timestamp.isoformat() if det_timestamp else None,
                            'detection_data': {
                                'camera_id': detection_metadata.get('camera_id', 'unknown'),
                                'location': location or detection_metadata.get('location', 'unknown'),
                                'detections': detections_list
                            },
                            'detections': detections_list,
                            'source': 'vehicle_detections_table',
                            'detection_id': det_id,
                            'message': f'Found vehicle detection record closest to {timestamp}'
                        }
            
            return None
            
        except Exception as e:
            print(f"[REPORT] Error getting frame from timestamp {timestamp}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _get_laptop_violation_frame(self, timestamp) -> Optional[Dict]:
        """Get frame from laptop violation frames directory"""
        try:
            from datetime import datetime
            import glob
            
            # Parse target timestamp
            if isinstance(timestamp, str):
                target_dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            else:
                target_dt = timestamp
            
            # Search in laptop violation frames directories (including esp32/evidence)
            search_dirs = [
                Path("backend/detection_frames"),
                Path("backend/detection_frames/evidence"),
                Path("detection_frames"),
                Path("detection_frames/evidence"),
                Path("esp32/evidence"),  # Add esp32 evidence directory
                Path("../esp32/evidence"),  # Also try relative path from backend
                Path("D:/embed/SMOKI/esp32/evidence")  # Direct path to evidence directory
            ]
            
            best_match = None
            best_time_diff = float('inf')
            
            for search_dir in search_dirs:
                if not search_dir.exists():
                    continue
                
                print(f"[REPORT] Searching in {search_dir}")
                
                # Look for violation frame files
                for frame_file in search_dir.glob("violation_frame_*.jpg"):
                    try:
                        # Try to extract timestamp from filename
                        filename = frame_file.stem
                        # Format: violation_frame_{frame_number}_{timestamp}
                        parts = filename.split('_')
                        if len(parts) >= 4:
                            # Reconstruct timestamp from filename parts
                            timestamp_part = '_'.join(parts[3:])  # Everything after frame number
                            
                            # Handle timezone suffix (+0000)
                            if timestamp_part.endswith('+0000'):
                                timestamp_part = timestamp_part[:-5]  # Remove +0000
                            
                            # Convert back to ISO format
                            # Format in filename: YYYYMMDD_HHMMSS_microseconds
                            if len(timestamp_part) >= 15:  # YYYYMMDD_HHMMSS
                                date_part = timestamp_part[:8]  # YYYYMMDD
                                time_part = timestamp_part[9:15]  # HHMMSS
                                microseconds_part = timestamp_part[16:] if len(timestamp_part) > 16 else "000000"
                                
                                # Reconstruct ISO timestamp
                                iso_timestamp = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}T{time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}.{microseconds_part}+00:00"
                                
                                frame_dt = datetime.fromisoformat(iso_timestamp)
                                time_diff = abs((target_dt - frame_dt).total_seconds())
                                
                                print(f"[REPORT] Found frame {frame_file.name} with timestamp {iso_timestamp}, diff: {time_diff:.1f}s")
                                
                                if time_diff < best_time_diff:
                                    best_time_diff = time_diff
                                    best_match = {
                                        'frame_file': frame_file,
                                        'timestamp': frame_dt.isoformat(),
                                        'time_diff': time_diff
                                    }
                    except Exception as e:
                        print(f"[REPORT] Error parsing frame {frame_file.name}: {e}")
                        continue
                
                # Look for evidence frames (esp32 format: violation_evidence_PLATE_TIMESTAMP.jpg)
                for evidence_file in search_dir.glob("violation_evidence_*.jpg"):
                    try:
                        # Try to extract timestamp from evidence filename
                        filename = evidence_file.stem
                        # Format: violation_evidence_{plate}_{timestamp}_{frame_number}
                        parts = filename.split('_')
                        if len(parts) >= 4:
                            # Find timestamp part (format: YYYYMMDD_HHMMSS)
                            for i, part in enumerate(parts):
                                if len(part) == 8 and part.isdigit():  # Date part YYYYMMDD
                                    if i + 1 < len(parts) and len(parts[i + 1]) == 6 and parts[i + 1].isdigit():  # Time part HHMMSS
                                        date_part = part
                                        time_part = parts[i + 1]
                                        
                                        # Reconstruct ISO timestamp
                                        iso_timestamp = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}T{time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}+00:00"
                                        
                                        frame_dt = datetime.fromisoformat(iso_timestamp)
                                        time_diff = abs((target_dt - frame_dt).total_seconds())
                                        
                                        print(f"[REPORT] Found evidence {evidence_file.name} with timestamp {iso_timestamp}, diff: {time_diff:.1f}s")
                                        
                                        if time_diff < best_time_diff:
                                            best_time_diff = time_diff
                                            best_match = {
                                                'frame_file': evidence_file,
                                                'timestamp': frame_dt.isoformat(),
                                                'time_diff': time_diff
                                            }
                                        break
                    except Exception as e:
                        print(f"[REPORT] Error parsing evidence {evidence_file.name}: {e}")
                        continue
                
                # Also look for standard evidence frames
                for evidence_file in search_dir.glob("evidence_*.jpg"):
                    try:
                        # Try to extract timestamp from evidence filename
                        filename = evidence_file.stem
                        # Format: evidence_{plate}_{frame_number}_{timestamp}
                        parts = filename.split('_')
                        if len(parts) >= 4:
                            # Reconstruct timestamp from filename parts
                            timestamp_part = '_'.join(parts[3:])  # Everything after frame number
                            
                            # Handle timezone suffix (+0000)
                            if timestamp_part.endswith('+0000'):
                                timestamp_part = timestamp_part[:-5]  # Remove +0000
                            
                            # Convert back to ISO format
                            if len(timestamp_part) >= 15:  # YYYYMMDD_HHMMSS
                                date_part = timestamp_part[:8]  # YYYYMMDD
                                time_part = timestamp_part[9:15]  # HHMMSS
                                microseconds_part = timestamp_part[16:] if len(timestamp_part) > 16 else "000000"
                                
                                # Reconstruct ISO timestamp
                                iso_timestamp = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}T{time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}.{microseconds_part}+00:00"
                                
                                frame_dt = datetime.fromisoformat(iso_timestamp)
                                time_diff = abs((target_dt - frame_dt).total_seconds())
                                
                                print(f"[REPORT] Found evidence {evidence_file.name} with timestamp {iso_timestamp}, diff: {time_diff:.1f}s")
                                
                                if time_diff < best_time_diff:
                                    best_time_diff = time_diff
                                    best_match = {
                                        'frame_file': evidence_file,
                                        'timestamp': frame_dt.isoformat(),
                                        'time_diff': time_diff
                                    }
                    except Exception as e:
                        print(f"[REPORT] Error parsing evidence {evidence_file.name}: {e}")
                        continue
            
            if best_match and best_match['time_diff'] <= 3600:  # Within 1 hour
                frame_file = best_match['frame_file']
                
                # Read the frame file
                import base64
                with open(frame_file, 'rb') as f:
                    frame_data = base64.b64encode(f.read()).decode('utf-8')
                
                # Try to read metadata file (if exists)
                metadata_file = frame_file.with_suffix('.json')
                detections = []
                detection_counts = {'smoke': 0, 'vehicles': 0, 'plates': 0}
                
                if metadata_file.exists():
                    try:
                        with open(metadata_file, 'r') as f:
                            metadata = json.load(f)
                        
                        detections = metadata.get('smoke_detections', []) + metadata.get('vehicle_detections', []) + metadata.get('plate_detections', [])
                        detection_counts = metadata.get('detections', detection_counts)
                    except Exception as e:
                        print(f"[REPORT] Could not read metadata file: {e}")
                
                print(f"[REPORT] Found laptop violation frame {best_match['time_diff']:.1f}s from target timestamp")
                
                return {
                    'frame_data': frame_data,
                    'timestamp': best_match['timestamp'],
                    'detection_data': {
                        'camera_id': 'laptop_cam_001',
                        'location': 'Laptop_Detection',
                        'detections': detections,
                        'detection_counts': detection_counts
                    },
                    'detections': detections,
                    'source': 'laptop_violation_frame',
                    'time_diff_seconds': best_match['time_diff'],
                    'frame_path': str(frame_file),
                    'message': f'Found laptop violation frame {best_match["time_diff"]:.1f}s from detection time'
                }
            
            return None
            
        except Exception as e:
            print(f"[REPORT] Error getting laptop violation frame: {e}")
            import traceback
            traceback.print_exc()
            return None
            
        except Exception as e:
            print(f"[REPORT] Error getting frame from timestamp {timestamp}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _get_frame_from_files(self, violation_id: str) -> Optional[Dict]:
        """Get frame data from saved violation files"""
        try:
            # Check for saved violation frames in various directories
            frame_dirs = [
                Path("backend/detection_frames"),
                Path("esp32/evidence"),
                Path("evidence"),
                Path("saved_frames")
            ]
            
            for frame_dir in frame_dirs:
                if frame_dir.exists():
                    # Look for files containing the violation ID
                    for file_path in frame_dir.glob(f"*{violation_id}*"):
                        if file_path.is_file() and file_path.suffix.lower() in ['.jpg', '.jpeg', '.png']:
                            # Found a violation frame file
                            with open(file_path, 'rb') as f:
                                frame_data = base64.b64encode(f.read()).decode('utf-8')
                            
                            # Try to get timestamp from filename or file modification time
                            timestamp = datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                            
                            return {
                                'frame_data': frame_data,
                                'timestamp': timestamp,
                                'detection_data': {},
                                'detections': [],
                                'source': 'violation_file',
                                'file_path': str(file_path)
                            }
            
            return None
            
        except Exception as e:
            print(f"[REPORT] Error getting frame from files for violation {violation_id}: {e}")
            return None
    
    def _find_violation_evidence(self, violation_id: str) -> List[str]:
        """Find evidence files for a violation"""
        evidence_files = []
        
        # Check multiple possible evidence directories
        evidence_dirs = [
            Path("backend/detection_frames"),
            Path("backend/detection_frames/evidence"),
            Path("esp32/evidence"),
            Path("../esp32/evidence"),
            Path("evidence"),
            Path("D:/embed/SMOKI/esp32/evidence")  # Direct path to evidence directory
        ]
        
        for evidence_dir in evidence_dirs:
            if evidence_dir.exists():
                # Look for files containing the violation ID
                for file_path in evidence_dir.glob(f"*{violation_id}*"):
                    if file_path.is_file() and file_path.suffix.lower() in ['.jpg', '.jpeg', '.png']:
                        evidence_files.append(str(file_path))
        
        return evidence_files
    
    def _generate_violation_verification_html(self, violation_details: Dict, vehicle_details: Dict, 
                                            evidence_files: List[str], report_id: str, violation_frame_data: Dict) -> str:
        """Generate HTML content for violation verification report"""
        
        # Encode evidence images as base64
        evidence_images = []
        for evidence_file in evidence_files:
            try:
                with open(evidence_file, 'rb') as f:
                    image_data = base64.b64encode(f.read()).decode('utf-8')
                    evidence_images.append({
                        'filename': os.path.basename(evidence_file),
                        'data': image_data
                    })
            except Exception as e:
                print(f"Error encoding evidence file {evidence_file}: {e}")
        
        # Get violation timestamp for display
        violation_timestamp = violation_details.get('created_at')
        if violation_timestamp:
            if hasattr(violation_timestamp, 'strftime'):
                display_timestamp = violation_timestamp.strftime("%Y-%m-%d %H:%M:%S")
            else:
                display_timestamp = str(violation_timestamp)
        else:
            display_timestamp = "Unknown"
        
        # Get frame timestamp
        frame_timestamp = violation_frame_data.get('timestamp', 'Unknown')
        if frame_timestamp and frame_timestamp != 'Unknown':
            try:
                if isinstance(frame_timestamp, str):
                    frame_dt = datetime.fromisoformat(frame_timestamp.replace('Z', '+00:00'))
                    frame_display = frame_dt.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    frame_display = str(frame_timestamp)
            except:
                frame_display = str(frame_timestamp)
        else:
            frame_display = "Unknown"
        
        # Generate current timestamp for report
        report_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Get frame source info
        frame_source = violation_frame_data.get('source', 'unknown')
        frame_message = violation_frame_data.get('message', '')
        
        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SMOKi Violation Verification Report - {violation_details.get('id', 'Unknown')}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 2.5em;
            font-weight: 300;
        }}
        .header p {{
            margin: 10px 0 0 0;
            opacity: 0.9;
            font-size: 1.1em;
        }}
        .content {{
            padding: 30px;
        }}
        .violation-info {{
            background: #f8f9fa;
            border-radius: 10px;
            padding: 25px;
            margin-bottom: 30px;
            border-left: 5px solid #ff6b6b;
        }}
        .info-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }}
        .info-item {{
            background: white;
            padding: 15px;
            border-radius: 8px;
            border: 1px solid #e9ecef;
        }}
        .info-label {{
            font-weight: 600;
            color: #495057;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 5px;
        }}
        .info-value {{
            font-size: 1.1em;
            color: #212529;
        }}
        .license-plate {{
            background: #ffc107;
            color: #212529;
            padding: 8px 15px;
            border-radius: 5px;
            font-family: 'Courier New', monospace;
            font-weight: bold;
            font-size: 1.2em;
            display: inline-block;
        }}
        .status-badge {{
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.9em;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .status-pending {{
            background: #fff3cd;
            color: #856404;
        }}
        .status-approved {{
            background: #d4edda;
            color: #155724;
        }}
        .status-rejected {{
            background: #f8d7da;
            color: #721c24;
        }}
        .frame-section {{
            margin-top: 30px;
        }}
        .section-title {{
            font-size: 1.5em;
            font-weight: 600;
            color: #495057;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #e9ecef;
        }}
        .frame-container {{
            background: #f8f9fa;
            border-radius: 10px;
            padding: 20px;
            text-align: center;
            margin-bottom: 20px;
        }}
        .violation-frame {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            margin-bottom: 15px;
        }}
        .frame-info {{
            background: white;
            padding: 15px;
            border-radius: 8px;
            margin-top: 15px;
            text-align: left;
        }}
        .frame-timestamp {{
            font-size: 1.1em;
            font-weight: 600;
            color: #495057;
            margin-bottom: 10px;
        }}
        .frame-source {{
            font-size: 0.9em;
            color: #6c757d;
            font-style: italic;
        }}
        .no-frame {{
            text-align: center;
            color: #6c757d;
            font-style: italic;
            padding: 40px;
            background: #f8f9fa;
            border-radius: 10px;
        }}
        .evidence-section {{
            margin-top: 30px;
        }}
        .evidence-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }}
        .evidence-item {{
            background: #f8f9fa;
            border-radius: 10px;
            padding: 15px;
            text-align: center;
        }}
        .evidence-image {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            margin-bottom: 10px;
        }}
        .no-evidence {{
            text-align: center;
            color: #6c757d;
            font-style: italic;
            padding: 40px;
            background: #f8f9fa;
            border-radius: 10px;
        }}
        .verification-actions {{
            background: #e3f2fd;
            border-radius: 10px;
            padding: 25px;
            margin-top: 30px;
            text-align: center;
        }}
        .verification-title {{
            font-size: 1.3em;
            font-weight: 600;
            color: #1976d2;
            margin-bottom: 15px;
        }}
        .verification-text {{
            color: #495057;
            margin-bottom: 20px;
            line-height: 1.6;
        }}
        .action-buttons {{
            display: flex;
            gap: 15px;
            justify-content: center;
            flex-wrap: wrap;
        }}
        .btn {{
            padding: 12px 25px;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            transition: all 0.3s ease;
            cursor: pointer;
        }}
        .btn-approve {{
            background: #28a745;
            color: white;
        }}
        .btn-approve:hover {{
            background: #218838;
            transform: translateY(-2px);
        }}
        .btn-reject {{
            background: #dc3545;
            color: white;
        }}
        .btn-reject:hover {{
            background: #c82333;
            transform: translateY(-2px);
        }}
        .footer {{
            background: #f8f9fa;
            padding: 20px;
            text-align: center;
            color: #6c757d;
            font-size: 0.9em;
        }}
        .timestamp-info {{
            background: #fff3cd;
            border: 1px solid #ffeaa7;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
        }}
        .timestamp-label {{
            font-weight: 600;
            color: #856404;
            margin-bottom: 5px;
        }}
        .timestamp-value {{
            color: #856404;
            font-family: 'Courier New', monospace;
        }}
        @media (max-width: 768px) {{
            .container {{
                margin: 10px;
                border-radius: 10px;
            }}
            .header {{
                padding: 20px;
            }}
            .header h1 {{
                font-size: 2em;
            }}
            .content {{
                padding: 20px;
            }}
            .info-grid {{
                grid-template-columns: 1fr;
            }}
            .action-buttons {{
                flex-direction: column;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚨 Violation Verification Report</h1>
            <p>SMOKi Detection System - Violation ID: {violation_details.get('id', 'Unknown')}</p>
        </div>
        
        <div class="content">
            <div class="timestamp-info">
                <div class="timestamp-label">⏰ Violation Detection Time</div>
                <div class="timestamp-value">{display_timestamp}</div>
                <div style="margin-top: 10px;">
                    <div class="timestamp-label">📸 Frame Capture Time</div>
                    <div class="timestamp-value">{frame_display}</div>
                </div>
            </div>
            
            <div class="violation-info">
                <h2 style="margin-top: 0; color: #ff6b6b;">Violation Details</h2>
                <div class="info-grid">
                    <div class="info-item">
                        <div class="info-label">License Plate</div>
                        <div class="info-value">
                            <span class="license-plate">{vehicle_details.get('license_plate', 'Unknown') if vehicle_details else 'Unknown'}</span>
                        </div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Vehicle Type</div>
                        <div class="info-value">{vehicle_details.get('vehicle_type', 'Unknown') if vehicle_details else 'Unknown'}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Violation Type</div>
                        <div class="info-value">{violation_details.get('violation_type', 'Unknown')}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Severity</div>
                        <div class="info-value">{violation_details.get('severity', 'Unknown')}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Status</div>
                        <div class="info-value">
                            <span class="status-badge status-{violation_details.get('status', 'pending').lower()}">{violation_details.get('status', 'Pending')}</span>
                        </div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Detection Time</div>
                        <div class="info-value">{display_timestamp}</div>
                    </div>
                </div>
                
                {f'<div style="margin-top: 20px;"><div class="info-label">Description</div><div class="info-value" style="line-height: 1.6;">{violation_details.get("description", "No description available")}</div></div>' if violation_details.get('description') else ''}
            </div>
            
            <div class="frame-section">
                <h2 class="section-title">📹 Original Violation Frame</h2>
                {self._generate_violation_frame_html(violation_frame_data)}
            </div>
            
            <div class="evidence-section">
                <h2 class="section-title">📸 Evidence Images</h2>
                {self._generate_evidence_html(evidence_images)}
            </div>
            
            <div class="verification-actions">
                <div class="verification-title">⚖️ Verification Required</div>
                <div class="verification-text">
                    Please review the violation details, original frame, and evidence images above. 
                    The frame shown is from the exact time when the violation was detected ({frame_display}).
                    Based on your assessment, decide whether this violation should be approved or rejected.
                </div>
                <div class="action-buttons">
                    <button class="btn btn-approve" onclick="window.close(); alert('Return to dashboard to approve this violation.');">
                        ✅ Ready to Approve
                    </button>
                    <button class="btn btn-reject" onclick="window.close(); alert('Return to dashboard to reject this violation.');">
                        ❌ Ready to Reject
                    </button>
                </div>
            </div>
        </div>
        
        <div class="footer">
            <p>Report generated on {report_timestamp} | SMOKi Detection System v2.0</p>
            <p>Report ID: {report_id}</p>
            <p>Frame Source: {frame_source} | {frame_message}</p>
        </div>
    </div>
</body>
</html>
"""
        return html_content
    
    def _generate_violation_frame_html(self, violation_frame_data: Dict) -> str:
        """Generate HTML for the original violation frame"""
        frame_data = violation_frame_data.get('frame_data')
        
        if not frame_data:
            return '''
                <div class="no-frame">
                    <p>📷 Original violation frame not available</p>
                    <p>The frame from when this violation was detected could not be retrieved.</p>
                    <p>This may occur if frame storage is not enabled or files have been cleaned up.</p>
                </div>
            '''
        
        frame_source = violation_frame_data.get('source', 'unknown')
        frame_timestamp = violation_frame_data.get('timestamp', 'Unknown')
        
        return f'''
            <div class="frame-container">
                <img src="data:image/jpeg;base64,{frame_data}" alt="Original Violation Frame" class="violation-frame">
                <div class="frame-info">
                    <div class="frame-timestamp">📸 Frame captured at: {frame_timestamp}</div>
                    <div class="frame-source">Source: {frame_source}</div>
                </div>
            </div>
        '''
    
    def _get_evidence_statistics(self) -> Dict:
        """Get statistics about evidence files"""
        try:
            evidence_dirs = [
                Path("D:/embed/SMOKI/esp32/evidence"),
                Path("esp32/evidence"),
                Path("../esp32/evidence"),
                Path("backend/detection_frames/evidence")
            ]
            
            stats = {
                'total_files': 0,
                'recent_violations': 0,
                'unique_plates': set(),
                'file_sizes': 0
            }
            
            from datetime import datetime, timedelta
            cutoff_time = datetime.now() - timedelta(hours=24)
            
            for evidence_dir in evidence_dirs:
                if not evidence_dir.exists():
                    continue
                
                for evidence_file in evidence_dir.glob("violation_evidence_*.jpg"):
                    try:
                        stats['total_files'] += 1
                        stats['file_sizes'] += evidence_file.stat().st_size
                        
                        # Check if recent
                        file_time = datetime.fromtimestamp(evidence_file.stat().st_mtime)
                        if file_time > cutoff_time:
                            stats['recent_violations'] += 1
                        
                        # Extract license plate from filename
                        filename_parts = evidence_file.stem.split('_')
                        if len(filename_parts) >= 3:
                            plate = filename_parts[2]  # violation_evidence_PLATE_timestamp
                            stats['unique_plates'].add(plate)
                            
                    except Exception as e:
                        continue
                
                # Only use the first directory that has files
                if stats['total_files'] > 0:
                    break
            
            stats['unique_plates'] = len(stats['unique_plates'])
            return stats
            
        except Exception as e:
            print(f"[REPORT] Error getting evidence statistics: {e}")
            return {'total_files': 0, 'recent_violations': 0, 'unique_plates': 0, 'file_sizes': 0}
    
    def _generate_evidence_gallery(self) -> str:
        """Generate comprehensive evidence gallery from D:\\embed\\SMOKI\\esp32\\evidence directory"""
        try:
            evidence_dirs = [
                Path("D:/embed/SMOKI/esp32/evidence"),
                Path("esp32/evidence"),
                Path("../esp32/evidence"),
                Path("backend/detection_frames/evidence")
            ]
            
            evidence_files = []
            
            for evidence_dir in evidence_dirs:
                if not evidence_dir.exists():
                    continue
                
                print(f"[REPORT] Scanning evidence directory: {evidence_dir}")
                
                # Get all evidence files
                for evidence_file in evidence_dir.glob("violation_evidence_*.jpg"):
                    try:
                        # Read metadata if available
                        metadata_file = evidence_file.with_suffix('.json')
                        metadata = {}
                        if metadata_file.exists():
                            with open(metadata_file, 'r') as f:
                                metadata = json.load(f)
                        
                        # Read and encode image
                        with open(evidence_file, 'rb') as f:
                            img_data = base64.b64encode(f.read()).decode('utf-8')
                        
                        # Get file stats
                        stat = evidence_file.stat()
                        
                        # Extract info from filename if metadata is missing
                        filename_parts = evidence_file.stem.split('_')
                        extracted_plate = filename_parts[2] if len(filename_parts) >= 3 else 'Unknown'
                        
                        evidence_files.append({
                            'filename': evidence_file.name,
                            'path': str(evidence_file),
                            'image_data': img_data,
                            'license_plate': metadata.get('license_plate', extracted_plate),
                            'vehicle_type': metadata.get('vehicle_type', 'Unknown'),
                            'smoke_type': metadata.get('smoke_type', 'Unknown'),
                            'timestamp': metadata.get('timestamp', 'Unknown'),
                            'distance': metadata.get('distance', 0),
                            'vehicle_confidence': metadata.get('vehicle_confidence', 0),
                            'smoke_confidence': metadata.get('smoke_confidence', 0),
                            'ocr_confidence': metadata.get('ocr_confidence', 0),
                            'has_readable_plate': metadata.get('has_readable_plate', False),
                            'modified_time': stat.st_mtime,
                            'file_size': stat.st_size
                        })
                    except Exception as e:
                        print(f"[REPORT] Error processing evidence file {evidence_file}: {e}")
                        continue
                
                # Only use the first directory that has files
                if evidence_files:
                    print(f"[REPORT] Found {len(evidence_files)} evidence files in {evidence_dir}")
                    break
            
            if not evidence_files:
                return """
                <div class="evidence-gallery-section">
                    <h3>📸 Evidence Gallery</h3>
                    <div class="no-evidence-message">
                        <div class="no-evidence-icon">📷</div>
                        <h4>Evidence Files Not Available on Production Server</h4>
                        <p>Evidence files are stored locally at <code>D:\\embed\\SMOKI\\esp32\\evidence</code> and are not accessible from the remote production server.</p>
                        <div class="evidence-help">
                            <h5>📋 To View Evidence Files:</h5>
                            <ul>
                                <li><strong>Local Access:</strong> Check <code>D:\\embed\\SMOKI\\esp32\\evidence</code> on your local machine</li>
                                <li><strong>Evidence Files:</strong> <code>violation_evidence_PLATE_TIMESTAMP.jpg</code></li>
                                <li><strong>Metadata:</strong> <code>violation_evidence_PLATE_TIMESTAMP.json</code></li>
                                <li><strong>Generated by:</strong> laptop_snap.py when violations are detected</li>
                            </ul>
                            <h5>🔧 For Production Evidence Gallery:</h5>
                            <ul>
                                <li>Upload evidence files to a cloud storage service</li>
                                <li>Configure the report generator to access remote evidence storage</li>
                                <li>Or run reports locally where evidence files are accessible</li>
                            </ul>
                        </div>
                        <div class="production-note">
                            <h5>💡 Current Setup:</h5>
                            <p>This report is generated on the production server (<code>smoki-backend-rpi.onrender.com</code>) which cannot access local evidence files. The enhanced report generator is working correctly, but evidence files need to be accessible to the server to display the interactive gallery.</p>
                        </div>
                    </div>
                </div>
                """
            
            # Sort by modification time (newest first)
            evidence_files.sort(key=lambda x: x['modified_time'], reverse=True)
            
            # Generate statistics
            total_files = len(evidence_files)
            unique_plates = len(set(f['license_plate'] for f in evidence_files))
            total_size = sum(f['file_size'] for f in evidence_files)
            readable_plates = sum(1 for f in evidence_files if f['has_readable_plate'])
            
            from datetime import datetime, timedelta
            cutoff_time = datetime.now() - timedelta(hours=24)
            recent_files = sum(1 for f in evidence_files if datetime.fromtimestamp(f['modified_time']) > cutoff_time)
            
            gallery_html = f"""
            <div class="evidence-gallery-section">
                <div class="evidence-header">
                    <h3>📸 Complete Evidence Gallery - Select Images for Report</h3>
                    <div class="gallery-description">
                        <p><strong>📋 Instructions:</strong> Review all violation evidence below and select which images to include in your official report.</p>
                        <p><strong>⚠️ Important:</strong> Since CV detection isn't perfect, please verify each image before including it in enforcement reports.</p>
                    </div>
                    <div class="evidence-stats">
                        <div class="stat-item">
                            <span class="stat-number">{total_files}</span>
                            <span class="stat-label">Total Files</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-number">{unique_plates}</span>
                            <span class="stat-label">Unique Plates</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-number">{readable_plates}</span>
                            <span class="stat-label">Readable Plates</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-number">{recent_files}</span>
                            <span class="stat-label">Recent (24h)</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-number">{total_size / (1024*1024):.1f}MB</span>
                            <span class="stat-label">Total Size</span>
                        </div>
                    </div>
                </div>
                
                <div class="evidence-controls">
                    <div class="selection-controls">
                        <button class="control-btn select-all" onclick="selectAllEvidence()">✅ Select All ({total_files})</button>
                        <button class="control-btn deselect-all" onclick="deselectAllEvidence()">❌ Deselect All</button>
                        <button class="control-btn select-readable" onclick="selectReadableOnly()">📋 Readable Only ({readable_plates})</button>
                        <button class="control-btn select-recent" onclick="selectRecentOnly()">🕒 Recent Only ({recent_files})</button>
                        <button class="control-btn select-high-conf" onclick="selectHighConfidenceOnly()">⭐ High Confidence</button>
                    </div>
                    <div class="selection-info">
                        <div class="selection-counter">
                            <span id="selectedCount">0</span> of {total_files} images selected for report
                        </div>
                        <div class="selection-details" id="selectionDetails">
                            No images selected
                        </div>
                    </div>
                </div>
                
                <div class="evidence-grid">
            """
            
            for i, evidence in enumerate(evidence_files):
                plate_status = "✅ Readable" if evidence['has_readable_plate'] else "⚠️ Unreadable"
                plate_class = "readable" if evidence['has_readable_plate'] else "unreadable"
                
                # Format timestamp for display
                try:
                    if evidence['timestamp'] != 'Unknown':
                        dt = datetime.fromisoformat(evidence['timestamp'].replace('Z', '+00:00'))
                        display_time = dt.strftime('%m/%d %H:%M')
                        full_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        dt = datetime.fromtimestamp(evidence['modified_time'])
                        display_time = dt.strftime('%m/%d %H:%M')
                        full_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    display_time = 'Unknown'
                    full_time = 'Unknown'
                
                # Check if recent (within 24 hours)
                is_recent = datetime.fromtimestamp(evidence['modified_time']) > cutoff_time
                recent_badge = '<span class="recent-badge">🆕 New</span>' if is_recent else ''
                
                # Confidence indicators
                confidence_class = "high" if (evidence['vehicle_confidence'] > 0.7 and evidence['smoke_confidence'] > 0.7) else "medium" if (evidence['vehicle_confidence'] > 0.5 and evidence['smoke_confidence'] > 0.5) else "low"
                
                gallery_html += f"""
                <div class="evidence-card" data-plate="{evidence['license_plate']}" data-recent="{is_recent}" data-readable="{evidence['has_readable_plate']}" data-confidence="{confidence_class}">
                    <div class="evidence-selector">
                        <input type="checkbox" id="evidence_{i}" class="evidence-checkbox" 
                               data-filename="{evidence['filename']}" 
                               data-plate="{evidence['license_plate']}"
                               data-vehicle="{evidence['vehicle_type']}"
                               data-smoke="{evidence['smoke_type']}"
                               data-timestamp="{evidence['timestamp']}"
                               data-confidence="{evidence['vehicle_confidence']:.2f}"
                               data-smoke-confidence="{evidence['smoke_confidence']:.2f}"
                               onchange="updateSelectedEvidence()">
                        <label for="evidence_{i}" class="checkbox-label">
                            <span class="checkbox-icon">☐</span>
                            <span class="checkbox-text">Include in Report</span>
                        </label>
                    </div>
                    
                    <div class="evidence-image-container">
                        <img src="data:image/jpeg;base64,{evidence['image_data']}" 
                             alt="Evidence for {evidence['license_plate']}" 
                             class="evidence-image"
                             onclick="openImageModal('{evidence['filename']}', 'data:image/jpeg;base64,{evidence['image_data']}', '{evidence['license_plate']}', '{full_time}')">
                        
                        <div class="evidence-overlay">
                            <div class="evidence-plate-badge">{evidence['license_plate']}</div>
                            <div class="evidence-badges">
                                {recent_badge}
                                <span class="confidence-badge {confidence_class}">
                                    {confidence_class.upper()}
                                </span>
                            </div>
                        </div>
                        
                        <div class="evidence-status-bar">
                            <span class="plate-status {plate_class}">{plate_status}</span>
                            <span class="confidence-indicator {confidence_class}">
                                V:{evidence['vehicle_confidence']:.2f} S:{evidence['smoke_confidence']:.2f}
                            </span>
                        </div>
                        
                        <div class="evidence-actions">
                            <button class="action-btn preview-btn" onclick="openImageModal('{evidence['filename']}', 'data:image/jpeg;base64,{evidence['image_data']}', '{evidence['license_plate']}', '{full_time}')">
                                🔍 Preview
                            </button>
                            <button class="action-btn info-btn" onclick="showEvidenceInfo('{evidence['filename']}', {json.dumps(evidence, default=str)})">
                                ℹ️ Details
                            </button>
                        </div>
                    </div>
                    
                    <div class="evidence-details">
                        <div class="evidence-title">{evidence['license_plate']}</div>
                        <div class="evidence-subtitle">{evidence['vehicle_type']} • {evidence['smoke_type']}</div>
                        
                        <div class="evidence-meta">
                            <div class="meta-row">
                                <span class="meta-label">📅 Time:</span>
                                <span class="meta-value" title="{full_time}">{display_time}</span>
                            </div>
                            <div class="meta-row">
                                <span class="meta-label">📏 Size:</span>
                                <span class="meta-value">{evidence['file_size'] / 1024:.1f} KB</span>
                            </div>
                            <div class="meta-row">
                                <span class="meta-label">🎯 Vehicle:</span>
                                <span class="meta-value">{evidence['vehicle_confidence']:.1%}</span>
                            </div>
                            <div class="meta-row">
                                <span class="meta-label">💨 Smoke:</span>
                                <span class="meta-value">{evidence['smoke_confidence']:.1%}</span>
                            </div>
                            {f'''<div class="meta-row">
                                <span class="meta-label">📝 OCR:</span>
                                <span class="meta-value">{evidence['ocr_confidence']:.1%}</span>
                            </div>''' if evidence['ocr_confidence'] > 0 else ''}
                        </div>
                        
                        <div class="evidence-quality">
                            <div class="quality-indicator {confidence_class}">
                                <span class="quality-dot"></span>
                                <span class="quality-text">
                                    {confidence_class.title()} Confidence
                                </span>
                            </div>
                        </div>
                    </div>
                </div>
                """
            
            gallery_html += """
                </div>
                
                <div class="report-actions">
                    <div class="report-header">
                        <h4>📊 Generate Report</h4>
                        <p>Select evidence images above and generate reports.</p>
                    </div>
                    
                    <div class="report-buttons">
                        <button class="report-btn primary large" onclick="generateSelectedReport()" id="generateReportBtn" disabled>
                            📊 Generate Report
                        </button>
                        <button class="report-btn email gmail" onclick="sendEmailReport('gmail')" id="emailGmailBtn" disabled>
                            📧 Email Report
                        </button>
                        <button class="report-btn download" onclick="downloadSelectedEvidence()" id="downloadBtn" disabled>
                            💾 Download Files
                        </button>
                    </div>
                    
                    <div class="email-template">
                        <div class="template-row">
                            <label for="emailRecipient">📧 Email To:</label>
                            <input type="email" id="emailRecipient" placeholder="enforcement@agency.gov" class="email-input">
                        </div>
                        
                        <div class="template-row">
                            <label for="emailBody">📄 Message:</label>
                            <textarea id="emailBody" class="email-textarea" rows="4">Evidence of smoking violations detected by SMOKi system.

Selected files: {total_files} evidence images
Detection date: {datetime.now().strftime('%Y-%m-%d')}

Please review and take appropriate action.</textarea>
                        </div>
                    </div>
                </div>
            </div>
            """
            
            return gallery_html
            
        except Exception as e:
            print(f"[REPORT] Error generating evidence gallery: {e}")
            import traceback
            traceback.print_exc()
            return f"""
            <div class="evidence-gallery-section">
                <h3>📸 Evidence Gallery</h3>
                <div class="error-message">
                    <div class="error-icon">⚠️</div>
                    <h4>Error Loading Evidence Gallery</h4>
                    <p>Error: {e}</p>
                    <p>Please check that the evidence directory exists and contains files.</p>
                </div>
            </div>
            """
        """Generate evidence gallery from D:\\embed\\SMOKI\\esp32\\evidence directory"""
        try:
            evidence_dirs = [
                Path("D:/embed/SMOKI/esp32/evidence"),
                Path("esp32/evidence"),
                Path("../esp32/evidence"),
                Path("backend/detection_frames/evidence")
            ]
            
            evidence_files = []
            
            for evidence_dir in evidence_dirs:
                if not evidence_dir.exists():
                    continue
                
                # Get all evidence files
                for evidence_file in evidence_dir.glob("violation_evidence_*.jpg"):
                    try:
                        # Read metadata if available
                        metadata_file = evidence_file.with_suffix('.json')
                        metadata = {}
                        if metadata_file.exists():
                            with open(metadata_file, 'r') as f:
                                metadata = json.load(f)
                        
                        # Read and encode image
                        with open(evidence_file, 'rb') as f:
                            img_data = base64.b64encode(f.read()).decode('utf-8')
                        
                        # Get file stats
                        stat = evidence_file.stat()
                        
                        evidence_files.append({
                            'filename': evidence_file.name,
                            'path': str(evidence_file),
                            'image_data': img_data,
                            'license_plate': metadata.get('license_plate', 'Unknown'),
                            'vehicle_type': metadata.get('vehicle_type', 'Unknown'),
                            'smoke_type': metadata.get('smoke_type', 'Unknown'),
                            'timestamp': metadata.get('timestamp', 'Unknown'),
                            'distance': metadata.get('distance', 0),
                            'vehicle_confidence': metadata.get('vehicle_confidence', 0),
                            'smoke_confidence': metadata.get('smoke_confidence', 0),
                            'has_readable_plate': metadata.get('has_readable_plate', False),
                            'modified_time': stat.st_mtime,
                            'file_size': stat.st_size
                        })
                    except Exception as e:
                        print(f"[REPORT] Error processing evidence file {evidence_file}: {e}")
                        continue
                
                # Only use the first directory that has files
                if evidence_files:
                    break
            
            if not evidence_files:
                return """
                <div class="evidence-gallery-section">
                    <h3>📸 Evidence Gallery</h3>
                    <div class="no-evidence">
                        <p>No evidence files found in D:\\embed\\SMOKI\\esp32\\evidence</p>
                        <p>Run laptop_snap.py to detect violations and generate evidence.</p>
                    </div>
                </div>
                """
            
            # Sort by modification time (newest first)
            evidence_files.sort(key=lambda x: x['modified_time'], reverse=True)
            
            # Limit to most recent 10 files to avoid huge reports
            evidence_files = evidence_files[:10]
            
            gallery_html = """
            <div class="evidence-gallery-section">
                <h3>📸 Evidence Gallery - Select Images for Email Report</h3>
                <p class="gallery-description">
                    Select evidence images below to include in your email report. 
                    These images are from the CV detection system and may need verification for accuracy.
                </p>
                <div class="evidence-gallery">
            """
            
            for i, evidence in enumerate(evidence_files):
                plate_status = "✅ Readable" if evidence['has_readable_plate'] else "⚠️ Unreadable"
                plate_class = "readable" if evidence['has_readable_plate'] else "unreadable"
                
                # Format timestamp for display
                try:
                    if evidence['timestamp'] != 'Unknown':
                        from datetime import datetime
                        dt = datetime.fromisoformat(evidence['timestamp'].replace('Z', '+00:00'))
                        display_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        display_time = datetime.fromtimestamp(evidence['modified_time']).strftime('%Y-%m-%d %H:%M:%S')
                except:
                    display_time = 'Unknown'
                
                gallery_html += f"""
                <div class="evidence-gallery-item">
                    <div class="evidence-selector">
                        <input type="checkbox" id="evidence_{i}" class="evidence-checkbox" 
                               data-filename="{evidence['filename']}" 
                               data-plate="{evidence['license_plate']}"
                               data-vehicle="{evidence['vehicle_type']}"
                               data-smoke="{evidence['smoke_type']}"
                               onchange="updateSelectedEvidence()">
                        <label for="evidence_{i}" class="evidence-label">
                            <span class="checkbox-custom"></span>
                            Include in Email
                        </label>
                    </div>
                    
                    <div class="evidence-preview">
                        <img src="data:image/jpeg;base64,{evidence['image_data']}" 
                             alt="Evidence for {evidence['license_plate']}" 
                             class="evidence-thumbnail"
                             onclick="openImageModal('{evidence['filename']}', 'data:image/jpeg;base64,{evidence['image_data']}')">
                        <div class="evidence-overlay">
                            <span class="evidence-plate">{evidence['license_plate']}</span>
                            <span class="evidence-status {plate_class}">{plate_status}</span>
                        </div>
                    </div>
                    
                    <div class="evidence-info">
                        <div class="evidence-details">
                            <p><strong>License Plate:</strong> {evidence['license_plate']}</p>
                            <p><strong>Vehicle:</strong> {evidence['vehicle_type']}</p>
                            <p><strong>Smoke Type:</strong> {evidence['smoke_type']}</p>
                            <p><strong>Detection Time:</strong> {display_time}</p>
                            <p><strong>Distance:</strong> {evidence['distance']:.1f}px</p>
                            <p><strong>Confidence:</strong> V:{evidence['vehicle_confidence']:.2f} S:{evidence['smoke_confidence']:.2f}</p>
                            <p><strong>File Size:</strong> {evidence['file_size'] / 1024:.1f} KB</p>
                        </div>
                    </div>
                </div>
                """
            
            gallery_html += """
                </div>
                
                <div class="email-actions">
                    <h4>📧 Email Report Actions</h4>
                    <div class="selected-count">
                        <span id="selectedCount">0</span> evidence images selected
                    </div>
                    <div class="email-buttons">
                        <button class="action-btn email-btn gmail" onclick="sendEmailReport('gmail')">
                            📧 Send via Gmail
                        </button>
                        <button class="action-btn email-btn outlook" onclick="sendEmailReport('outlook')">
                            📧 Send via Outlook
                        </button>
                        <button class="action-btn email-btn download" onclick="downloadSelectedEvidence()">
                            💾 Download Selected
                        </button>
                    </div>
                    <div class="email-template">
                        <label for="emailSubject">Email Subject:</label>
                        <input type="text" id="emailSubject" value="SMOKi Violation Report - {datetime.now().strftime('%Y-%m-%d')}" class="email-input">
                        
                        <label for="emailBody">Email Body:</label>
                        <textarea id="emailBody" class="email-textarea" rows="4">Dear Enforcement Team,

Please find attached evidence of smoking violations detected by the SMOKi system.

Detection Summary:
- Total Evidence Files: {len(evidence_files)}
- Detection Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- System: SMOKi Automated Detection

Please review the attached evidence and take appropriate action.

Best regards,
SMOKi Detection System</textarea>
                    </div>
                </div>
            </div>
            """
            
            return gallery_html
            
        except Exception as e:
            print(f"[REPORT] Error generating evidence gallery: {e}")
            import traceback
            traceback.print_exc()
            return f"""
            <div class="evidence-gallery-section">
                <h3>📸 Evidence Gallery</h3>
                <div class="error">
                    <p>Error loading evidence gallery: {e}</p>
                </div>
            </div>
            """
        """Generate HTML for evidence images"""
        if not evidence_images:
            return '''
                <div class="no-evidence">
                    <p>📷 No evidence images available for this violation</p>
                    <p>Evidence may not have been captured or files may have been moved.</p>
                </div>
            '''
        
        evidence_html = '<div class="evidence-grid">'
        for i, image in enumerate(evidence_images, 1):
            evidence_html += f'''
                <div class="evidence-item">
                    <img src="data:image/jpeg;base64,{image['data']}" alt="Evidence {i}" class="evidence-image">
                    <p><strong>Evidence {i}:</strong> {image['filename']}</p>
                </div>
            '''
        evidence_html += '</div>'
        
        return evidence_html

# Example usage
if __name__ == "__main__":
    generator = SMOKiReportGenerator()
    result = generator.generate_report("smoke_detection")
    print(json.dumps(result, indent=2))