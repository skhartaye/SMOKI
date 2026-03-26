"""
Download YOLOv8n Model for Face Detection
Saves model to esp32 directory for easy access
"""

from ultralytics import YOLO
from pathlib import Path
import os

def download_yolov8_face():
    """Download YOLOv8n model and save to project directory"""
    print("Downloading YOLOv8n model for face detection...")
    print("This may take a few minutes depending on your internet speed.\n")
    
    try:
        # Create models directory in esp32 folder
        models_dir = Path(__file__).parent / "models"
        models_dir.mkdir(exist_ok=True)
        
        print(f"Saving to: {models_dir}\n")
        
        # Load YOLOv8n model (nano - smallest and fastest)
        # This will download and cache the model
        model = YOLO('yolov8n.pt')
        
        # Get the cached model path
        model_path = model.model_name
        print(f"Model downloaded from cache: {model_path}")
        
        # Copy to our models directory
        import shutil
        dest_path = models_dir / "yolov8n.pt"
        
        # Try to find and copy the model
        try:
            # Check common cache locations
            cache_locations = [
                Path.home() / ".cache" / "ultralytics" / "yolov8n.pt",
                Path.home() / "AppData" / "Local" / "ultralytics" / "yolov8n.pt",
                Path("yolov8n.pt"),
            ]
            
            found = False
            for cache_path in cache_locations:
                if cache_path.exists():
                    print(f"Found model at: {cache_path}")
                    shutil.copy(cache_path, dest_path)
                    found = True
                    break
            
            if not found:
                print("Model cached by Ultralytics, will be auto-loaded on first use")
                print(f"Model will be used from: {model_path}")
        except Exception as e:
            print(f"Note: Could not copy to project directory: {e}")
            print("Model will be loaded from Ultralytics cache on first use")
        
        print("\n✓ YOLOv8n model is ready!")
        print(f"Model size: ~6.2 MB")
        print(f"Model type: Object Detection (includes face detection)")
        
        return True
    
    except Exception as e:
        print(f"\n✗ Error downloading model: {e}")
        return False

if __name__ == '__main__':
    success = download_yolov8_face()
    if success:
        print("\n✓ Ready to use! You can now run:")
        print("  - python yolov8_face_blur.py")
        print("  - python rpi5_camera_stream_yolov8_face.py")
    else:
        print("\n✗ Download failed. Please check your internet connection and try again.")
