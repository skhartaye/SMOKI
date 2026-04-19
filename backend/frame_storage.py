#!/usr/bin/env python3
"""
Local Frame Storage System
Saves detection frames locally for later retrieval in reports
"""
import os
import cv2
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict
import json

class LocalFrameStorage:
    """Manages local storage of detection frames"""
    
    def __init__(self, storage_dir: str = "detection_frames"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)
        
        # Create subdirectories
        self.frames_dir = self.storage_dir / "frames"
        self.metadata_dir = self.storage_dir / "metadata"
        self.frames_dir.mkdir(exist_ok=True)
        self.metadata_dir.mkdir(exist_ok=True)
        
        print(f"[FRAME_STORAGE] Initialized with storage directory: {self.storage_dir}")
    
    def save_detection_frame(self, frame_data: bytes, timestamp: datetime, 
                           detections: list, metadata: dict = None) -> str:
        """Save a detection frame with timestamp and metadata"""
        try:
            # Generate filename based on timestamp
            timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S_%f")[:-3]  # Include milliseconds
            frame_filename = f"frame_{timestamp_str}.jpg"
            metadata_filename = f"frame_{timestamp_str}.json"
            
            frame_path = self.frames_dir / frame_filename
            metadata_path = self.metadata_dir / metadata_filename
            
            # Convert bytes to image and save
            nparr = np.frombuffer(frame_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is not None:
                # Save frame with high quality
                cv2.imwrite(str(frame_path), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
                
                # Save metadata
                frame_metadata = {
                    'timestamp': timestamp.isoformat(),
                    'frame_filename': frame_filename,
                    'detections': detections,
                    'detection_counts': {
                        'smoke': sum(1 for d in detections if 'smoke' in d.get('class_name', '').lower()),
                        'vehicles': sum(1 for d in detections if d.get('class_name', '').lower() in ['passenger', 'puv', 'services', 'two_wheel', 'vehicle']),
                        'plates': sum(1 for d in detections if 'license' in d.get('class_name', '').lower() or 'plate' in d.get('class_name', '').lower())
                    },
                    'original_metadata': metadata or {}
                }
                
                with open(metadata_path, 'w') as f:
                    json.dump(frame_metadata, f, indent=2)
                
                print(f"[FRAME_STORAGE] Saved frame: {frame_filename} with {len(detections)} detections")
                return str(frame_path)
            else:
                print(f"[FRAME_STORAGE] Failed to decode frame data")
                return None
                
        except Exception as e:
            print(f"[FRAME_STORAGE] Error saving frame: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_frame_by_timestamp(self, target_timestamp: datetime, tolerance_seconds: int = 300) -> Optional[Dict]:
        """Get the closest frame to a target timestamp"""
        try:
            best_match = None
            best_diff = float('inf')
            
            # Search through metadata files
            for metadata_file in self.metadata_dir.glob("frame_*.json"):
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                    
                    frame_timestamp = datetime.fromisoformat(metadata['timestamp'])
                    time_diff = abs((target_timestamp - frame_timestamp).total_seconds())
                    
                    if time_diff < best_diff and time_diff <= tolerance_seconds:
                        best_diff = time_diff
                        best_match = {
                            'metadata': metadata,
                            'time_diff': time_diff,
                            'frame_path': self.frames_dir / metadata['frame_filename']
                        }
                
                except Exception as e:
                    continue
            
            if best_match:
                # Load the frame data
                frame_path = best_match['frame_path']
                if frame_path.exists():
                    # Read frame and convert to base64
                    img = cv2.imread(str(frame_path))
                    if img is not None:
                        _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 95])
                        import base64
                        frame_b64 = base64.b64encode(buffer).decode('utf-8')
                        
                        return {
                            'frame_data': frame_b64,
                            'timestamp': best_match['metadata']['timestamp'],
                            'detections': best_match['metadata']['detections'],
                            'detection_counts': best_match['metadata']['detection_counts'],
                            'time_diff_seconds': best_match['time_diff'],
                            'source': 'local_storage',
                            'frame_path': str(frame_path)
                        }
            
            return None
            
        except Exception as e:
            print(f"[FRAME_STORAGE] Error retrieving frame: {e}")
            return None
    
    def cleanup_old_frames(self, max_age_hours: int = 24):
        """Clean up frames older than specified hours"""
        try:
            from datetime import timedelta
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
            
            deleted_count = 0
            for metadata_file in self.metadata_dir.glob("frame_*.json"):
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                    
                    frame_timestamp = datetime.fromisoformat(metadata['timestamp'])
                    if frame_timestamp < cutoff_time:
                        # Delete metadata file
                        metadata_file.unlink()
                        
                        # Delete corresponding frame file
                        frame_file = self.frames_dir / metadata['frame_filename']
                        if frame_file.exists():
                            frame_file.unlink()
                        
                        deleted_count += 1
                
                except Exception as e:
                    continue
            
            if deleted_count > 0:
                print(f"[FRAME_STORAGE] Cleaned up {deleted_count} old frames")
            
        except Exception as e:
            print(f"[FRAME_STORAGE] Error during cleanup: {e}")
    
    def get_storage_stats(self) -> Dict:
        """Get statistics about stored frames"""
        try:
            frame_count = len(list(self.frames_dir.glob("frame_*.jpg")))
            metadata_count = len(list(self.metadata_dir.glob("frame_*.json")))
            
            # Calculate total size
            total_size = 0
            for frame_file in self.frames_dir.glob("frame_*.jpg"):
                total_size += frame_file.stat().st_size
            
            return {
                'frame_count': frame_count,
                'metadata_count': metadata_count,
                'total_size_mb': total_size / (1024 * 1024),
                'storage_dir': str(self.storage_dir)
            }
        except Exception as e:
            return {'error': str(e)}

# Global instance
frame_storage = LocalFrameStorage()