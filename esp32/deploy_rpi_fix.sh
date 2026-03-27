#!/bin/bash

# Deploy updated rpi_simple_detect.py to RPi and restart
# Usage: ./deploy_rpi_fix.sh [rpi_ip]

RPI_IP=${1:-"192.168.100.199"}  # Default IP, can be overridden
RPI_USER="sevi"
RPI_PATH="/home/sevi/smoki_project/src/model-skhart-ready"
LOCAL_FILE="esp32/rpi_simple_detect.py"

echo "🚀 Deploying RPi Detection Fix"
echo "================================"
echo "RPi IP: $RPI_IP"
echo "Local file: $LOCAL_FILE"
echo "Remote path: $RPI_PATH"
echo ""

# Check if local file exists
if [ ! -f "$LOCAL_FILE" ]; then
    echo "❌ Error: Local file $LOCAL_FILE not found"
    exit 1
fi

echo "📋 Step 1: Copying updated script to RPi..."
scp "$LOCAL_FILE" "$RPI_USER@$RPI_IP:$RPI_PATH/"

if [ $? -eq 0 ]; then
    echo "✅ File copied successfully"
else
    echo "❌ Failed to copy file"
    exit 1
fi

echo ""
echo "📋 Step 2: Testing script syntax on RPi..."
ssh "$RPI_USER@$RPI_IP" "cd $RPI_PATH && python3 -m py_compile rpi_simple_detect.py"

if [ $? -eq 0 ]; then
    echo "✅ Script syntax is valid"
else
    echo "❌ Script has syntax errors"
    exit 1
fi

echo ""
echo "📋 Step 3: Checking if script is currently running..."
RUNNING_PID=$(ssh "$RPI_USER@$RPI_IP" "pgrep -f rpi_simple_detect.py")

if [ ! -z "$RUNNING_PID" ]; then
    echo "🔄 Found running script (PID: $RUNNING_PID), stopping it..."
    ssh "$RPI_USER@$RPI_IP" "pkill -f rpi_simple_detect.py"
    sleep 2
    echo "✅ Previous script stopped"
else
    echo "ℹ️  No running script found"
fi

echo ""
echo "📋 Step 4: Starting updated script..."
echo "Command: cd $RPI_PATH && source /home/sevi/smoki_project/skhart_fucksyou/bin/activate && python rpi_simple_detect.py --interval 3"
echo ""

# Start the script in the background and show initial output
ssh "$RPI_USER@$RPI_IP" "cd $RPI_PATH && source /home/sevi/smoki_project/skhart_fucksyou/bin/activate && nohup python rpi_simple_detect.py --interval 3 > rpi_detect.log 2>&1 &"

sleep 3

echo "📋 Step 5: Checking if script started successfully..."
NEW_PID=$(ssh "$RPI_USER@$RPI_IP" "pgrep -f rpi_simple_detect.py")

if [ ! -z "$NEW_PID" ]; then
    echo "✅ Script started successfully (PID: $NEW_PID)"
    echo ""
    echo "📋 Step 6: Showing initial log output..."
    ssh "$RPI_USER@$RPI_IP" "cd $RPI_PATH && tail -20 rpi_detect.log"
    echo ""
    echo "🎯 Deployment Complete!"
    echo "================================"
    echo "✅ Updated script deployed and running"
    echo "✅ Database initialization should now work"
    echo "✅ Detection data will flow to backend"
    echo ""
    echo "📊 Monitor logs: ssh $RPI_USER@$RPI_IP 'cd $RPI_PATH && tail -f rpi_detect.log'"
    echo "🔍 Check backend: curl https://smoki-backend-rpi.onrender.com/api/stream/status"
else
    echo "❌ Failed to start script"
    echo "📋 Checking error logs..."
    ssh "$RPI_USER@$RPI_IP" "cd $RPI_PATH && tail -10 rpi_detect.log"
    exit 1
fi