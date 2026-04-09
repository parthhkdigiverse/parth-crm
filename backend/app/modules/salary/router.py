# backend/app/modules/salary/router.py
from typing import List, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from beanie import PydanticObjectId
from beanie.operators import In
from datetime import datetime, timezone
import json

from app.core.dependencies import RoleChecker, get_current_user
from app.modules.users.models import User, UserRole
from app.modules.salary.models import LeaveRecord, SalarySlip, LeaveStatus
from app.core.cache import get_or_set, invalidate
from app.modules.salary.schemas import (
    LeaveApplicationCreate, LeaveRecordRead, LeaveApproval,
    SalarySlipGenerate, SalarySlipRead, SalaryPreviewResponse,
    SalaryBulkGenerateRequest, SalaryBulkGenerateResponse
)
from app.modules.notifications.models import Notification
from app.modules.settings.models import SystemSettings
from app.modules.salary.service import SalaryService

router = APIRouter()

# Role checkers
hr_checker = RoleChecker([UserRole.ADMIN])
staff_checker = RoleChecker([
    UserRole.ADMIN,
    UserRole.SALES,
    UserRole.TELESALES,
    UserRole.PROJECT_MANAGER,
    UserRole.PROJECT_MANAGER_AND_SALES
])

DEFAULT_FEATURE_ACCESS = {
    "leave_apply_roles": ["SALES", "TELESALES", "PROJECT_MANAGER", "PROJECT_MANAGER_AND_SALES"],
    "leave_edit_own_roles": ["SALES", "TELESALES", "PROJECT_MANAGER", "PROJECT_MANAGER_AND_SALES"],
    "leave_cancel_own_roles": ["SALES", "TELESALES", "PROJECT_MANAGER", "PROJECT_MANAGER_AND_SALES"],
    "leave_manage_roles": ["ADMIN"],
    "salary_manage_roles": ["ADMIN"],
    "salary_view_all_roles": ["ADMIN"],
}

async def _get_feature_roles(feature_key: str) -> set[str]:
    fallback = set(DEFAULT_FEATURE_ACCESS.get(feature_key, ["ADMIN"]))

    # Cache SystemSettings for 60 seconds to avoid repeated DB reads
    async def _fetch_settings():
        settings = await SystemSettings.find_one()
        return settings
    settings = await get_or_set("system_settings", _fetch_settings, ttl_seconds=60)

    if not settings or not settings.access_policy:
        return fallback
    
    feature_access = settings.access_policy.get("feature_access") or {}
    configured = feature_access.get(feature_key)
    if isinstance(configured, list) and configured:
        return {str(r).upper() for r in configured if str(r).strip()}
    return fallback

async def _require_feature_access(current_user: User, feature_key: str, detail: str = "Access denied") -> None:
    role_name = (current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)).upper()
    allowed = await _get_feature_roles(feature_key)
    if role_name not in allowed:
        raise HTTPException(status_code=403, detail=detail)

async def _leaves_to_dicts(leaves: list[LeaveRecord], current_user_override: User = None) -> list[dict]:
    """Bulk convert leave records to dicts with a SINGLE user fetch."""
    if not leaves:
        return []

    # Collect all unique user IDs needed
    user_ids = set()
    for l in leaves:
        if l.user_id: user_ids.add(l.user_id)
        if l.approved_by: user_ids.add(l.approved_by)

    # If we already have the current user, seed the map to save one lookup
    user_cache: dict = {}
    if current_user_override and current_user_override.id in user_ids:
        user_cache[str(current_user_override.id)] = current_user_override
        user_ids.discard(current_user_override.id)

    # Single bulk fetch for remaining users
    if user_ids:
        fetched = await User.find(In(User.id, list(user_ids))).to_list()
        for u in fetched:
            user_cache[str(u.id)] = u

    results = []
    for l in leaves:
        u = user_cache.get(str(l.user_id))
        approver = user_cache.get(str(l.approved_by)) if l.approved_by else None
        results.append({
            "id": l.id,
            "user_id": l.user_id,
            "start_date": l.start_date,
            "end_date": l.end_date,
            "leave_type": l.leave_type or "CASUAL",
            "day_type": getattr(l, "day_type", "FULL") or "FULL",
            "reason": l.reason,
            "status": l.status,
            "approved_by": l.approved_by,
            "remarks": getattr(l, "remarks", None),
            "user_name": (u.name or u.email) if u else None,
            "approver_name": (approver.name or approver.email) if approver else None,
            "created_at": l.created_at,
            "updated_at": l.updated_at,
        })
    return results

# Keep single-record helper for mutation endpoints (apply/approve/update)
async def _leave_to_dict(l: LeaveRecord, override_user: User = None) -> dict:
    result = await _leaves_to_dicts([l], override_user)
    return result[0] if result else {}

# ═══════════════════════════════════════════════════════
# LEAVE ENDPOINTS
# ═══════════════════════════════════════════════════════

@router.post("/leave", response_model=LeaveRecordRead)
async def apply_leave(
    leave_in: LeaveApplicationCreate,
    current_user: User = Depends(staff_checker)
) -> Any:
    if current_user.role == UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin cannot apply leave")

    await _require_feature_access(current_user, "leave_apply_roles", "You do not have permission to apply leave")

    if leave_in.end_date < leave_in.start_date:
        raise HTTPException(status_code=400, detail="End date must be after start date")

    db_leave = LeaveRecord(
        user_id=current_user.id,
        start_date=leave_in.start_date,
        end_date=leave_in.end_date,
        leave_type=leave_in.leave_type,
        day_type=leave_in.day_type,
        reason=leave_in.reason,
        status=LeaveStatus.PENDING,
    )
    await db_leave.insert()

    # Trigger Admin Notification
    try:
        from app.modules.users.models import User as UserModel
        admins = await UserModel.find(UserModel.role == UserRole.ADMIN, UserModel.is_active == True, UserModel.is_deleted == False).to_list()
        for admin in admins:
            notif = Notification(
                user_id=admin.id,
                title=f"[Leave] New Leave Request: {current_user.name or current_user.email}",
                message=f"{current_user.name or current_user.email} applied for {db_leave.leave_type} leave."
            )
            await notif.insert()
    except Exception as e:
        print(f"Error creating leave notification: {e}")

    return await _leave_to_dict(db_leave, current_user)

@router.patch("/leave/{leave_id}/approve", response_model=LeaveRecordRead)
async def approve_leave(
    leave_id: PydanticObjectId,
    approval_in: LeaveApproval,
    current_user: User = Depends(staff_checker)
) -> Any:
    await _require_feature_access(current_user, "leave_manage_roles", "You do not have permission to approve/reject leave")

    db_leave = await LeaveRecord.find_one(LeaveRecord.id == leave_id, LeaveRecord.is_deleted != True)
    if not db_leave:
        raise HTTPException(status_code=404, detail="Leave record not found")

    db_leave.status = approval_in.status
    if approval_in.status == LeaveStatus.APPROVED:
        db_leave.approved_by = current_user.id
    if approval_in.remarks is not None:
        db_leave.remarks = approval_in.remarks.strip() or None

    await db_leave.save()
    return await _leave_to_dict(db_leave)

@router.get("/leave", response_model=List[LeaveRecordRead])
async def get_my_leaves(
    current_user: User = Depends(staff_checker)
) -> Any:
    leaves = await LeaveRecord.find(
        LeaveRecord.user_id == current_user.id,
        LeaveRecord.is_deleted != True
    ).sort("-start_date").to_list()
    return await _leaves_to_dicts(leaves, current_user)

@router.get("/leave/all", response_model=List[LeaveRecordRead])
async def get_all_leaves(
    current_user: User = Depends(staff_checker)
) -> Any:
    await _require_feature_access(current_user, "leave_manage_roles", "You do not have permission to view all leave records")

    leaves = await LeaveRecord.find(LeaveRecord.is_deleted != True).sort("-start_date").to_list()
    return await _leaves_to_dicts(leaves)

@router.patch("/leave/{leave_id}", response_model=LeaveRecordRead)
async def update_my_leave(
    leave_id: PydanticObjectId,
    leave_in: LeaveApplicationCreate,
    current_user: User = Depends(staff_checker)
) -> Any:
    await _require_feature_access(current_user, "leave_edit_own_roles", "You do not have permission to edit leave")

    db_leave = await LeaveRecord.find_one(LeaveRecord.id == leave_id, LeaveRecord.is_deleted != True)
    if not db_leave:
        raise HTTPException(status_code=404, detail="Leave record not found")
    if db_leave.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can edit only your own leave")
    if db_leave.status != LeaveStatus.PENDING:
        raise HTTPException(status_code=400, detail="Only pending leave can be edited")
    if leave_in.end_date < leave_in.start_date:
        raise HTTPException(status_code=400, detail="End date must be after start date")

    db_leave.start_date = leave_in.start_date
    db_leave.end_date = leave_in.end_date
    db_leave.leave_type = leave_in.leave_type
    db_leave.day_type = leave_in.day_type
    db_leave.reason = leave_in.reason

    await db_leave.save()
    return await _leave_to_dict(db_leave, current_user)

@router.get("/leave/summary/{user_id}")
async def get_leave_summary(
    user_id: PydanticObjectId,
    month: str = Query(..., description="YYYY-MM"),
    current_user: User = Depends(staff_checker)
) -> Any:
    """Return leave counts for a user in the given month."""
    if current_user.role != UserRole.ADMIN and user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    year, month_num = map(int, month.split('-'))
    
    # MongoDB filter for year/month on start_date
    import calendar
    _, last_day = calendar.monthrange(year, month_num)
    start_dt = datetime(year, month_num, 1, tzinfo=timezone.utc)
    end_dt = datetime(year, month_num, last_day, 23, 59, 59, tzinfo=timezone.utc)

    leaves = await LeaveRecord.find(
        LeaveRecord.user_id == user_id,
        LeaveRecord.is_deleted != True,
        LeaveRecord.start_date >= start_dt,
        LeaveRecord.start_date <= end_dt
    ).to_list()

    total = 0
    approved = 0
    pending = 0
    rejected = 0
    for l in leaves:
        days = (l.end_date - l.start_date).days + 1
        total += days
        if l.status == LeaveStatus.APPROVED:
            approved += days
        elif l.status == LeaveStatus.PENDING:
            pending += days
        else:
            rejected += days

    paid = min(approved, 1)
    unpaid = max(0, approved - 1)
    return {
        "user_id": str(user_id),
        "month": month,
        "total_leave_days": total,
        "approved_days": approved,
        "pending_days": pending,
        "rejected_days": rejected,
        "paid_leaves": paid,
        "unpaid_leaves": unpaid,
    }

@router.delete("/leave/{leave_id}", status_code=204)
async def delete_leave(
    leave_id: PydanticObjectId,
    current_user: User = Depends(staff_checker)
) -> Response:
    leave = await LeaveRecord.find_one(LeaveRecord.id == leave_id, LeaveRecord.is_deleted != True)
    if not leave:
        raise HTTPException(status_code=404, detail="Leave not found")

    settings = await SystemSettings.find_one()
    delete_policy = settings.delete_policy if settings else "SOFT"
    
    can_manage = (current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)).upper() in await _get_feature_roles("leave_manage_roles")
    can_cancel_own = (current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)).upper() in await _get_feature_roles("leave_cancel_own_roles")

    if can_manage:
        if delete_policy == "HARD":
            await leave.delete()
        else:
            leave.is_deleted = True
            await leave.save()
        return Response(status_code=204)

    if not can_cancel_own:
        raise HTTPException(status_code=403, detail="Access denied")
    if leave.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can cancel only your own leave")
    if leave.status != LeaveStatus.PENDING:
        raise HTTPException(status_code=400, detail="Only pending leave can be cancelled")

    leave.is_deleted = True
    await leave.save()
    return Response(status_code=204)

# ═══════════════════════════════════════════════════════
# SALARY ENDPOINTS
# ═══════════════════════════════════════════════════════

@router.get("/salary/preview", response_model=SalaryPreviewResponse)
async def preview_salary(
    user_id: PydanticObjectId = Query(...),
    month: str = Query(...),
    extra_deduction: float = Query(0.0),
    base_salary: float = Query(None),
    current_user: User = Depends(staff_checker)
) -> Any:
    await _require_feature_access(current_user, "salary_manage_roles", "You do not have permission to preview salary")
    return await SalaryService().preview_salary(user_id, month, extra_deduction, base_salary=base_salary)

@router.post("/salary/generate-bulk", response_model=SalaryBulkGenerateResponse)
async def generate_bulk_salary(
    bulk_in: SalaryBulkGenerateRequest,
    current_user: User = Depends(staff_checker)
) -> Any:
    await _require_feature_access(current_user, "salary_manage_roles", "You do not have permission to generate bulk salary")
    return await SalaryService().generate_bulk_salary(bulk_in.month, bulk_in.extra_deduction_default)

@router.post("/salary/generate", response_model=SalarySlipRead)
async def generate_salary_slip(
    salary_in: SalarySlipGenerate,
    current_user: User = Depends(staff_checker)
) -> Any:
    await _require_feature_access(current_user, "salary_manage_roles", "You do not have permission to generate salary")
    return await SalaryService().generate_salary_slip(salary_in)

@router.post("/salary/regenerate", response_model=SalarySlipRead)
async def regenerate_salary_slip(
    salary_in: SalarySlipGenerate,
    current_user: User = Depends(staff_checker)
) -> Any:
    await _require_feature_access(current_user, "salary_manage_roles", "You do not have permission to regenerate salary")
    return await SalaryService().regenerate_salary_slip(salary_in)

@router.patch("/salary/update-draft/{slip_id}", response_model=SalarySlipRead)
async def update_draft_salary_slip(
    slip_id: PydanticObjectId,
    salary_in: SalarySlipGenerate,
    current_user: User = Depends(staff_checker)
) -> Any:
    await _require_feature_access(current_user, "salary_manage_roles", "You do not have permission to update draft salary")
    return await SalaryService().update_draft_slip(slip_id, salary_in)

@router.patch("/salary/confirm/{slip_id}", response_model=SalarySlipRead)
async def confirm_salary_slip(
    slip_id: PydanticObjectId,
    current_user: User = Depends(staff_checker)
) -> Any:
    await _require_feature_access(current_user, "salary_manage_roles", "You do not have permission to confirm salary")
    return await SalaryService().confirm_salary_slip(slip_id, current_user.id)

@router.get("/salary/all", response_model=List[SalarySlipRead])
async def get_all_salary_slips(
    current_user: User = Depends(staff_checker)
) -> Any:
    await _require_feature_access(current_user, "salary_view_all_roles", "You do not have permission to view all salary slips")
    return await SalaryService().get_all_salary_slips()

@router.get("/salary/me", response_model=List[SalarySlipRead])
async def get_my_salary_slips(
    current_user: User = Depends(staff_checker)
) -> Any:
    # Non-admins only see CONFIRMED slips
    return await SalaryService().get_user_salary_slips(current_user.id, show_drafts=False, only_visible=True)

@router.get("/salary/{user_id}", response_model=List[SalarySlipRead])
async def get_user_salary_slips(
    user_id: PydanticObjectId,
    current_user: User = Depends(staff_checker)
) -> Any:
    await _require_feature_access(current_user, "salary_view_all_roles", "You do not have permission to view this employee salary slips")
    return await SalaryService().get_user_salary_slips(user_id)

@router.patch("/salary/slip/{slip_id}/remarks", response_model=SalarySlipRead)
async def update_salary_slip_remarks(
    slip_id: PydanticObjectId,
    payload: dict,
    current_user: User = Depends(staff_checker)
) -> Any:
    slip = await SalarySlip.find_one(SalarySlip.id == slip_id, SalarySlip.is_deleted != True)
    if not slip:
        raise HTTPException(status_code=404, detail="Slip not found")

    can_manage = (current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)).upper() in await _get_feature_roles("salary_manage_roles")
    employee_remarks = payload.get("employee_remarks")
    manager_remarks = payload.get("manager_remarks")

    if can_manage:
        if employee_remarks is not None:
            slip.employee_remarks = str(employee_remarks).strip() or None
        if manager_remarks is not None:
            slip.manager_remarks = str(manager_remarks).strip() or None
    else:
        if slip.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        if slip.status != "CONFIRMED" or not slip.is_visible_to_employee:
            raise HTTPException(status_code=400, detail="Remarks can be added only on visible confirmed slips")
        if employee_remarks is None:
            raise HTTPException(status_code=400, detail="employee_remarks is required")
        slip.employee_remarks = str(employee_remarks).strip() or None

    await slip.save()
    return await SalaryService()._format_slip(slip)

@router.patch("/salary/slip/{slip_id}/visibility", response_model=SalarySlipRead)
async def update_salary_slip_visibility(
    slip_id: PydanticObjectId,
    payload: dict,
    current_user: User = Depends(staff_checker)
) -> Any:
    await _require_feature_access(current_user, "salary_manage_roles", "You do not have permission to change salary visibility")
    slip = await SalarySlip.find_one(SalarySlip.id == slip_id, SalarySlip.is_deleted != True)
    if not slip:
        raise HTTPException(status_code=404, detail="Slip not found")

    is_visible = bool(payload.get("is_visible_to_employee", False))
    slip.is_visible_to_employee = is_visible
    await slip.save()

    if is_visible:
        try:
            notif = Notification(
                user_id=slip.user_id,
                title=f"[Salary] Salary Slip Available: {slip.period}",
                message=f"Your salary slip for {slip.period} is now available for review."
            )
            await notif.insert()
        except Exception as e:
            print(f"Error creating salary notification: {e}")

    return await SalaryService()._format_slip(slip)

@router.get("/salary/slip/{slip_id}/invoice")
async def get_salary_invoice(
    slip_id: PydanticObjectId,
    current_user: User = Depends(staff_checker)
) -> Any:
    from fastapi.responses import HTMLResponse
    slip = await SalarySlip.find_one(SalarySlip.id == slip_id, SalarySlip.is_deleted != True)
    if not slip:
        raise HTTPException(status_code=404, detail="Slip not found")

    can_view_all = (current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)).upper() in await _get_feature_roles("salary_view_all_roles")
    if not can_view_all and slip.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    if current_user.role != UserRole.ADMIN and slip.status != "CONFIRMED":
        raise HTTPException(status_code=403, detail="Slip not yet confirmed")

    html = await SalaryService().generate_invoice_html(slip_id)
    return HTMLResponse(content=html)

# ═══════════════════════════════════════════════════════
# PAYSLIP COMPANY SETTINGS
# ═══════════════════════════════════════════════════════

@router.get("/payslip-settings")
async def get_payslip_settings(
    current_user: User = Depends(staff_checker)
) -> Any:
    settings = await SystemSettings.find_one()
    return {
        "email": settings.payslip_email if settings else "hrmangukiya3494@gmail.com",
        "phone": settings.payslip_phone if settings else "8866005029",
    }

@router.put("/payslip-settings")
async def update_payslip_settings(
    payload: dict,
    current_user: User = Depends(staff_checker)
) -> Any:
    await _require_feature_access(current_user, "salary_manage_roles", "You do not have permission to update payslip settings")

    email = (payload.get("email") or "").strip()
    phone = (payload.get("phone") or "").strip()
    if not email or not phone:
        raise HTTPException(status_code=400, detail="Email and phone are required")

    settings = await SystemSettings.find_one()
    if not settings:
        settings = SystemSettings()
    
    settings.payslip_email = email
    settings.payslip_phone = phone
    await settings.save()
    return {"email": email, "phone": phone}

@router.get("/delete-policy")
async def get_delete_policy(
    current_user: User = Depends(staff_checker)
) -> dict:
    await _require_feature_access(current_user, "salary_manage_roles", "You do not have permission to view delete policy")
    settings = await SystemSettings.find_one()
    return {"policy": settings.delete_policy if settings else "SOFT"}

@router.put("/delete-policy")
async def update_delete_policy(
    payload: dict,
    current_user: User = Depends(staff_checker)
) -> dict:
    await _require_feature_access(current_user, "salary_manage_roles", "You do not have permission to update delete policy")

    policy = payload.get("policy")
    if policy not in ["SOFT", "HARD"]:
        raise HTTPException(status_code=400, detail="Invalid policy type. Must be SOFT or HARD.")
    
    settings = await SystemSettings.find_one()
    if not settings:
        settings = SystemSettings()
    
    settings.delete_policy = policy
    await settings.save()
    return {"policy": policy}

@router.delete("/salary/slip/{slip_id}", status_code=204)
async def delete_salary_slip(
    slip_id: PydanticObjectId,
    current_user: User = Depends(staff_checker)
) -> Response:
    await _require_feature_access(current_user, "salary_manage_roles", "You do not have permission to delete salary slips")

    slip = await SalarySlip.find_one(SalarySlip.id == slip_id, SalarySlip.is_deleted != True)
    if not slip:
        raise HTTPException(status_code=404, detail="Slip not found")
        
    settings = await SystemSettings.find_one()
    delete_policy = settings.delete_policy if settings else "SOFT"

    if delete_policy == "HARD":
        await slip.delete()
    else:
        slip.is_deleted = True
        await slip.save()
    return Response(status_code=204)
