from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import sys
sys.path.append('..')
from postgre.database import init_db_pool, insert_sensor_data, get_latest_sensor_data, close_db_pool

app = FastAPI()

# Allow requests from React frontend and ESP32
origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:5174",
    "*"  # Allow all origins (needed for ESP32)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_methods=["*"],
    allow_headers=["*"]
)

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    init_db_pool()

# Close database on shutdown
@app.on_event("shutdown")
async def shutdown_event():
    close_db_pool()

class SensorData(BaseModel):
    temperature: float = None
    humidity: float = None
    vocs: float = None
    nitrogen_dioxide: float = None
    carbon_monoxide: float = None
    pm25: float = None
    pm10: float = None

@app.get("/api/hello")
def read_root():
    return {"message": "Hello from FastAPI!"}

@app.post("/api/sensors/data")
def add_sensor_data(data: SensorData):
    """Add new sensor reading to database"""
    try:
        result = insert_sensor_data(
            temperature=data.temperature,
            humidity=data.humidity,
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
    """Get latest sensor readings"""
    try:
        data = get_latest_sensor_data(limit=limit)
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sensors/latest")
def get_latest_reading():
    """Get the most recent sensor reading"""
    try:
        data = get_latest_sensor_data(limit=1)
        if data:
            return {"success": True, "data": data[0]}
        else:
            return {"success": True, "data": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))