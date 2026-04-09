# backend/app/modules/settings/router.py
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from app.core.dependencies import RoleChecker, get_current_user
from app.modules.users.models import User, UserRole
from app.modules.settings.models import SystemSettings
from app.modules.settings.schemas import SystemSettingsRead, SystemSettingsUpdate

router = APIRouter()
admin_access = RoleChecker([UserRole.ADMIN])

@router.get("/", response_model=SystemSettingsRead)
async def get_settings(
    current_user: User = Depends(get_current_user)
) -> Any:
    # Get or create the single settings row
    settings_obj = await SystemSettings.find_one()
    if not settings_obj:
        settings_obj = SystemSettings(feature_flags={"enable_soft_delete": True})
        await settings_obj.insert()
    return settings_obj

@router.patch("/", response_model=SystemSettingsRead)
async def update_settings(
    settings_in: SystemSettingsUpdate,
    current_user: User = Depends(admin_access)
) -> Any:
    """Update global system settings (Admin only)."""
    settings_obj = await SystemSettings.find_one()
    if not settings_obj:
        settings_obj = SystemSettings(feature_flags={"enable_soft_delete": True})
        await settings_obj.insert()
    
    if settings_in.feature_flags is not None:
        current_flags = settings_obj.feature_flags or {}
        settings_obj.feature_flags = {**current_flags, **settings_in.feature_flags}
    
    if settings_in.access_policy is not None:
        settings_obj.access_policy = settings_in.access_policy
    
    if settings_in.delete_policy is not None:
        settings_obj.delete_policy = settings_in.delete_policy
    
    if settings_in.payslip_email is not None:
        settings_obj.payslip_email = settings_in.payslip_email
    
    if settings_in.payslip_phone is not None:
        settings_obj.payslip_phone = settings_in.payslip_phone
    
    await settings_obj.save()
    return settings_obj

@router.get("/access-control")
async def get_access_control(
    current_user: User = Depends(get_current_user)
):
    settings_obj = await SystemSettings.find_one()
    if not settings_obj:
        return {"page_access": {}, "feature_access": {}}
    return settings_obj.access_policy or {}

@router.post("/access-control")
async def set_access_control(
    data: dict,
    current_user: User = Depends(admin_access)
):
    settings_obj = await SystemSettings.find_one()
    if not settings_obj:
        settings_obj = SystemSettings(feature_flags={}, access_policy={})
        await settings_obj.insert()
    
    settings_obj.access_policy = data
    await settings_obj.save()
    return JSONResponse(content=data)
