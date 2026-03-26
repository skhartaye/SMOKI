#!/bin/bash
# Diagnose why Hailo device isn't being detected

echo "=== HAILO DEVICE DIAGNOSTICS ==="
echo ""

echo "[STEP 1] Check if Hailo is visible on PCIe bus"
echo "Running: lspci | grep -i hailo"
lspci | grep -i hailo
if [ $? -eq 0 ]; then
    echo "✓ Hailo device found on PCIe bus"
else
    echo "✗ Hailo device NOT found on PCIe bus"
    echo ""
    echo "  Possible causes:"
    echo "  1. Device not connected to PCIe slot"
    echo "  2. PCIe not enabled in firmware"
    echo "  3. Device not powered"
    echo ""
    echo "  Try:"
    echo "  - Check physical connection"
    echo "  - Run: sudo raspi-config -> Advanced -> PCIe -> Enable"
    echo "  - Reboot and try again"
    exit 1
fi

echo ""
echo "[STEP 2] Check if Hailo kernel module is loaded"
echo "Running: lsmod | grep hailo"
lsmod | grep hailo
if [ $? -eq 0 ]; then
    echo "✓ Hailo kernel module loaded"
else
    echo "✗ Hailo kernel module NOT loaded"
    echo ""
    echo "  Try: sudo modprobe hailo_pci"
    exit 1
fi

echo ""
echo "[STEP 3] Check if device is accessible"
echo "Running: ls -la /dev/hailo*"
ls -la /dev/hailo* 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✓ Hailo device files found"
else
    echo "✗ Hailo device files NOT found"
    echo ""
    echo "  Try: sudo modprobe hailo_pci"
    exit 1
fi

echo ""
echo "[STEP 4] Check if device is in use"
echo "Running: lsof /dev/hailo*"
lsof /dev/hailo* 2>/dev/null
if [ $? -eq 0 ]; then
    echo "⚠ Device is in use by another process"
    echo "  Kill the process and try again"
else
    echo "✓ Device is not in use"
fi

echo ""
echo "[STEP 5] Test Python hailo_platform import"
python3 -c "import hailo_platform; print('✓ hailo_platform imported successfully')" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✓ Python hailo_platform library available"
else
    echo "✗ Python hailo_platform library NOT available"
    echo ""
    echo "  Try: pip install hailo-platform"
    exit 1
fi

echo ""
echo "=== ALL CHECKS PASSED ==="
echo "Hailo device should be working. If rpi_stream.py still fails:"
echo "1. Check the error message in rpi_stream.py output"
echo "2. Verify HEF model files exist at paths in rpi_stream.py"
echo "3. Check system resources (RAM, CPU)"
