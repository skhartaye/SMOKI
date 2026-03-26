# SMOKI PROJECT - COMPLETE PRINTABLE SOURCE CODE

**Project**: Smoke Emission Detection & Violator Documentation System  
**Date**: March 27, 2026  
**Purpose**: Complete source code for printing and reference

---

## 1. RPi Detection System - `esp32/rpi_simple_detect.py`

```python
#!/usr/bin/env python3
"""
rpi_snap.py  —  Smoki Project  |  Snapshot detection every N seconds
═══════════════════════════════════════════════════════════════════════
Every INTERVAL seconds:
  1. Capture one frame from picam2
  2. Run smoke / license-plate / vehicle Hailo models
  3. HOG pedestrian detection → blur pedestrians only (cyclists/motos skipped)
  4. Crop plate regions → EasyOCR
  5. Draw bounding boxes on annotated frame
  6. POST annotated JPEG + all metadata to backend
  7. Sleep until next interval

No FFmpeg, no HLS, no queues, no threads.
Simple, stable, easy to debug.
═══════════════════════════════════════════════════════════════════════
"""

import hailo_platform as hp
import numpy as np
import cv2
import time
import os
import requests
import json
from datetime import datetime, timezone
from picamera2 import Picamera2
from concurrent.futures import ThreadPoolExecutor

# ─── CONFIGURATION ────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env.rpi'))
except ImportError:
    pass

INTERVAL        = 5.0
BACKEND_URL     = os.getenv('API_URL',          'https://smoki-backend-rpi.onrender.com')
CAMERA_ID       = os.getenv('DEVICE_ID',        'rpi_camera_01')
CAMERA_LOCATION = os.getenv('CAMERA_LOCATION',  'Main_Entrance')

PLATE_CONF   = 0.3
SMOKE_CONF   = 0.53
VEHICLE_CONF = 0.3

SMOKE_CLASSES   = {'smoke_black', 'smoke_white'}
VEHICLE_CLASSES = {'passenger', 'puv', 'services', 'two_wheel'}

# ─── PEDESTRIAN BLUR CONFIGURATION ───────────────────────────────────────────
PED_CONF_THRESHOLD  = 0.3    # Minimum HOG score to count as a person
PED_UPSCALE         = 2.0    # Upscale before detection (helps find small/distant people)
PED_BLUR_STRENGTH   = 55     # Gaussian blur kernel strength (odd number)
PED_BLUR_PAD        = 8      # Extra pixels to pad around each detected person box
PED_TEXTURE_THRESHOLD = 38   # Background texture threshold for pedestrian vs rider classification

ALL_MODELS = [
    {
        "hef":     "/home/sevi/smoki_project/src/model-skhart-ready/smoke-hailo8l.hef",
        "classes": ["smoke_black", "smoke_white"],
        "type":    "seg",
        "conf":    SMOKE_CONF,
        "role":    "smoke",
    },
    {
        "hef":     "/home/sevi/smoki_project/src/model-skhart-ready/license-plate-opt-hailo8l.hef",
        "classes": ["license_plate"],
        "type":    "detect",
        "conf":    PLATE_CONF,
        "role":    "plate_detect",
    },
    {
        "hef":     "/home/sevi/smoki_project/src/model-skhart-ready/vehicle-class-hailo8l.hef",
        "classes": ["passenger", "puv", "services", "two_wheel"],
        "type":    "detect",
        "conf":    VEHICLE_CONF,
        "role":    "vehicle",
    },
]
```

---

## 2. Backend Requirements - `backend/requirements.txt`

```
fastapi==0.115.0
uvicorn[standard]==0.32.0
psycopg[binary]==3.3.2
python-dotenv==1.0.0
python-jose[cryptography]==3.3.0
bcrypt==4.2.1
python-multipart==0.0.9
websockets==14.1
requests==2.32.3
```

---

## 3. Database Requirements - `postgre/requirements.txt`

```
psycopg2-binary==2.9.9
python-dotenv==1.0.0
```

---

## 4. Frontend Environment - `frontend/.env`

```
VITE_API_URL=https://smoki-backend-rpi.onrender.com
VITE_API_URL_FALLBACK=http://192.168.100.199:8000
VITE_RPI_IP=192.168.100.199
VITE_HLS_PORT=8001
```

---