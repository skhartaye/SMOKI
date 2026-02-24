"""
Camera streaming module - serves HLS stream
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from collections import deque
import threading
import time
import os
from pathlib import Path

router = APIRouter(prefix="/api/stream", tags=["stream"])

class StreamManager:
    def __init__(self):
        self.latest_frame = None
        self.frame_buffer = deque(maxlen=60)  # Increased from 30 to 60 frames
        self.lock = threading.Lock()
        self.fps = 0
        self.frame_count = 0
        self.last_time = time.time()
    
    def add_frame(self, frame_data: bytes):
        """Store latest frame"""
        try:
            with self.lock:
                self.latest_frame = frame_data
                self.frame_buffer.append(frame_data)
                self.frame_count += 1
                
                # Calculate FPS
                current_time = time.time()
                if current_time - self.last_time >= 1.0:
                    self.fps = self.frame_count
                    self.frame_count = 0
                    self.last_time = current_time
            return True
        except Exception as e:
            print(f"Error adding frame: {e}")
            return False
    
    def get_latest_frame(self):
        """Get latest frame"""
        with self.lock:
            return self.latest_frame
    
    def get_mjpeg_stream(self):
        """Generate MJPEG stream at 60 FPS"""
        last_frame = None
        while True:
            frame = self.get_latest_frame()
            if frame and frame != last_frame:  # Only send if frame changed
                last_frame = frame
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Content-Length: ' + str(len(frame)).encode() + b'\r\n\r\n' + frame + b'\r\n')
            time.sleep(0.0167)  # ~60 FPS (1/60 = 0.0167)

# Global stream manager
stream_manager = StreamManager()

# ============ ENDPOINTS ============

@router.post("/frame")
async def receive_frame(frame: UploadFile = File(...)):
    """Receive frame from RPi camera"""
    try:
        frame_data = await frame.read()
        print(f"Received frame: {len(frame_data)} bytes")
        
        if stream_manager.add_frame(frame_data):
            return {
                "success": True,
                "fps": stream_manager.fps,
                "buffered_frames": len(stream_manager.frame_buffer)
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to process frame")
    except Exception as e:
        print(f"Frame receive error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stream.mjpeg")
async def get_mjpeg_stream():
    """Get MJPEG stream"""
    response = StreamingResponse(
        stream_manager.get_mjpeg_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Connection"] = "keep-alive"
    return response

@router.get("/latest.jpg")
async def get_latest_frame():
    """Get latest frame as JPEG"""
    frame = stream_manager.get_latest_frame()
    if not frame:
        raise HTTPException(status_code=503, detail="No frame available")
    
    return StreamingResponse(
        iter([frame]),
        media_type="image/jpeg"
    )

@router.get("/status")
async def get_stream_status():
    """Get stream status"""
    return {
        "status": "active" if stream_manager.latest_frame else "idle",
        "fps": stream_manager.fps,
        "buffered_frames": len(stream_manager.frame_buffer),
        "latest_frame_size": len(stream_manager.latest_frame) if stream_manager.latest_frame else 0
    }

@router.get("/debug")
async def debug_stream():
    """Debug endpoint to check stream state"""
    return {
        "has_frames": stream_manager.latest_frame is not None,
        "frame_size": len(stream_manager.latest_frame) if stream_manager.latest_frame else 0,
        "buffer_size": len(stream_manager.frame_buffer),
        "fps": stream_manager.fps,
        "endpoints": {
            "latest_frame": "/api/stream/latest.jpg",
            "mjpeg_stream": "/api/stream/stream.mjpeg",
            "status": "/api/stream/status"
        }
    }
