"""
RPi5 Simple Face Detection and Blur with HLS Server
Captures from picamera2, detects faces with YOLOv8, blurs them, and streams via HLS
"""

import cv2
import numpy as np
from ultralytics import YOLO
from picamera2 import Picamera2
import time
import subprocess
import os
import shutil
import threading
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

# Configuration
BLUR_STRENGTH = 25
CONF_THRESHOLD = 0.5
HLS_DIR = '/dev/shm/hls'
OUTPUT_WIDTH = 640
OUTPUT_HEIGHT = 480
FPS = 15
HTTP_PORT = 8000

# Clean up and prepare HLS directory
if os.path.exists(HLS_DIR):
    shutil.rmtree(HLS_DIR)
os.makedirs(HLS_DIR, exist_ok=True)

# Load YOLOv8 model
print("Loading YOLOv8n model...")
model = YOLO('yolov8n.pt')
print("✓ Model loaded\n")

# ─── HLS HTTP SERVER ───────────────────────────────────────────────────────
class HLSHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=HLS_DIR, **kwargs)
    
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        super().end_headers()
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()
    
    def log_message(self, format, *args):
        pass  # Suppress logging

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True

def start_http_server():
    """Start HTTP server for HLS streaming"""
    server = ThreadedHTTPServer(('0.0.0.0', HTTP_PORT), HLSHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server

def start_ffmpeg(w, h, fps=15):
    """Start FFmpeg for HLS streaming"""
    cmd = ['ffmpeg', '-y',
        '-f', 'rawvideo', '-vcodec', 'rawvideo',
        '-pix_fmt', 'bgr24', '-s', f'{w}x{h}', '-r', str(fps),
        '-i', '-', '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
        '-b:v', '800k',
        '-g', str(fps * 2),
        '-hls_time', '2', '-hls_list_size', '3', '-hls_flags', 'delete_segments',
        os.path.join(HLS_DIR, 'stream.m3u8')
    ]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)

def blur_faces(frame, faces):
    """Blur detected faces in frame"""
    for (x1, y1, x2, y2) in faces:
        # Extract face region
        face_roi = frame[y1:y2, x1:x2]
        
        # Apply Gaussian blur
        blurred_face = cv2.GaussianBlur(face_roi, (BLUR_STRENGTH, BLUR_STRENGTH), 0)
        
        # Replace face region with blurred version
        frame[y1:y2, x1:x2] = blurred_face
    
    return frame

def detect_faces(frame):
    """Detect faces using YOLOv8"""
    results = model(frame, conf=CONF_THRESHOLD, verbose=False)
    faces = []
    
    if results[0].boxes is not None:
        for box in results[0].boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = float(box.conf[0])
            faces.append((x1, y1, x2, y2, conf))
    
    return faces

def main():
    """Main function - capture, detect, blur, stream"""
    print("Starting HTTP server...")
    http_server = start_http_server()
    print(f"✓ HTTP server started on port {HTTP_PORT}")
    
    print("Starting picamera2...")
    picam2 = Picamera2()
    config = picam2.create_video_configuration(main={"format": "BGR888", "size": (OUTPUT_WIDTH, OUTPUT_HEIGHT)})
    picam2.configure(config)
    picam2.start()
    
    print("✓ Camera started")
    print("Starting FFmpeg for HLS streaming...")
    ffmpeg_proc = start_ffmpeg(OUTPUT_WIDTH, OUTPUT_HEIGHT, fps=FPS)
    print("✓ FFmpeg started")
    
    # Get local IP
    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    
    print(f"\n✓ Stream available at:")
    print(f"  - http://localhost:{HTTP_PORT}/stream.m3u8")
    print(f"  - http://{local_ip}:{HTTP_PORT}/stream.m3u8")
    print(f"\nUse VLC or any HLS player to view the stream\n")
    
    frame_count = 0
    start_time = time.time()
    
    try:
        while True:
            # Capture frame
            frame = picam2.capture_array()
            frame_count += 1
            
            # Detect faces
            faces = detect_faces(frame)
            
            # Blur faces
            if len(faces) > 0:
                frame = blur_faces(frame, [(x1, y1, x2, y2) for x1, y1, x2, y2, _ in faces])
                
                # Draw bounding boxes
                for (x1, y1, x2, y2, conf) in faces:
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(frame, f'{conf:.2f}', (x1, y1-10), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
            # Calculate FPS
            elapsed = time.time() - start_time
            fps = frame_count / elapsed if elapsed > 0 else 0
            
            # Display info on frame
            cv2.putText(frame, f'FPS: {fps:.1f} | Faces: {len(faces)}', (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # Send to FFmpeg
            try:
                ffmpeg_proc.stdin.write(frame.tobytes())
            except BrokenPipeError:
                print("FFmpeg pipe broken, restarting...")
                ffmpeg_proc = start_ffmpeg(OUTPUT_WIDTH, OUTPUT_HEIGHT, fps=FPS)
            
            # Print stats every 30 frames
            if frame_count % 30 == 0:
                print(f"Frame: {frame_count} | FPS: {fps:.1f} | Faces: {len(faces)}")
    
    except KeyboardInterrupt:
        print("\n✓ Interrupted by user")
    
    finally:
        print("Cleaning up...")
        try:
            ffmpeg_proc.terminate()
        except:
            pass
        try:
            http_server.shutdown()
        except:
            pass
        picam2.stop()
        print("✓ Done")

if __name__ == '__main__':
    main()
