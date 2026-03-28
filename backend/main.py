"""
SMOKI Backend API - Main FastAPI Application
"""
from fastapi import FastAPI, HTTPException, Depends, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import json
import os
import sys

# Add postgre directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'postgre'))
sys.path.insert(0, os.path.dirname(__file__))

from auth import (
    create_access_token, verify_password, get_password_hash, 
    get_current_user, get_current_superadmin,
    Token, User, ACCESS_TOKEN_EXPIRE_MINUTES
)
from vehicles import router as vehicles_router
from stream import router as stream_router
from webrtc_proxy import router as webrtc_router

# Initialize FastAPI app
app = FastAPI(
    title="SMOKI API",
    description="Air Quality and Smoke Detection System",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add stream headers middleware
@app.middleware("http")
async def add_stream_headers(request, call_next):
    response = await call_next(request)
    
    # Add CORS headers for streaming endpoints
    if "/api/stream/" in str(request.url):
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

# Startup event
@app.on_event("startup")
async def startup_event():
    print("🚀 SMOKI Backend API starting up...")
    print("📊 Available endpoints: /docs")

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    print("🛑 SMOKI Backend API shutting down...")

# Pydantic models
class SensorData(BaseModel):
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    pressure: Optional[float] = None
    vocs: Optional[float] = None
    nitrogen_dioxide: Optional[float] = None
    carbon_monoxide: Optional[float] = None
    pm25: Optional[float] = None
    pm10: Optional[float] = None

class LoginRequest(BaseModel):
    username: str
    password: str

# Authentication endpoints
@app.post("/api/auth/login", response_model=Token)
def login(login_data: LoginRequest):
    """Login endpoint"""
    try:
        from postgre.database import get_user_by_username
        
        user = get_user_by_username(login_data.username)
        if not user or not verify_password(login_data.password, user['password_hash']):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user['username'], "role": user['role']},
            expires_delta=access_token_expires
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user": {
                "username": user['username'],
                "role": user['role']
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/auth/me")
def get_me(current_user: User = Depends(get_current_user)):
    """Get current user info"""
    return current_user

# Basic endpoints
@app.get("/")
def read_root():
    return {"message": "SMOKI Backend API", "status": "running", "version": "1.0.0"}

@app.get("/api/health")
def health_check():
    """Health check endpoint"""
    try:
        from postgre.database import get_connection_string
        import psycopg
        
        with psycopg.connect(get_connection_string()) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}

# Sensor data endpoints
@app.post("/api/sensors/data")
def add_sensor_data(data: SensorData):
    """Add sensor data"""
    try:
        from postgre.database import insert_sensor_data
        
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
            return {"success": True, "id": result}
        else:
            raise HTTPException(status_code=500, detail="Failed to insert data")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sensors/data")
def get_sensor_data(limit: int = 10):
    """Get sensor data"""
    try:
        from postgre.database import get_latest_sensor_data
        data = get_latest_sensor_data(limit=limit)
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sensors/latest")
def get_latest_reading():
    """Get latest sensor reading"""
    try:
        from postgre.database import get_latest_sensor_data
        data = get_latest_sensor_data(limit=1)
        if data:
            return {"success": True, "data": data[0]}
        else:
            return {"success": True, "data": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sensors/status")
def get_sensor_status():
    """Get sensor connection status"""
    try:
        # Simple status check - just return a basic response for now
        return {
            "success": True,
            "connected": False,
            "last_update": None,
            "seconds_since_update": None,
            "timeout_threshold_seconds": 30,
            "message": "Sensor status endpoint active"
        }
    except Exception as e:
        print(f"Error in get_sensor_status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/time")
def get_server_time():
    """Get server time"""
    return {
        "server_time": datetime.now().isoformat(),
        "utc_time": datetime.utcnow().isoformat()
    }

# Correlation endpoint
@app.get("/api/correlation/pm-smoke")
def get_pm_smoke_correlation(limit: int = 100):
    """Get correlation data with historical smoke events"""
    try:
        # Historical smoke events from March 27, 2026
        historical_events = [
            {
                'timestamp': '2026-03-27T04:39:28+00:00',
                'pm25': 9,
                'pm10': 15,
                'smoke_events': 1,
                'combined_pm': 12,
                'is_real_event': True
            },
            {
                'timestamp': '2026-03-27T04:42:10+00:00',
                'pm25': 9,
                'pm10': 15,
                'smoke_events': 1,
                'combined_pm': 12,
                'is_real_event': True
            },
            {
                'timestamp': '2026-03-27T04:42:19+00:00',
                'pm25': 10,
                'pm10': 16,
                'smoke_events': 1,
                'combined_pm': 13,
                'is_real_event': True
            },
            {
                'timestamp': '2026-03-27T04:42:25+00:00',
                'pm25': 10,
                'pm10': 16,
                'smoke_events': 1,
                'combined_pm': 13,
                'is_real_event': True
            },
            {
                'timestamp': '2026-03-27T04:44:40+00:00',
                'pm25': 11,
                'pm10': 17,
                'smoke_events': 1,
                'combined_pm': 14,
                'is_real_event': True
            },
            {
                'timestamp': '2026-03-27T05:55:10+00:00',
                'pm25': 11,
                'pm10': 17,
                'smoke_events': 1,
                'combined_pm': 14,
                'is_real_event': True
            }
        ]
        
        # Recent trend data from March 28, 2026
        recent_trends = [
            {
                'timestamp': '2026-03-28T08:00:00+00:00',
                'pm25': 8,
                'pm10': 12,
                'smoke_events': 0,
                'combined_pm': 10,
                'is_real_event': False
            },
            {
                'timestamp': '2026-03-28T08:15:00+00:00',
                'pm25': 7,
                'pm10': 11,
                'smoke_events': 0,
                'combined_pm': 9,
                'is_real_event': False
            },
            {
                'timestamp': '2026-03-28T08:30:00+00:00',
                'pm25': 8,
                'pm10': 13,
                'smoke_events': 0,
                'combined_pm': 10,
                'is_real_event': False
            },
            {
                'timestamp': '2026-03-28T08:45:00+00:00',
                'pm25': 9,
                'pm10': 14,
                'smoke_events': 0,
                'combined_pm': 11,
                'is_real_event': False
            },
            {
                'timestamp': '2026-03-28T09:00:00+00:00',
                'pm25': 8,
                'pm10': 12,
                'smoke_events': 0,
                'combined_pm': 10,
                'is_real_event': False
            },
            {
                'timestamp': '2026-03-28T09:15:00+00:00',
                'pm25': 7,
                'pm10': 11,
                'smoke_events': 0,
                'combined_pm': 9,
                'is_real_event': False
            }
        ]
        
        # Combine data
        correlation_data = historical_events + recent_trends
        
        return {
            "success": True,
            "data": correlation_data,
            "historical_smoke_events": len(historical_events),
            "recent_trend_points": len(recent_trends),
            "total_points": len(correlation_data)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Debug endpoints
@app.get("/api/detections/smoke/events")
def get_smoke_events_debug(limit: int = 50, current_user: User = Depends(get_current_user)):
    """Debug endpoint to see smoke events from detections table"""
    try:
        from postgre.database import get_connection_string
        import psycopg
        
        with psycopg.connect(get_connection_string()) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, timestamp, camera_id, location, smoke_count, vehicle_count, 
                           plate_count, face_count, is_violation, inference_ms, upload_ms, 
                           detections_json
                    FROM detections
                    WHERE smoke_count > 0
                    ORDER BY timestamp DESC
                    LIMIT %s;
                """, (limit,))
                
                rows = cursor.fetchall()
                detections = []
                
                for row in rows:
                    detections_json = json.loads(row[11]) if row[11] else {}
                    detections.append({
                        "id": row[0],
                        "timestamp": row[1].isoformat() if row[1] else None,
                        "camera_id": row[2],
                        "location": row[3],
                        "smoke_count": row[4],
                        "vehicle_count": row[5],
                        "plate_count": row[6],
                        "face_count": row[7],
                        "is_violation": row[8],
                        "inference_ms": row[9],
                        "upload_ms": row[10],
                        "detections_json": detections_json
                    })
                
                return {
                    "success": True,
                    "data": detections,
                    "count": len(detections),
                    "query": f"SELECT * FROM detections WHERE smoke_count > 0 ORDER BY timestamp DESC LIMIT {limit}"
                }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/detections/all/debug")
def get_all_detections_debug(limit: int = 50, current_user: User = Depends(get_current_user)):
    """Debug endpoint to see all detections from detections table"""
    try:
        from postgre.database import get_connection_string
        import psycopg
        
        with psycopg.connect(get_connection_string()) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, timestamp, camera_id, location, smoke_count, vehicle_count, 
                           plate_count, face_count, is_violation, inference_ms, upload_ms, 
                           detections_json
                    FROM detections
                    ORDER BY timestamp DESC
                    LIMIT %s;
                """, (limit,))
                
                rows = cursor.fetchall()
                detections = []
                
                for row in rows:
                    detections_json = json.loads(row[11]) if row[11] else {}
                    detections.append({
                        "id": row[0],
                        "timestamp": row[1].isoformat() if row[1] else None,
                        "camera_id": row[2],
                        "location": row[3],
                        "smoke_count": row[4],
                        "vehicle_count": row[5],
                        "plate_count": row[6],
                        "face_count": row[7],
                        "is_violation": row[8],
                        "inference_ms": row[9],
                        "upload_ms": row[10],
                        "detections_json": detections_json
                    })
                
                return {
                    "success": True,
                    "data": detections,
                    "count": len(detections),
                    "total_smoke_events": len([d for d in detections if d["smoke_count"] > 0]),
                    "query": f"SELECT * FROM detections ORDER BY timestamp DESC LIMIT {limit}"
                }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)