#!/bin/bash
# Simple detection runner script
# Usage: ./run_simple_detect.sh

echo "🎥 Starting RPi Simple Detection System"
echo "========================================"

# Check if we're in the right directory
if [ ! -f "rpi_simple_detect.py" ]; then
    echo "❌ Error: rpi_simple_detect.py not found in current directory"
    echo "Please run this script from the esp32/ directory"
    exit 1
fi

# Check if .env.rpi exists
if [ ! -f ".env.rpi" ]; then
    echo "❌ Error: .env.rpi not found"
    echo "Please create .env.rpi with your configuration"
    exit 1
fi

# Load environment variables
source .env.rpi

echo "📍 Location: $CAMERA_LOCATION"
echo "🔗 Backend: $API_URL"
echo "📷 Camera ID: $DEVICE_ID"
echo ""

# Run the detection script
python3 rpi_simple_detect.py