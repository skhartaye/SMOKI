"""
Image Cropping Worker for Detection Evidence
Crops detection frames to show only relevant areas (vehicle + smoke) with padding
"""

import cv2
import numpy as np
import os
from datetime import datetime
from typing import List, Dict, Tuple, Optional
import json

class DetectionImageCropper:
    def __init__(self, padding_pixels: int = 100):
        """
        Initialize the image cropper
        
        Args:
            padding_pixels: Pixels to add around the detection bounding box
        """
        self.padding_pixels = padding_pixels
        self.cropped_frames_dir = "detection_frames/cropped"
        
        # Create cropped frames directory if it doesn't exist
        os.makedirs(self.cropped_frames_dir, exist_ok=True)
        
    def calculate_combined_bbox(self, detections: List[Dict], image_shape: Tuple[int, int]) -> Optional[Dict]:
        """
        Calculate a combined bounding box that encompasses all relevant detections
        
        Args:
            detections: List of detection objects with bbox information
            image_shape: (height, width) of the image
            
        Returns:
            Combined bounding box dict or None if no valid detections
        """
        if not detections:
            return None
            
        height, width = image_shape
        
        # Find all relevant bounding boxes (vehicles and smoke)
        relevant_bboxes = []
        
        for detection in detections:
            class_name = detection.get('class_name', '').lower()
            bbox = detection.get('bbox', {})
            
            # Check if this is a relevant detection (vehicle or smoke)
            is_vehicle = class_name in ['passenger', 'puv', 'services', 'two_wheel', 'vehicle', 'car', 'truck', 'bus', 'motorcycle']
            is_smoke = 'smoke' in class_name
            
            if (is_vehicle or is_smoke) and bbox:
                # Extract bounding box coordinates
                # Support different bbox formats
                if 'x' in bbox and 'y' in bbox and 'width' in bbox and 'height' in bbox:
                    # Format: {x, y, width, height}
                    x1 = int(bbox['x'])
                    y1 = int(bbox['y'])
                    x2 = int(bbox['x'] + bbox['width'])
                    y2 = int(bbox['y'] + bbox['height'])
                elif 'x1' in bbox and 'y1' in bbox and 'x2' in bbox and 'y2' in bbox:
                    # Format: {x1, y1, x2, y2}
                    x1 = int(bbox['x1'])
                    y1 = int(bbox['y1'])
                    x2 = int(bbox['x2'])
                    y2 = int(bbox['y2'])
                elif isinstance(bbox, list) and len(bbox) >= 4:
                    # Format: [x1, y1, x2, y2] or [x, y, width, height]
                    if len(bbox) == 4:
                        # Assume [x, y, width, height] format
                        x1 = int(bbox[0])
                        y1 = int(bbox[1])
                        x2 = int(bbox[0] + bbox[2])
                        y2 = int(bbox[1] + bbox[3])
                    else:
                        continue
                else:
                    print(f"[CROP] Unsupported bbox format: {bbox}")
                    continue
                
                # Validate coordinates
                if x1 >= 0 and y1 >= 0 and x2 > x1 and y2 > y1:
                    relevant_bboxes.append({
                        'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2,
                        'class': class_name,
                        'confidence': detection.get('confidence', 0.0)
                    })
                    print(f"[CROP] Added {class_name} bbox: ({x1}, {y1}) to ({x2}, {y2})")
        
        if not relevant_bboxes:
            print("[CROP] No relevant bounding boxes found")
            return None
        
        # Calculate combined bounding box
        min_x1 = min(bbox['x1'] for bbox in relevant_bboxes)
        min_y1 = min(bbox['y1'] for bbox in relevant_bboxes)
        max_x2 = max(bbox['x2'] for bbox in relevant_bboxes)
        max_y2 = max(bbox['y2'] for bbox in relevant_bboxes)
        
        # Add padding
        padded_x1 = max(0, min_x1 - self.padding_pixels)
        padded_y1 = max(0, min_y1 - self.padding_pixels)
        padded_x2 = min(width, max_x2 + self.padding_pixels)
        padded_y2 = min(height, max_y2 + self.padding_pixels)
        
        combined_bbox = {
            'x1': padded_x1,
            'y1': padded_y1,
            'x2': padded_x2,
            'y2': padded_y2,
            'width': padded_x2 - padded_x1,
            'height': padded_y2 - padded_y1,
            'detections_count': len(relevant_bboxes),
            'detections': relevant_bboxes
        }
        
        print(f"[CROP] Combined bbox: ({padded_x1}, {padded_y1}) to ({padded_x2}, {padded_y2}), size: {combined_bbox['width']}x{combined_bbox['height']}")
        return combined_bbox
    
    def crop_detection_image(self, image_data: bytes, detections: List[Dict], 
                           timestamp: datetime, violation_id: str = None) -> Dict:
        """
        Crop the detection image to show only relevant areas
        
        Args:
            image_data: Raw image bytes
            detections: List of detection objects
            timestamp: Timestamp for the detection
            violation_id: Optional violation ID for naming
            
        Returns:
            Dict with cropping results and file paths
        """
        try:
            # Convert bytes to numpy array
            nparr = np.frombuffer(image_data, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if image is None:
                print("[CROP] Failed to decode image")
                return {'success': False, 'error': 'Failed to decode image'}
            
            height, width = image.shape[:2]
            print(f"[CROP] Original image size: {width}x{height}")
            
            # Calculate combined bounding box
            combined_bbox = self.calculate_combined_bbox(detections, (height, width))
            
            if not combined_bbox:
                print("[CROP] No valid detections to crop")
                return {'success': False, 'error': 'No valid detections found'}
            
            # Crop the image
            x1, y1, x2, y2 = combined_bbox['x1'], combined_bbox['y1'], combined_bbox['x2'], combined_bbox['y2']
            cropped_image = image[y1:y2, x1:x2]
            
            if cropped_image.size == 0:
                print("[CROP] Cropped image is empty")
                return {'success': False, 'error': 'Cropped image is empty'}
            
            # Generate file names
            timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S_%f")[:-3]
            base_filename = f"detection_{timestamp_str}"
            
            if violation_id:
                base_filename = f"violation_{violation_id}_{timestamp_str}"
            
            # Save full frame
            full_frame_filename = f"{base_filename}_FULL.jpg"
            full_frame_path = os.path.join("detection_frames", full_frame_filename)
            
            # Save cropped frame
            cropped_filename = f"{base_filename}_CROPPED.jpg"
            cropped_path = os.path.join(self.cropped_frames_dir, cropped_filename)
            
            # Write images
            cv2.imwrite(full_frame_path, image, [cv2.IMWRITE_JPEG_QUALITY, 90])
            cv2.imwrite(cropped_path, cropped_image, [cv2.IMWRITE_JPEG_QUALITY, 95])
            
            # Create metadata
            crop_metadata = {
                'original_size': {'width': width, 'height': height},
                'cropped_size': {'width': combined_bbox['width'], 'height': combined_bbox['height']},
                'crop_bbox': combined_bbox,
                'padding_pixels': self.padding_pixels,
                'detections_included': combined_bbox['detections'],
                'timestamp': timestamp.isoformat(),
                'violation_id': violation_id
            }
            
            # Save metadata
            metadata_filename = f"{base_filename}_METADATA.json"
            metadata_path = os.path.join(self.cropped_frames_dir, metadata_filename)
            
            with open(metadata_path, 'w') as f:
                json.dump(crop_metadata, f, indent=2)
            
            print(f"[CROP] Successfully saved:")
            print(f"[CROP]   Full frame: {full_frame_path}")
            print(f"[CROP]   Cropped: {cropped_path}")
            print(f"[CROP]   Metadata: {metadata_path}")
            
            return {
                'success': True,
                'full_frame_path': full_frame_path,
                'cropped_frame_path': cropped_path,
                'metadata_path': metadata_path,
                'crop_metadata': crop_metadata,
                'original_size': (width, height),
                'cropped_size': (combined_bbox['width'], combined_bbox['height']),
                'detections_count': combined_bbox['detections_count']
            }
            
        except Exception as e:
            print(f"[CROP] Error cropping image: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
    
    def get_cropped_image_url(self, violation_id: str, timestamp: datetime) -> Optional[str]:
        """
        Get the URL for a cropped image based on violation ID and timestamp
        
        Args:
            violation_id: Violation ID
            timestamp: Detection timestamp
            
        Returns:
            URL path to cropped image or None if not found
        """
        timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S_%f")[:-3]
        cropped_filename = f"violation_{violation_id}_{timestamp_str}_CROPPED.jpg"
        cropped_path = os.path.join(self.cropped_frames_dir, cropped_filename)
        
        if os.path.exists(cropped_path):
            # Return relative path for web serving
            return f"/api/stream/cropped-frame/{cropped_filename}"
        
        return None
    
    def cleanup_old_crops(self, days_to_keep: int = 7):
        """
        Clean up old cropped images to save disk space
        
        Args:
            days_to_keep: Number of days to keep cropped images
        """
        try:
            import time
            cutoff_time = time.time() - (days_to_keep * 24 * 60 * 60)
            
            for filename in os.listdir(self.cropped_frames_dir):
                file_path = os.path.join(self.cropped_frames_dir, filename)
                if os.path.isfile(file_path):
                    file_time = os.path.getmtime(file_path)
                    if file_time < cutoff_time:
                        os.remove(file_path)
                        print(f"[CROP] Cleaned up old file: {filename}")
                        
        except Exception as e:
            print(f"[CROP] Error during cleanup: {e}")

# Global cropper instance
image_cropper = DetectionImageCropper(padding_pixels=100)