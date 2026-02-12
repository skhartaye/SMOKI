"""
Vehicle detection and violation management endpoints
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import sys
sys.path.insert(0, '../postgre')
from database import (
    register_vehicle, get_top_violators, get_vehicle_ranking,
    insert_vehicle_detection, create_violation, get_recent_violations,
    create_notification, get_unread_notifications, mark_notification_read
)
from auth import get_current_user

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])

# ============ MODELS ============

class VehicleDetectionRequest(BaseModel):
    license_plate: str
    vehicle_type: Optional[str] = "unknown"
    location: str
    confidence: float
    smoke_detected: bool = False
    emission_level: str = "normal"
    image_path: Optional[str] = None
    metadata: Optional[dict] = None

class ViolationRequest(BaseModel):
    license_plate: str
    violation_type: str
    severity: str
    description: Optional[str] = None

class NotificationResponse(BaseModel):
    id: int
    title: str
    message: str
    notification_type: str
    timestamp: datetime
    severity: Optional[str] = None
    license_plate: Optional[str] = None

# ============ ENDPOINTS ============

@router.post("/detect")
async def detect_vehicle(request: VehicleDetectionRequest, current_user = Depends(get_current_user)):
    """
    Record a vehicle detection from RPi camera
    """
    try:
        # Register or update vehicle
        vehicle = register_vehicle(request.license_plate, request.vehicle_type)
        if not vehicle:
            raise HTTPException(status_code=400, detail="Failed to register vehicle")
        
        # Insert detection record
        detection = insert_vehicle_detection(
            vehicle_id=vehicle['id'],
            location=request.location,
            confidence=request.confidence,
            smoke_detected=request.smoke_detected,
            emission_level=request.emission_level,
            image_path=request.image_path,
            metadata=request.metadata
        )
        
        if not detection:
            raise HTTPException(status_code=400, detail="Failed to record detection")
        
        return {
            "success": True,
            "vehicle_id": vehicle['id'],
            "detection_id": detection['id'],
            "license_plate": vehicle['license_plate'],
            "violations": vehicle['violations']
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/violation")
async def report_violation(request: ViolationRequest, current_user = Depends(get_current_user)):
    """
    Report a violation for a vehicle
    """
    try:
        # Register vehicle if not exists
        vehicle = register_vehicle(request.license_plate)
        if not vehicle:
            raise HTTPException(status_code=400, detail="Failed to register vehicle")
        
        # Create violation
        violation = create_violation(
            vehicle_id=vehicle['id'],
            detection_id=None,
            violation_type=request.violation_type,
            severity=request.severity,
            description=request.description
        )
        
        if not violation:
            raise HTTPException(status_code=400, detail="Failed to create violation")
        
        # Create notification
        title = f"Violation: {request.license_plate}"
        message = f"{request.violation_type} - {request.description or 'No description'}"
        notification = create_notification(
            violation_id=violation['id'],
            title=title,
            message=message,
            notification_type="violation"
        )
        
        return {
            "success": True,
            "violation_id": violation['id'],
            "notification_id": notification['id'] if notification else None,
            "license_plate": request.license_plate
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/top-violators")
async def get_top_violators_endpoint(limit: int = 5, current_user = Depends(get_current_user)):
    """
    Get top violating vehicles
    """
    try:
        violators = get_top_violators(limit)
        return {
            "success": True,
            "data": violators,
            "count": len(violators)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ranking")
async def get_vehicle_ranking_endpoint(current_user = Depends(get_current_user)):
    """
    Get all vehicles ranked by violations
    """
    try:
        ranking = get_vehicle_ranking()
        return {
            "success": True,
            "data": ranking,
            "count": len(ranking)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/violations/recent")
async def get_recent_violations_endpoint(limit: int = 10, current_user = Depends(get_current_user)):
    """
    Get recent violations
    """
    try:
        violations = get_recent_violations(limit)
        return {
            "success": True,
            "data": violations,
            "count": len(violations)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/notifications/unread")
async def get_unread_notifications_endpoint(limit: int = 10, current_user = Depends(get_current_user)):
    """
    Get unread notifications
    """
    try:
        notifications = get_unread_notifications(limit)
        return {
            "success": True,
            "data": notifications,
            "count": len(notifications)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/notifications/{notification_id}/read")
async def mark_notification_read_endpoint(notification_id: int, current_user = Depends(get_current_user)):
    """
    Mark a notification as read
    """
    try:
        success = mark_notification_read(notification_id)
        if not success:
            raise HTTPException(status_code=404, detail="Notification not found")
        
        return {
            "success": True,
            "notification_id": notification_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
