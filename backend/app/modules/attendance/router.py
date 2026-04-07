# backend/app/modules/attendance/router.py
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from datetime import date as dt_date, timedelta
from beanie import PydanticObjectId

from app.core.dependencies import get_current_active_user
from app.modules.users.models import User, UserRole
from app.modules.attendance.service import AttendanceService
from app.modules.attendance.schemas import (
    AttendanceResponse, AttendanceCreate, PunchStatus, 
    AttendanceLog, AttendanceSummaryResponse, AttendanceSettings
)

router = APIRouter()

@router.post("/punch", response_model=AttendanceResponse)
async def punch_in_out(
    current_user: User = Depends(get_current_active_user)
):
    return await AttendanceService.punch_in_out(current_user)

@router.get("/punch-status", response_model=PunchStatus)
async def get_punch_status(
    current_user: User = Depends(get_current_active_user)
):
    return await AttendanceService.get_punch_status(current_user)

@router.get("/logs", response_model=List[AttendanceLog])
async def get_attendance_logs(
    date: dt_date = Query(...),
    user_id: Optional[PydanticObjectId] = Query(None),
    current_user: User = Depends(get_current_active_user)
):
    target_user_id = user_id if user_id and current_user.role == UserRole.ADMIN else current_user.id
    return await AttendanceService.get_attendance_logs(date, target_user_id)

@router.get("/summary", response_model=AttendanceSummaryResponse)
async def get_attendance_summary(
    background_tasks: BackgroundTasks,
    user_id: Optional[PydanticObjectId] = Query(None),
    start_date: Optional[dt_date] = Query(None),
    end_date: Optional[dt_date] = Query(None),
    reconcile: bool = Query(False),
    current_user: User = Depends(get_current_active_user)
):
    target_user = None
    if user_id:
        if current_user.role != UserRole.ADMIN and user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized")
        target_user = await User.get(user_id)
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")

    # Ensure dates are defaulted before background tasks or service calls
    if not end_date:
        end_date = AttendanceService.get_ist_today()
    if not start_date:
        start_date = end_date - timedelta(days=30)

    # Optimization: Move reconcile to background if it's broad
    if reconcile:
        from datetime import datetime, timezone, timedelta
        # Resolve defaults here — background tasks receive raw values, not the service's defaults
        resolved_end = end_date or datetime.now(timezone.utc).date()
        resolved_start = start_date or (resolved_end - timedelta(days=30))
        settings = await AttendanceService.load_attendance_settings()
        if target_user:
            background_tasks.add_task(AttendanceService.ensure_auto_leaves, target_user, resolved_start, resolved_end, settings)
        else:
            # Multi-user reconciliation in background
            background_tasks.add_task(AttendanceService.reconcile_all_users, resolved_start, resolved_end, settings)

    return await AttendanceService.get_attendance_summary(
        target_user, start_date, end_date, False, current_user
    )

@router.get("/settings", response_model=AttendanceSettings)
async def get_attendance_settings(
    current_user: User = Depends(get_current_active_user)
):
    # Only Admin or PM can view settings (or any active user for self-settings?)
    # For now, load as dict
    data = await AttendanceService.load_attendance_settings()
    return AttendanceSettings(**data)
