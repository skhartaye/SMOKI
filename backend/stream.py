"""
HLS Streaming module for RPi camera feed
Handles frame reception and HLS segment generation
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
import cv2
import numpy as np
from collections import deque
from datetime import datetime
import threading
import time
import os
from pathlib import Path

router = APIRouter(prefix="/api/stream", tags=["stream"])

# HLS Configuration
HLS_SEGMENT_DURATION = 2  # seconds
HLS_SEGMENTS_COUNT = 3  # number of segments to keep
FRAME_BUFFER_SIZE = 60  # frames to buffer

class HLSStreamManager:
    def __init__(self):
        self.frame_buffer = deque(maxlen=FRAME_BUFFER_SIZE)
        self.segments = deque(maxlen=HLS_SEGMENTS_COUNT)
        self.segment_index = 0
        self.lock = threading.Lock()
        self.last_frame_time = time.time()
        self.fps = 0
        self.frame_count = 0
        
        # Create temp directory for segments
        self.temp_dir = Path("./temp_hls")
        self.temp_dir.mkdir(exist_ok=True)
    
    def add_frame(self, frame_data: bytes):
        """Add frame to buffer"""
        try:
            # Decode frame
            nparr = np.frombuffer(frame_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is None:
                return False
            
            with self.lock:
                self.frame_buffer.append(frame)
                self.frame_count += 1
                
                # Calculate FPS
                current_time = time.time()
                if current_time - self.last_frame_time >= 1.0:
                    self.fps = self.frame_count
                    self.frame_count = 0
                    self.last_frame_time = current_time
            
            return True
        except Exception as e:
            print(f"Error adding frame: {e}")
            return False
    
    def generate_segment(self):
        """Generate HLS segment from buffered frames"""
        try:
            with self.lock:
                if len(self.frame_buffer) == 0:
                    return None
                
                # Get frames for this segment
                frames_needed = max(1, int(self.fps * HLS_SEGMENT_DURATION / 10))
                segment_frames = list(self.frame_buffer)[-frames_needed:]
            
            if not segment_frames:
                return None
            
            # Create video segment
            segment_path = self.temp_dir / f"segment_{self.segment_index}.ts"
            
            # Use first frame dimensions
            height, width = segment_frames[0].shape[:2]
            
            # Create video writer
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(
                str(segment_path),
                fourcc,
                max(self.fps, 15),  # Ensure minimum FPS
                (width, height)
            )
            
            # Write frames
            for frame in segment_frames:
                out.write(frame)
            
            out.release()
            
            # Store segment info
            with self.lock:
                self.segments.append({
                    'index': self.segment_index,
                    'path': segment_path,
                    'duration': HLS_SEGMENT_DURATION
                })
                self.segment_index += 1
            
            return segment_path
        except Exception as e:
            print(f"Error generating segment: {e}")
            return None
    
    def get_playlist(self):
        """Generate M3U8 playlist"""
        try:
            with self.lock:
                if not self.segments:
                    return None
                
                playlist = "#EXTM3U\n"
                playlist += "#EXT-X-VERSION:3\n"
                playlist += f"#EXT-X-TARGETDURATION:{HLS_SEGMENT_DURATION}\n"
                playlist += "#EXT-X-MEDIA-SEQUENCE:0\n"
                
                for segment in self.segments:
                    playlist += f"#EXTINF:{segment['duration']},\n"
                    playlist += f"segment_{segment['index']}.ts\n"
                
                playlist += "#EXT-X-ENDLIST\n"
                
                return playlist
        except Exception as e:
            print(f"Error generating playlist: {e}")
            return None
    
    def cleanup(self):
        """Clean up old segments"""
        try:
            for file in self.temp_dir.glob("segment_*.ts"):
                try:
                    file.unlink()
                except:
                    pass
        except Exception as e:
            print(f"Error cleaning up: {e}")

# Global stream manager
stream_manager = HLSStreamManager()

# Background thread to generate segments
def segment_generator():
    """Background thread to continuously generate segments"""
    while True:
        try:
            stream_manager.generate_segment()
            time.sleep(HLS_SEGMENT_DURATION)
        except Exception as e:
            print(f"Error in segment generator: {e}")
            time.sleep(1)

# Start segment generator thread
segment_thread = threading.Thread(target=segment_generator, daemon=True)
segment_thread.start()

# ============ ENDPOINTS ============

@router.post("/frame")
async def receive_frame(frame: UploadFile = File(...)):
    """
    Receive frame from RPi camera
    """
    try:
        frame_data = await frame.read()
        
        if stream_manager.add_frame(frame_data):
            return {
                "success": True,
                "fps": stream_manager.fps,
                "buffered_frames": len(stream_manager.frame_buffer)
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to process frame")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/playlist.m3u8")
async def get_playlist():
    """
    Get HLS playlist
    """
    try:
        playlist = stream_manager.get_playlist()
        
        if not playlist:
            raise HTTPException(status_code=503, detail="Stream not ready")
        
        return StreamingResponse(
            iter([playlist]),
            media_type="application/vnd.apple.mpegurl"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/segment_{segment_id}.ts")
async def get_segment(segment_id: int):
    """
    Get HLS segment
    """
    try:
        segment_path = stream_manager.temp_dir / f"segment_{segment_id}.ts"
        
        if not segment_path.exists():
            raise HTTPException(status_code=404, detail="Segment not found")
        
        return FileResponse(
            segment_path,
            media_type="video/mp2t"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def get_stream_status():
    """
    Get stream status
    """
    return {
        "status": "active" if len(stream_manager.frame_buffer) > 0 else "idle",
        "fps": stream_manager.fps,
        "buffered_frames": len(stream_manager.frame_buffer),
        "segments": len(stream_manager.segments),
        "segment_duration": HLS_SEGMENT_DURATION
    }
