from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
import sys
sys.path.append('..')
from postgre.database import init_db_pool, insert_sensor_data, get_latest_sensor_data, update_sensor_data, delete_sensor_data, close_db_pool
from auth import (
    authenticate_user, create_access_token, get_current_user, 
    get_current_superadmin, get_current_admin_or_superadmin,
    Token, User, ACCESS_TOKEN_EXPIRE_MINUTES
)
from vehicles import router as vehicles_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
    ],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
    allow_credentials=True,
    max_age=3600
)

# Include routers
app.include_router(vehicles_router)

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    init_db_pool()

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
    return {"message": "Hello from FastAPI!"}

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