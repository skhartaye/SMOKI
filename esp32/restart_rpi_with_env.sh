#!/bin/bash
# Restart RPi detection script with proper environment variables loaded
# Usage: ./restart_rpi_with_env.sh

echo "🔄 Restarting RPi detection script with proper environment..."

# Kill existing processes
echo "🛑 Stopping existing detection scripts..."
pkill -f "rpi_simple_detect.py" || echo "No rpi_simple_detect.py process found"
pkill -f "rpi_stream.py" || echo "No rpi_stream.py process found"

# Wait a moment for cleanup
sleep 2

# Load environment variables from .env.rpi
ENV_FILE="/home/sevi/smoki_project/src/model-skhart-ready/.env.rpi"
if [ -f "$ENV_FILE" ]; then
    echo "📋 Loading environment from $ENV_FILE"
    export $(grep -v '^#' "$ENV_FILE" | xargs)
    echo "✅ Environment variables loaded:"
    echo "   API_URL=$API_URL"
    echo "   DEVICE_ID=$DEVICE_ID"
    echo "   SEND_DETECTIONS=$SEND_DETECTIONS"
else
    echo "⚠️  Environment file not found at $ENV_FILE"
    echo "Using default values..."
    export API_URL="https://smoki-backend-rpi.onrender.com"
    export DEVICE_ID="cam_001"
    export SEND_DETECTIONS="true"
fi

# Activate virtual environment
VENV_PATH="/home/sevi/smoki_project/skhart_fucksyou"
if [ -d "$VENV_PATH" ]; then
    echo "🐍 Activating virtual environment..."
    source "$VENV_PATH/bin/activate"
else
    echo "⚠️  Virtual environment not found at $VENV_PATH"
fi

# Choose which script to run (prefer rpi_simple_detect.py)
SIMPLE_SCRIPT="/home/sevi/smoki_project/src/model-skhart-ready/rpi_simple_detect.py"
STREAM_SCRIPT="/home/sevi/smoki_project/src/model-skhart-ready/rpi_stream.py"

if [ -f "$SIMPLE_SCRIPT" ]; then
    SCRIPT_PATH="$SIMPLE_SCRIPT"
    SCRIPT_ARGS="--interval 3"
    echo "🚀 Using rpi_simple_detect.py (recommended)"
elif [ -f "$STREAM_SCRIPT" ]; then
    SCRIPT_PATH="$STREAM_SCRIPT"
    SCRIPT_ARGS=""
    echo "🚀 Using rpi_stream.py (fallback)"
else
    echo "❌ No detection script found!"
    exit 1
fi

echo "Command: python $SCRIPT_PATH $SCRIPT_ARGS"

# Run in background and show PID
nohup python "$SCRIPT_PATH" $SCRIPT_ARGS > /tmp/rpi_detect.log 2>&1 &
PID=$!

echo "✅ Detection script started with PID: $PID"
echo "📋 Process info:"
ps aux | grep "$PID" | grep -v grep

echo ""
echo "📊 Monitor logs with: tail -f /tmp/rpi_detect.log"
echo "🔍 Check process: ps aux | grep rpi_"
echo "🛑 Stop process: kill $PID"
echo ""
echo "🌐 Test backend connection:"
echo "curl -X GET $API_URL/api/stream/status"