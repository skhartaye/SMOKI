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
            from stream import stream_manager
            
            # Get current frame from local stream manager
            frame_data = None
            latest_frame = stream_manager.get_latest_frame()
            if latest_frame:
                frame_data = base64.b64encode(latest_frame).decode('utf-8')
            
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
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            print(f"Error fetching current data from stream manager: {e}")
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
            'plate_detections': 0
        }
        
        for detection in detections:
            class_name = detection.get('class_name', '').lower()
            if 'smoke' in class_name:
                summary['smoke_detections'] += 1
            elif class_name in ['passenger', 'puv', 'services', 'two_wheel']:
                summary['vehicle_detections'] += 1
            elif 'license' in class_name or 'plate' in class_name:
                summary['plate_detections'] += 1
        
        return summary
    
    def generate_html_report(self, report_data: Dict, report_type: str = "general") -> str:
        """Generate HTML report with current frame and detection data"""
        
        timestamp = datetime.now(timezone.utc)
        report_id = f"SMOKi_Report_{timestamp.strftime('%Y%m%d_%H%M%S')}"
        
        # Extract detection information
        detections = report_data.get('detection_data', {}).get('latest_detections', [])
        detection_summary = report_data.get('detection_data', {}).get('detection_summary', {})
        camera_info = report_data.get('detection_data', {}).get('camera_info', {})
        
        # Count detections by type
        smoke_count = detection_summary.get('smoke_detections', 0)
        vehicle_count = detection_summary.get('vehicle_detections', 0)
        plate_count = detection_summary.get('plate_detections', 0)
        
        # Determine report severity
        severity = "LOW"
        severity_color = "#28a745"
        if smoke_count > 0:
            severity = "HIGH"
            severity_color = "#dc3545"
        elif vehicle_count > 0:
            severity = "MEDIUM"
            severity_color = "#ffc107"
        
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
            frame_html = f"""
            <div class="frame-container">
                <h3>Current Frame</h3>
                <img src="data:image/jpeg;base64,{report_data['frame_data']}" 
                     alt="Current camera frame with detections" 
                     class="camera-frame">
                <p class="frame-caption">
                    Frame captured at {timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')} 
                    from {camera_info.get('location', 'Main Camera Station')}
                </p>
            </div>
            """
        else:
            frame_html = """
            <div class="frame-container">
                <h3>Current Frame</h3>
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
        .detection-summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }}
        .summary-item {{
            text-align: center;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
            border: 2px solid #e9ecef;
        }}
        .summary-number {{
            font-size: 2.5em;
            font-weight: bold;
            color: #667eea;
            margin: 0;
        }}
        .summary-label {{
            color: #6c757d;
            font-size: 0.9em;
            margin: 5px 0 0 0;
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
            .detection-summary {{
                grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
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
            
            <h3>Detection Summary</h3>
            <div class="detection-summary">
                <div class="summary-item">
                    <div class="summary-number">{smoke_count}</div>
                    <div class="summary-label">Smoke Detections</div>
                </div>
                <div class="summary-item">
                    <div class="summary-number">{vehicle_count}</div>
                    <div class="summary-label">Vehicle Detections</div>
                </div>
                <div class="summary-item">
                    <div class="summary-number">{plate_count}</div>
                    <div class="summary-label">License Plates</div>
                </div>
                <div class="summary-item">
                    <div class="summary-number">{len(detections)}</div>
                    <div class="summary-label">Total Objects</div>
                </div>
            </div>
            
            {frame_html}
            
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
                text: 'SMOKi Detection Report\\n\\nReport ID: {report_id}\\nGenerated: {timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}\\nSeverity: {severity}\\n\\nDetection Summary:\\n- Smoke Detections: {smoke_count}\\n- Vehicle Detections: {vehicle_count}\\n- License Plates: {plate_count}',
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
        }});
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
    
    def generate_report(self, report_type: str = "general") -> Dict:
        """Generate a complete report with current data"""
        try:
            # Get current frame and detection data
            current_data = self.get_current_frame_and_data()
            
            # Generate HTML report
            report_path = self.generate_html_report(current_data, report_type)
            
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

# Example usage
if __name__ == "__main__":
    generator = SMOKiReportGenerator()
    result = generator.generate_report("smoke_detection")
    print(json.dumps(result, indent=2))