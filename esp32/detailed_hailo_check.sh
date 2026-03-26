#!/bin/bash
# Detailed Hailo hardware diagnostics

echo "=== DETAILED HAILO HARDWARE CHECK ==="
echo ""

echo "[1] Full lspci output:"
lspci -v
echo ""

echo "[2] Check PCIe bus status:"
cat /proc/bus/pci/devices 2>/dev/null || echo "  Could not read /proc/bus/pci/devices"
echo ""

echo "[3] Check for any PCIe errors in dmesg:"
dmesg | grep -i "pcie\|pci\|error" | tail -30
echo ""

echo "[4] Check kernel version:"
uname -a
echo ""

echo "[5] Check if PCIe is enabled:"
vcgencmd get_config int | grep pcie || echo "  vcgencmd not available"
echo ""

echo "[6] Check device tree for PCIe:"
find /sys/firmware/devicetree -name "*pcie*" 2>/dev/null || echo "  No PCIe in device tree"
echo ""

echo "[7] Try to rescan PCIe bus:"
echo "  (This requires root)"
echo 1 | sudo tee /sys/bus/pci/rescan 2>/dev/null || echo "  Could not rescan (need sudo)"
echo ""

echo "[8] Check after rescan:"
lspci | grep -i hailo || echo "  Still no Hailo detected"
