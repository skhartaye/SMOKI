#!/bin/bash
# Deploy Simple Detection System
# Usage: ./deploy_simple_detect.sh

echo "🚀 Deploying Simple Detection System"
echo "===================================="

# Check if we're on the RPi
if [ ! -f "/proc/device-tree/model" ] || ! grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
    echo "❌ This script should be run on a Raspberry Pi"
    exit 1
fi

# Check if we're in the right directory
if [ ! -f "rpi_simple_detect.py" ]; then
    echo "❌ Error: rpi_simple_detect.py not found"
    echo "Please run this script from the esp32/ directory"
    exit 1
fi

# Check if .env.rpi exists
if [ ! -f ".env.rpi" ]; then
    echo "❌ Error: .env.rpi not found"
    echo "Creating template .env.rpi file..."
    cat > .env.rpi << EOF
# RPi Simple Detection Configuration
API_URL=https://smoki-backend-rpi.onrender.com
DEVICE_ID=cam_001
CAMERA_LOCATION=Main_Entrance
EOF
    echo "✅ Created .env.rpi template"
    echo "Please edit .env.rpi with your configuration and run this script again"
    exit 1
fi

# Load environment variables
source .env.rpi

echo "📍 Location: $CAMERA_LOCATION"
echo "🔗 Backend: $API_URL"
echo "📷 Camera ID: $DEVICE_ID"
echo ""

# Check dependencies
echo "🔍 Checking dependencies..."

# Check Python packages
python3 -c "import hailo_platform" 2>/dev/null || {
    echo "❌ hailo_platform not found"
    echo "Please install Hailo platform SDK"
    exit 1
}

python3 -c "import cv2" 2>/dev/null || {
    echo "❌ OpenCV not found"
    echo "Install with: pip3 install opencv-python"
    exit 1
}

python3 -c "import numpy" 2>/dev/null || {
    echo "❌ NumPy not found"
    echo "Install with: pip3 install numpy"
    exit 1
}

python3 -c "import requests" 2>/dev/null || {
    echo "❌ Requests not found"
    echo "Install with: pip3 install requests"
    exit 1
}

python3 -c "from picamera2 import Picamera2" 2>/dev/null || {
    echo "❌ Picamera2 not found"
    echo "Install with: pip3 install picamera2"
    exit 1
}

echo "✅ All dependencies found"

# Check model files
echo "🤖 Checking AI models..."

MODELS=(
    "/home/sevi/smoki_project/src/model-skhart-ready/smoke-hailo8l.hef"
    "/home/sevi/smoki_project/src/model-skhart-ready/license-plate-opt-hailo8l.hef"
    "/home/sevi/smoki_project/src/model-skhart-ready/vehicle-class-hailo8l.hef"
)

for model in "${MODELS[@]}"; do
    if [ -f "$model" ]; then
        echo "✅ Found: $(basename $model)"
    else
        echo "❌ Missing: $model"
        exit 1
    fi
done

# Test backend connectivity
echo "🌐 Testing backend connectivity..."
if curl -s --max-time 10 "$API_URL/api/health" > /dev/null; then
    echo "✅ Backend is reachable"
else
    echo "⚠️  Backend connectivity issue - will retry during runtime"
fi

# Check camera
echo "📷 Testing camera..."
if python3 -c "
from picamera2 import Picamera2
try:
    picam2 = Picamera2()
    picam2.close()
    print('✅ Camera test passed')
except Exception as e:
    print(f'❌ Camera test failed: {e}')
    exit(1)
"; then
    echo "Camera is ready"
else
    echo "❌ Camera test failed"
    exit 1
fi

echo ""
echo "🎉 All checks passed! System is ready to deploy."
echo ""
echo "🚀 Starting Simple Detection System..."
echo "Press Ctrl+C to stop"
echo ""

# Run the detection system
python3 rpi_simple_detect.py