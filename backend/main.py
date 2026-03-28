from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, timedelta
import sys
import os
sys.path.append('..')

# Import auth functions
from auth import (
    create_access_token, get_current_user,
    Token, User, ACCESS_TOKEN_EXPIRE_MINUTES, verify_password, get_password_hash
)

app = FastAPI()

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

# Startup event - NO database dependency
@app.on_event("startup")
async def startup_event():
    print("🚀 SMOKI Backend API starting up...")
    print("📊 Available endpoints: /docs")

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    print("🛑 SMOKI Backend API shutting down...")

class LoginRequest(BaseModel):
    username: str
    password: str

# Working credentials - these will work immediately
WORKING_USERS = {
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
        print(f"[LOGIN] Available users: {list(WORKING_USERS.keys())}")
        
        # Check working users
        user_data = WORKING_USERS.get(login_data.username)
        if not user_data:
            print(f"[LOGIN] User {login_data.username} not found")
            raise HTTPException(status_code=401, detail="Incorrect username or password")
        
        print(f"[LOGIN] User found: {user_data['username']}")
        
        # Verify password
        if not verify_password(login_data.password, user_data['password_hash']):
            print(f"[LOGIN] Invalid password for user: {login_data.username}")
            raise HTTPException(status_code=401, detail="Incorrect username or password")
        
        print(f"[LOGIN] Password verified for user: {login_data.username}")
        
        # Create token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user_data['username'], "role": user_data['role']},
            expires_delta=access_token_expires
        )
        
        print(f"[LOGIN] Token created for user: {login_data.username}")
        
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

# Mock sensor endpoints
@app.get("/api/sensors/data")
def get_sensor_data(limit: int = 10):
    """Get mock sensor readings"""
    return {
        "success": True, 
        "data": [
            {
                "id": 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "temperature": 25.5,
                "humidity": 60.2,
                "pressure": 1013.25,
                "pm25": 8.5,
                "pm10": 12.3
            }
        ]
    }

@app.get("/api/sensors/latest")
def get_latest_reading():
    """Get mock latest sensor reading"""
    return {
        "success": True,
        "data": {
            "id": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "temperature": 25.5,
            "humidity": 60.2,
            "pressure": 1013.25,
            "pm25": 8.5,
            "pm10": 12.3
        }
    }

@app.get("/api/sensors/status")
def get_sensor_status():
    """Get mock sensor status"""
    return {
        "success": True,
        "connected": True,
        "last_update": datetime.now(timezone.utc).isoformat(),
        "seconds_since_update": 5.2,
        "timeout_threshold_seconds": 30
    }

# ============ CORRELATION API ENDPOINTS ============

@app.get("/api/correlation/pm-smoke")
def get_pm_smoke_correlation(limit: int = 100):
    """Get correlation data with historical smoke events on LEFT, latest trends on RIGHT"""
    try:
        # 1. HISTORICAL DATA (LEFT SIDE) - March 27, 2026 smoke events
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
        
        # 2. RECENT TREND DATA (RIGHT SIDE) - March 28, 2026 normal readings
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
        
        # Combine historical events and recent trends
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