from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, timedelta
import sys
import os
sys.path.append('..')

# Import database and auth functions
from database import init_db_pool, create_default_users, get_user_by_username
from auth import (
    create_access_token, get_current_user,
    Token, User, ACCESS_TOKEN_EXPIRE_MINUTES, verify_password, get_password_hash
)

# Import routers
from vehicles import router as vehicles_router
from stream import router as stream_router

app = FastAPI()

# Include routers
app.include_router(vehicles_router)
app.include_router(stream_router)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://smoki.aeroband.org",
        "http://localhost:5173",
        "http://localhost:3000",
        "http://192.168.100.199:5173",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup event - with database connection
@app.on_event("startup")
async def startup_event():
    print("🚀 SMOKI Backend API starting up...")
    try:
        init_db_pool()
        create_default_users()
        print("✓ Database connected and initialized")
    except Exception as e:
        print(f"⚠️ Database initialization failed: {e}")
        print("⚠️ Using fallback authentication")
    print("📊 Available endpoints: /docs")

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    print("🛑 SMOKI Backend API shutting down...")

class LoginRequest(BaseModel):
    username: str
    password: str

# Fallback users in case database fails
FALLBACK_USERS = {
    "admin": {
        "username": "admin",
        "password_hash": get_password_hash("admin123"),
        "role": "admin",
        "full_name": "Admin User"
    },
    "admin1234": {
        "username": "admin1234", 
        "password_hash": get_password_hash("superadmin"),
        "role": "admin",
        "full_name": "Admin User"
    },
    "superadmin": {
        "username": "superadmin",
        "password_hash": get_password_hash("superadmin123"),
        "role": "superadmin", 
        "full_name": "Super Admin"
    }
}

@app.post("/api/auth/login", response_model=Token)
def login(login_data: LoginRequest):
    """Authenticate user and return JWT token"""
    try:
        print(f"[LOGIN] Attempting login for user: {login_data.username}")
        
        # Try database authentication first
        try:
            user_data = get_user_by_username(login_data.username)
            if user_data and verify_password(login_data.password, user_data['password_hash']):
                print(f"[LOGIN] Database authentication successful for: {login_data.username}")
                
                access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
                access_token = create_access_token(
                    data={"sub": user_data['username'], "role": user_data['role']},
                    expires_delta=access_token_expires
                )
                
                return {
                    "access_token": access_token,
                    "token_type": "bearer",
                    "role": user_data['role'],
                    "username": user_data['username']
                }
        except Exception as db_error:
            print(f"[LOGIN] Database auth failed: {db_error}")
        
        # Fallback to hardcoded users
        print(f"[LOGIN] Trying fallback authentication for: {login_data.username}")
        user_data = FALLBACK_USERS.get(login_data.username)
        if not user_data:
            print(f"[LOGIN] User {login_data.username} not found in fallback")
            raise HTTPException(status_code=401, detail="Incorrect username or password")
        
        if not verify_password(login_data.password, user_data['password_hash']):
            print(f"[LOGIN] Invalid password for user: {login_data.username}")
            raise HTTPException(status_code=401, detail="Incorrect username or password")
        
        print(f"[LOGIN] Fallback authentication successful for: {login_data.username}")
        
        # Create token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user_data['username'], "role": user_data['role']},
            expires_delta=access_token_expires
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "role": user_data['role'],
            "username": user_data['username']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[LOGIN] Login error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/auth/me", response_model=User)
def get_me(current_user: User = Depends(get_current_user)):
    """Get current user information"""
    return current_user

@app.get("/")
def read_root():
    return {"message": "SMOKI Backend API", "status": "running", "version": "1.0.0"}

@app.get("/api/hello")
def hello():
    return {"message": "Hello from FastAPI!", "status": "ok"}

@app.get("/api/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "database": "not_required"}

@app.get("/api/time")
def get_server_time():
    """Get server time for debugging timezone issues"""
    return {
        "server_time_utc": datetime.now(timezone.utc).isoformat(),
        "server_time_local": datetime.now().isoformat(),
        "timezone": "UTC" if datetime.now().astimezone().utcoffset().total_seconds() == 0 else str(datetime.now().astimezone().tzinfo)
    }

# Real sensor endpoints - database only
@app.get("/api/sensors/data")
def get_sensor_data(limit: int = 10):
    """Get latest sensor readings from database"""
    try:
        from database import get_latest_sensor_data
        data = get_latest_sensor_data(limit=limit)
        return {"success": True, "data": data}
    except Exception as e:
        print(f"[SENSORS] Database error: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/api/sensors/latest")
def get_latest_reading():
    """Get the most recent sensor reading from database"""
    try:
        from database import get_latest_sensor_data
        data = get_latest_sensor_data(limit=1)
        if data:
            return {"success": True, "data": data[0]}
        else:
            return {"success": True, "data": None}
    except Exception as e:
        print(f"[SENSORS] Database error: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/api/sensors/status")
def get_sensor_status():
    """Get sensor connection status and last update time"""
    try:
        from database import get_latest_sensor_data
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
        print(f"[SENSORS] Database error: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

class SensorData(BaseModel):
    temperature: float | None = None
    humidity: float | None = None
    pressure: float | None = None
    vocs: float | None = None
    nitrogen_dioxide: float | None = None
    carbon_monoxide: float | None = None
    pm25: float | None = None
    pm10: float | None = None

@app.post("/api/sensors/data")
def add_sensor_data(data: SensorData):
    """Add new sensor reading to database (No auth required for ESP32)"""
    try:
        from database import insert_sensor_data
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
        print(f"[SENSORS] Insert error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ CORRELATION API ENDPOINTS ============

@app.get("/api/correlation/pm-smoke")
def get_pm_smoke_correlation(limit: int = 100):
    """Get correlation data between PM levels and smoke events from real database"""
    try:
        from database import get_latest_sensor_data, get_smoke_detections
        
        # Get recent sensor data
        sensor_data = get_latest_sensor_data(limit=limit)
        
        # Get recent smoke detections (if function exists)
        try:
            smoke_detections = get_smoke_detections(limit=limit)
        except:
            smoke_detections = []
        
        # Combine sensor data with smoke events
        correlation_data = []
        
        for sensor in sensor_data:
            timestamp = sensor.get('timestamp')
            pm25 = sensor.get('pm25', 0) or 0
            pm10 = sensor.get('pm10', 0) or 0
            
            # Check if there were smoke events around this time
            smoke_events = 0
            for smoke in smoke_detections:
                smoke_time = smoke.get('timestamp')
                # Simple time matching (within 5 minutes)
                if smoke_time and timestamp:
                    # This is a simplified correlation - in production you'd want better time matching
                    smoke_events = 1 if abs((smoke_time - timestamp).total_seconds()) < 300 else 0
                    break
            
            correlation_data.append({
                'timestamp': timestamp.isoformat() if timestamp else None,
                'pm25': pm25,
                'pm10': pm10,
                'smoke_events': smoke_events,
                'combined_pm': (pm25 + pm10) / 2 if pm25 and pm10 else 0,
                'is_real_event': smoke_events > 0
            })
        
        return {
            "success": True,
            "data": correlation_data,
            "sensor_readings": len(sensor_data),
            "smoke_detections": len(smoke_detections),
            "total_points": len(correlation_data)
        }
    except Exception as e:
        print(f"Error in correlation endpoint: {e}")
        # Return empty data instead of mock data
        return {
            "success": True,
            "data": [],
            "sensor_readings": 0,
            "smoke_detections": 0,
            "total_points": 0
        }