#!/bin/bash

# RPi Stream Runner Script
# This script sets up the environment and runs the camera stream

# Set environment variables
export BACKEND_URL=https://smoki-backend-rpi.onrender.com
export CAMERA_ID=rpi_camera_01
export CAMERA_LOCATION=Main_Entrance
export HEF_PATH=/home/sevi/smoki_project/src/model-skhart-ready/smoke-seg-v3.hef

# Optional: Load additional variables from .env.rpi if it exists
if [ -f "esp32/.env.rpi" ]; then
    echo "Loading environment variables from .env.rpi..."
    source esp32/.env.rpi
fi

echo "Starting RPi camera stream..."
echo "Backend URL: $BACKEND_URL"
echo "Camera ID: $CAMERA_ID"
echo "Location: $CAMERA_LOCATION"

# Run the Python script
/home/sevi/smoki_project/skhart_fucksyou/bin/python /home/sevi/smoki_project/src/model-skhart-ready/rpi_stream.py