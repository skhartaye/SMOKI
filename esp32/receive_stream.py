import cv2
import requests
import numpy as np
from urllib.parse import urljoin
import time

# Configuration
STREAM_IP = "192.168.100.199"
STREAM_PORT = 8000
STREAM_URL = f"http://{STREAM_IP}:{STREAM_PORT}/stream.m3u8"

def receive_stream():
    """Receive and display HLS stream from RPi"""
    print(f"Connecting to stream at {STREAM_URL}...")
    
    # Use OpenCV to open the HLS stream
    cap = cv2.VideoCapture(STREAM_URL)
    
    if not cap.isOpened():
        print(f"Failed to open stream at {STREAM_URL}")
        return
    
    print("Stream connected. Press 'q' to quit.")
    
    frame_count = 0
    start_time = time.time()
    
    while True:
        ret, frame = cap.read()
        
        if not ret:
            print("Failed to read frame from stream")
            break
        
        frame_count += 1
        
        # Display FPS
        elapsed = time.time() - start_time
        if elapsed > 0:
            fps = frame_count / elapsed
            cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # Display the frame
        cv2.imshow(f"Stream from {STREAM_IP}", frame)
        
        # Press 'q' to quit
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    cap.release()
    cv2.destroyAllWindows()
    print(f"Stream closed. Received {frame_count} frames.")

if __name__ == "__main__":
    receive_stream()
