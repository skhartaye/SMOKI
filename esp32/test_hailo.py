#!/usr/bin/env python3
"""
Simple test script to check if Hailo device is available and working
"""

import sys

print("[TEST] Checking Hailo device availability...")

try:
    import hailo_platform as hp
    print("[OK] hailo_platform imported successfully")
except ImportError as e:
    print(f"[ERROR] Failed to import hailo_platform: {e}")
    sys.exit(1)

# Test 1: Check if device exists
print("\n[TEST 1] Checking for available Hailo devices...")
try:
    # Try different methods to list devices
    try:
        devices = hp.Device.scan_devices()
        print(f"[OK] Found {len(devices)} device(s) via scan_devices()")
    except AttributeError:
        # Try alternative method
        print("[INFO] scan_devices() not available, trying get_available_devices()...")
        devices = hp.get_available_devices()
        print(f"[OK] Found {len(devices)} device(s) via get_available_devices()")
    
    for i, device in enumerate(devices):
        print(f"  Device {i}: {device}")
except Exception as e:
    print(f"[WARNING] Could not list devices: {e}")
    print("[INFO] Proceeding to VDevice test anyway...")

# Test 2: Try to create VDevice
print("\n[TEST 2] Attempting to create VDevice...")
try:
    with hp.VDevice() as vdevice:
        print("[OK] VDevice created successfully")
        print(f"  VDevice: {vdevice}")
except Exception as e:
    print(f"[ERROR] Failed to create VDevice: {e}")
    print(f"  Error type: {type(e).__name__}")
    print(f"  Error code: {getattr(e, 'status', 'N/A')}")
    print("\n[DIAGNOSIS]")
    print("  - Hailo library is installed")
    print("  - But no Hailo device is accessible")
    print("  - Possible causes:")
    print("    1. Hailo hardware not connected")
    print("    2. Hailo driver not loaded")
    print("    3. Device already in use by another process")
    print("    4. Device permissions issue")
    sys.exit(1)

print("\n[SUCCESS] Hailo device is working!")
