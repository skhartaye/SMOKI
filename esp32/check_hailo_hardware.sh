#!/bin/bash
# Check if Hailo hardware is detected

echo "[CHECK] Hailo Hardware Detection"
echo "================================"

echo ""
echo "[1] Checking lspci for Hailo device..."
lspci | grep -i hailo || echo "  No Hailo device found in lspci"

echo ""
echo "[2] Checking lsusb for Hailo device..."
lsusb | grep -i hailo || echo "  No Hailo device found in lsusb"

echo ""
echo "[3] Checking /dev for Hailo device..."
ls -la /dev/hailo* 2>/dev/null || echo "  No /dev/hailo* devices found"

echo ""
echo "[4] Checking dmesg for Hailo errors..."
dmesg | grep -i hailo | tail -20 || echo "  No Hailo messages in dmesg"

echo ""
echo "[5] Checking if hailort service is running..."
systemctl status hailo 2>/dev/null || echo "  hailo service not found"

echo ""
echo "[6] Checking PCIe devices..."
lspci -v | grep -A 5 -B 5 "Hailo" || echo "  No Hailo in PCIe verbose output"

echo ""
echo "[7] Checking kernel modules..."
lsmod | grep hailo || echo "  No hailo kernel module loaded"

echo ""
echo "[8] Checking for Hailo in all devices..."
find /sys/devices -name "*hailo*" 2>/dev/null || echo "  No hailo in /sys/devices"
