# Deploy updated rpi_simple_detect.py to RPi and restart
# Usage: .\deploy_rpi_fix.ps1 [rpi_ip]

param(
    [string]$RpiIP = "192.168.100.199"  # Default IP, can be overridden
)

$RpiUser = "sevi"
$RpiPath = "/home/sevi/smoki_project/src/model-skhart-ready"
$LocalFile = "esp32/rpi_simple_detect.py"

Write-Host "🚀 Deploying RPi Detection Fix (Face Detection Removed)" -ForegroundColor Green
Write-Host "======================================================="
Write-Host "RPi IP: $RpiIP"
Write-Host "Local file: $LocalFile"
Write-Host "Remote path: $RpiPath"
Write-Host ""

# Check if local file exists
if (-not (Test-Path $LocalFile)) {
    Write-Host "❌ Error: Local file $LocalFile not found" -ForegroundColor Red
    exit 1
}

Write-Host "📋 Step 1: Copying updated script to RPi..." -ForegroundColor Yellow
& scp $LocalFile "${RpiUser}@${RpiIP}:${RpiPath}/"

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ File copied successfully" -ForegroundColor Green
} else {
    Write-Host "❌ Failed to copy file" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "📋 Step 2: Testing script syntax on RPi..." -ForegroundColor Yellow
& ssh "${RpiUser}@${RpiIP}" "cd $RpiPath; python3 -m py_compile rpi_simple_detect.py"

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Script syntax is valid" -ForegroundColor Green
} else {
    Write-Host "❌ Script has syntax errors" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "📋 Step 3: Checking if script is currently running..." -ForegroundColor Yellow
$RunningPid = & ssh "${RpiUser}@${RpiIP}" "pgrep -f rpi_simple_detect.py"

if ($RunningPid) {
    Write-Host "🔄 Found running script (PID: $RunningPid), stopping it..." -ForegroundColor Yellow
    & ssh "${RpiUser}@${RpiIP}" "pkill -f rpi_simple_detect.py"
    Start-Sleep -Seconds 2
    Write-Host "✅ Previous script stopped" -ForegroundColor Green
} else {
    Write-Host "ℹ️  No running script found" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "📋 Step 4: Starting updated script..." -ForegroundColor Yellow
Write-Host "Command: cd $RpiPath; source venv; python rpi_simple_detect.py --interval 3"
Write-Host ""

# Start the script in the background (escape the & properly)
$Command = "cd $RpiPath; source /home/sevi/smoki_project/skhart_fucksyou/bin/activate; nohup python rpi_simple_detect.py --interval 3 > rpi_detect.log 2>&1 '&'"
& ssh "${RpiUser}@${RpiIP}" $Command

Start-Sleep -Seconds 3

Write-Host "📋 Step 5: Checking if script started successfully..." -ForegroundColor Yellow
$NewPid = & ssh "${RpiUser}@${RpiIP}" "pgrep -f rpi_simple_detect.py"

if ($NewPid) {
    Write-Host "✅ Script started successfully (PID: $NewPid)" -ForegroundColor Green
    Write-Host ""
    Write-Host "📋 Step 6: Showing initial log output..." -ForegroundColor Yellow
    & ssh "${RpiUser}@${RpiIP}" "cd $RpiPath; tail -20 rpi_detect.log"
    Write-Host ""
    Write-Host "🎯 Deployment Complete!" -ForegroundColor Green
    Write-Host "======================================================="
    Write-Host "✅ Updated script deployed and running" -ForegroundColor Green
    Write-Host "✅ Face detection completely removed" -ForegroundColor Green
    Write-Host "✅ Database initialization should now work" -ForegroundColor Green
    Write-Host "✅ Detection data will flow to backend" -ForegroundColor Green
    Write-Host ""
    Write-Host "📊 Monitor logs: ssh ${RpiUser}@${RpiIP} 'cd $RpiPath; tail -f rpi_detect.log'" -ForegroundColor Cyan
    Write-Host "🔍 Check backend: curl https://smoki-backend-rpi.onrender.com/api/stream/status" -ForegroundColor Cyan
} else {
    Write-Host "❌ Failed to start script" -ForegroundColor Red
    Write-Host "📋 Checking error logs..." -ForegroundColor Yellow
    & ssh "${RpiUser}@${RpiIP}" "cd $RpiPath; tail -10 rpi_detect.log"
    exit 1
}