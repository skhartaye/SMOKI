from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
import sys
import psycopg
import os
sys.path.append('..')
from postgre.database import init_db_pool, insert_sensor_data, get_latest_sensor_data, update_sensor_data, delete_sensor_data, close_db_pool, get_connection_string, create_default_users
from auth import (
    authenticate_user, create_access_token, get_current_user, 
    get_current_superadmin, get_current_admin_or_superadmin,
    Token, User, ACCESS_TOKEN_EXPIRE_MINUTES
)
from vehicles import router as vehicles_router
from stream import router as stream_router
from webrtc_proxy import router as webrtc_router

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add response headers for streaming
@app.middleware("http")
async def add_stream_headers(request, call_next):
    response = await call_next(request)
    if "/api/stream" in request.url.path:
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Include routers
app.include_router(vehicles_router)
app.include_router(stream_router)
app.include_router(webrtc_router)

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    init_db_pool()
    create_default_users()

# Close database on shutdown
@app.on_event("shutdown")
async def shutdown_event():
    close_db_pool()

class SensorData(BaseModel):
    temperature: float | None = None
    humidity: float | None = None
    pressure: float | None = None
    vocs: float | None = None
    nitrogen_dioxide: float | None = None
    carbon_monoxide: float | None = None
    pm25: float | None = None
    pm10: float | None = None

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/api/auth/login", response_model=Token)
def login(login_data: LoginRequest):
    """Authenticate user and return JWT token"""
    user = authenticate_user(login_data.username, login_data.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password"
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role},
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role,
        "username": user.username
    }

@app.get("/api/auth/me", response_model=User)
def get_me(current_user: User = Depends(get_current_user)):
    """Get current user information"""
    return current_user

@app.get("/api/hello")
def read_root():
    return {"message": "Hello from FastAPI!", "status": "ok"}

@app.get("/api/health")
def health_check():
    """Health check endpoint"""
    try:
        with psycopg.connect(get_connection_string()) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}

@app.get("/api/camera/health")
def camera_health():
    """Check camera health (no auth required)"""
    return {
        "status": "healthy",
        "stream_url": "/api/stream/playlist.m3u8",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/camera/stream")
def camera_stream():
    """Redirect to HLS stream (no auth required)"""
    return {"stream_url": "/api/stream/playlist.m3u8"}

@app.post("/api/camera/detections")
def camera_detections_post():
    """Receive detections from RPi (no auth required)"""
    return {"success": True}

class SmokeDetection(BaseModel):
    timestamp: str
    confidence: float
    smoke_type: str  # 'smoke_black' or 'smoke_white'
    bounding_box: dict | None = None  # {"x1": int, "y1": int, "x2": int, "y2": int}
    camera_id: str = "rpi_camera"
    location: str = "unknown"
    metadata: dict | None = None

@app.post("/api/detections/smoke")
def record_smoke_detection(detection: SmokeDetection):
    """Record smoke detection from RPi camera (no auth required)"""
    try:
        from postgre.database import insert_smoke_detection
        result = insert_smoke_detection(
            timestamp=detection.timestamp,
            confidence=detection.confidence,
            smoke_type=detection.smoke_type,
            bounding_box=detection.bounding_box,
            camera_id=detection.camera_id,
            location=detection.location,
            metadata=detection.metadata
        )
        if result:
            return {"success": True, "data": result}
        else:
            raise HTTPException(status_code=500, detail="Failed to record detection")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/detections/smoke")
def get_smoke_detections(limit: int = 50, hours: int = 24, current_user: User = Depends(get_current_user)):
    """Get recent smoke detections (requires authentication)"""
    try:
        from postgre.database import get_smoke_detections
        detections = get_smoke_detections(limit=limit, hours=hours)
        return {
            "success": True,
            "data": detections,
            "count": len(detections)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/vehicles/detections")
def get_vehicle_detections(limit: int = 10, current_user: User = Depends(get_current_user)):
    """Get recent vehicle detections"""
    try:
        from vehicles import get_recent_violations
        violations = get_recent_violations(limit)
        return {
            "success": True,
            "data": violations
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/time")
def get_server_time():
    """Get server time for debugging timezone issues"""
    return {
        "server_time_utc": datetime.now(timezone.utc).isoformat(),
        "server_time_local": datetime.now().isoformat(),
        "timezone": "UTC" if datetime.now().astimezone().utcoffset().total_seconds() == 0 else str(datetime.now().astimezone().tzinfo)
    }

@app.post("/api/sensors/data")
def add_sensor_data(data: SensorData):
    """Add new sensor reading to database (No auth required for ESP32)"""
    try:
        result = insert_sensor_data(
            temperature=data.temperature,
            humidity=data.humidity,
            pressure=data.pressure,
            vocs=data.vocs,
            nitrogen_dioxide=data.nitrogen_dioxide,
            carbon_monoxide=data.carbon_monoxide,
            pm25=data.pm25,
            pm10=data.pm10
        )
        if result:
            return {"success": True, "data": result}
        else:
            raise HTTPException(status_code=500, detail="Failed to insert data")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sensors/data")
def get_sensor_data(limit: int = 10):
    """Get latest sensor readings (Public access for debugging)"""
    try:
        data = get_latest_sensor_data(limit=limit)
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sensors/latest")
def get_latest_reading():
    """Get the most recent sensor reading (Public access)"""
    try:
        data = get_latest_sensor_data(limit=1)
        if data:
            return {"success": True, "data": data[0]}
        else:
            return {"success": True, "data": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sensors/status")
def get_sensor_status():
    """Get sensor connection status and last update time"""
    try:
        data = get_latest_sensor_data(limit=1)
        if data:
            last_update = data[0].get('timestamp')
            if last_update:
                # Parse timestamp and check if it's older than 30 seconds
                from datetime import datetime
                
                # Handle both string and datetime objects
                if isinstance(last_update, str):
                    last_update_dt = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                else:
                    last_update_dt = last_update
                    
                current_time = datetime.now(timezone.utc)
                time_diff = (current_time - last_update_dt).total_seconds()  # In seconds
                
                is_timeout = time_diff > 30  # 30 seconds timeout
                
                return {
                    "success": True,
                    "connected": not is_timeout,
                    "last_update": str(last_update),
                    "seconds_since_update": round(time_diff, 2),
                    "timeout_threshold_seconds": 30
                }
        
        return {
            "success": True,
            "connected": False,
            "last_update": None,
            "seconds_since_update": None,
            "timeout_threshold_seconds": 30
        }
    except Exception as e:
        print(f"Error in get_sensor_status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/sensors/data/{record_id}")
def update_sensor_record(record_id: int, data: SensorData, current_user: User = Depends(get_current_superadmin)):
    """Update sensor reading (Superadmin only)"""
    try:
        result = update_sensor_data(
            record_id=record_id,
            temperature=data.temperature,
            humidity=data.humidity,
            pressure=data.pressure,
            vocs=data.vocs,
            nitrogen_dioxide=data.nitrogen_dioxide,
            carbon_monoxide=data.carbon_monoxide,
            pm25=data.pm25,
            pm10=data.pm10
        )
        if result:
            return {"success": True, "message": "Record updated", "data": result}
        else:
            raise HTTPException(status_code=404, detail="Record not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/sensors/data/{record_id}")
def delete_sensor_record(record_id: int, current_user: User = Depends(get_current_superadmin)):
    """Delete sensor reading (Superadmin only)"""
    try:
        success = delete_sensor_data(record_id)
        if success:
            return {"success": True, "message": f"Record {record_id} deleted"}
        else:
            raise HTTPException(status_code=404, detail="Record not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))