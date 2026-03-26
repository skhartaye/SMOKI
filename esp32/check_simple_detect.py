#!/usr/bin/env python3
"""
Simple detection system health check
Tests camera, models, and backend connectivity
"""

import os
import sys
import time
import requests
from datetime import datetime

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv('.env.rpi')
except ImportError:
    print("⚠️  dotenv not available, using system environment")

def check_environment():
    """Check environment variables"""
    print("🔧 Environment Configuration:")
    
    api_url = os.getenv('API_URL', 'https://smoki-backend-rpi.onrender.com')
    device_id = os.getenv('DEVICE_ID', 'rpi_camera_01')
    location = os.getenv('CAMERA_LOCATION', 'Main_Entrance')
    
    print(f"   Backend URL: {api_url}")
    print(f"   Device ID: {device_id}")
    print(f"   Location: {location}")
    
    return api_url, device_id, location

def check_backend(api_url):
    """Test backend connectivity"""
    print("\n🌐 Backend Connectivity:")
    
    try:
        print(f"   Testing: {api_url}/api/health")
        response = requests.get(f"{api_url}/api/health", timeout=10)
        
        if response.status_code == 200:
            print("   ✅ Backend is online")
            data = response.json()
            print(f"   Status: {data.get('status', 'unknown')}")
            print(f"   Database: {data.get('database', 'unknown')}")
            return True
        else:
            print(f"   ❌ Backend returned HTTP {response.status_code}")
            return False
            
    except requests.exceptions.Timeout:
        print("   ❌ Backend timeout (>10s)")
        return False
    except requests.exceptions.ConnectionError:
        print("   ❌ Cannot connect to backend")
        return False
    except Exception as e:
        print(f"   ❌ Backend error: {e}")
        return False

def check_camera():
    """Test camera availability"""
    print("\n📷 Camera Check:")
    
    try:
        from picamera2 import Picamera2
        print("   ✅ Picamera2 library available")
        
        # Try to initialize camera
        picam2 = Picamera2()
        print("   ✅ Camera device detected")
        
        # Test configuration
        config = picam2.create_video_configuration(main={"format": "BGR888", "size": (640, 640)})
        picam2.configure(config)
        print("   ✅ Camera configuration successful")
        
        picam2.close()
        print("   ✅ Camera test complete")
        return True
        
    except ImportError:
        print("   ❌ Picamera2 not installed")
        return False
    except Exception as e:
        print(f"   ❌ Camera error: {e}")
        return False

def check_hailo():
    """Test Hailo platform"""
    print("\n🤖 Hailo AI Platform:")
    
    try:
        import hailo_platform as hp
        print("   ✅ Hailo platform library available")
        
        # Check model files
        models = [
            "/home/sevi/smoki_project/src/model-skhart-ready/smoke-hailo8l.hef",
            "/home/sevi/smoki_project/src/model-skhart-ready/license-plate-opt-hailo8l.hef", 
            "/home/sevi/smoki_project/src/model-skhart-ready/vehicle-class-hailo8l.hef"
        ]
        
        for model_path in models:
            if os.path.exists(model_path):
                print(f"   ✅ Found: {os.path.basename(model_path)}")
            else:
                print(f"   ❌ Missing: {os.path.basename(model_path)}")
        
        # Test VDevice creation
        try:
            with hp.VDevice() as target:
                print("   ✅ Hailo VDevice creation successful")
            return True
        except Exception as e:
            print(f"   ❌ VDevice error: {e}")
            return False
            
    except ImportError:
        print("   ❌ Hailo platform not installed")
        return False
    except Exception as e:
        print(f"   ❌ Hailo error: {e}")
        return False

def check_dependencies():
    """Check Python dependencies"""
    print("\n📦 Python Dependencies:")
    
    deps = [
        ('cv2', 'OpenCV'),
        ('numpy', 'NumPy'),
        ('requests', 'Requests'),
        ('picamera2', 'Picamera2'),
        ('hailo_platform', 'Hailo Platform')
    ]
    
    all_good = True
    for module, name in deps:
        try:
            __import__(module)
            print(f"   ✅ {name}")
        except ImportError:
            print(f"   ❌ {name} - not installed")
            all_good = False
    
    return all_good

def main():
    print("🔍 RPi Simple Detection - System Health Check")
    print("=" * 50)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Run all checks
    api_url, device_id, location = check_environment()
    deps_ok = check_dependencies()
    camera_ok = check_camera()
    hailo_ok = check_hailo()
    backend_ok = check_backend(api_url)
    
    # Summary
    print("\n📊 System Status Summary:")
    print(f"   Dependencies: {'✅' if deps_ok else '❌'}")
    print(f"   Camera: {'✅' if camera_ok else '❌'}")
    print(f"   Hailo AI: {'✅' if hailo_ok else '❌'}")
    print(f"   Backend: {'✅' if backend_ok else '❌'}")
    
    if all([deps_ok, camera_ok, hailo_ok, backend_ok]):
        print("\n🎉 All systems ready! You can run rpi_simple_detect.py")
        return 0
    else:
        print("\n⚠️  Some issues detected. Please fix before running detection.")
        return 1

if __name__ == '__main__':
    sys.exit(main())