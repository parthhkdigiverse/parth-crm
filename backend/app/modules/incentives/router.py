# backend/app/modules/incentives/router.py
from typing import List, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from beanie import PydanticObjectId
from app.core.dependencies import RoleChecker, get_current_active_user
from app.modules.users.models import User, UserRole
from app.modules.incentives.models import (
    IncentiveSlab, IncentiveSlip, EmployeePerformance
)
from app.modules.notifications.models import Notification
from app.modules.incentives.schemas import (
    IncentiveSlabCreate, IncentiveSlabRead, IncentiveSlabUpdate,
    IncentiveCalculationRequest, IncentiveSlipRead, IncentivePreviewResponse,
    IncentiveBulkCalculationRequest, IncentiveBulkCalculationResponse
)
from app.modules.settings.models import SystemSettings

router = APIRouter()

# Role checkers
admin_checker = RoleChecker([UserRole.ADMIN])
staff_checker = RoleChecker([
    UserRole.ADMIN, UserRole.SALES, UserRole.TELESALES,
    UserRole.PROJECT_MANAGER, UserRole.PROJECT_MANAGER_AND_SALES
])

DEFAULT_FEATURE_ACCESS = {
    "incentive_manage_roles": ["ADMIN"],
    "incentive_view_all_roles": ["ADMIN"],
}

async def _get_feature_roles(feature_key: str) -> set[str]:
    fallback = set(DEFAULT_FEATURE_ACCESS.get(feature_key, ["ADMIN"]))
    settings = await SystemSettings.find_one()
    if not settings or not settings.access_policy:
        return fallback
    
    feature_access = settings.access_policy.get("feature_access") or {}
    configured = feature_access.get(feature_key)
    if isinstance(configured, list) and configured:
        return {str(r).upper() for r in configured if str(r).strip()}
    return fallback

async def _require_feature_access(current_user: User, feature_key: str, detail: str = "Access denied") -> None:
    role_name = (current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)).upper()
    allowed_roles = await _get_feature_roles(feature_key)
    if role_name not in allowed_roles:
        raise HTTPException(status_code=403, detail=detail)

# ─── SLABS ───────────────────────────────────────────────────────────────────

@router.post("/slabs", response_model=IncentiveSlabRead)
async def create_incentive_slab(
    slab_in: IncentiveSlabCreate,
    current_user: User = Depends(staff_checker)
) -> Any:
    await _require_feature_access(current_user, "incentive_manage_roles", "You do not have permission to manage incentive slabs")
    db_slab = IncentiveSlab(**slab_in.model_dump())
    await db_slab.insert()
    return db_slab

@router.get("/slabs", response_model=List[IncentiveSlabRead])
async def read_incentive_slabs(
    current_user: User = Depends(staff_checker)
) -> Any:
    return await IncentiveSlab.find_all().sort("min_units").to_list()

@router.put("/slabs/{slab_id}", response_model=IncentiveSlabRead)
async def update_incentive_slab(
    slab_id: PydanticObjectId,
    slab_in: IncentiveSlabUpdate,
    current_user: User = Depends(staff_checker)
) -> Any:
    await _require_feature_access(current_user, "incentive_manage_roles", "You do not have permission to manage incentive slabs")

    slab = await IncentiveSlab.get(slab_id)
    if not slab:
        raise HTTPException(status_code=404, detail="Slab not found")
    
    update_data = slab_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(slab, field, value)
    await slab.save()
    return slab

@router.delete("/slabs/{slab_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_incentive_slab(
    slab_id: PydanticObjectId,
    current_user: User = Depends(staff_checker)
):
    await _require_feature_access(current_user, "incentive_manage_roles", "You do not have permission to manage incentive slabs")

    slab = await IncentiveSlab.get(slab_id)
    if not slab:
        raise HTTPException(status_code=404, detail="Slab not found")
    await slab.delete()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post("/slabs/batch-delete", status_code=status.HTTP_200_OK)
async def batch_delete_slabs(
    slab_ids: List[PydanticObjectId],
    current_user: User = Depends(staff_checker)
):
    await _require_feature_access(current_user, "incentive_manage_roles", "You do not have permission to manage incentive slabs")
    
    from beanie.operators import In
    res = await IncentiveSlab.find(In(IncentiveSlab.id, slab_ids)).delete()
    return {"message": f"Successfully deleted {res.deleted_count} slabs"}

# ─── CALCULATION ─────────────────────────────────────────────────────────────

@router.post("/calculate/preview", response_model=IncentivePreviewResponse)
async def preview_incentive(
    calc_in: IncentiveCalculationRequest,
    current_user: User = Depends(staff_checker)
) -> Any:
    await _require_feature_access(current_user, "incentive_manage_roles", "You do not have permission to calculate incentives")

    from app.modules.incentives.service import IncentiveService
    return await IncentiveService().preview_incentive(calc_in.user_id, calc_in.period, calc_in.closed_units)

@router.post("/calculate", response_model=IncentiveSlipRead)
async def calculate_incentive(
    calc_in: IncentiveCalculationRequest,
    current_user: User = Depends(staff_checker)
) -> Any:
    await _require_feature_access(current_user, "incentive_manage_roles", "You do not have permission to calculate incentives")

    from app.modules.incentives.service import IncentiveService
    return await IncentiveService().calculate_incentive(calc_in)

@router.post("/calculate/bulk", response_model=IncentiveBulkCalculationResponse)
async def calculate_incentive_bulk(
    calc_in: IncentiveBulkCalculationRequest,
    current_user: User = Depends(staff_checker)
) -> Any:
    await _require_feature_access(current_user, "incentive_manage_roles", "You do not have permission to calculate incentives")

    from app.modules.incentives.service import IncentiveService
    return await IncentiveService().calculate_incentive_bulk(calc_in.period)

# ─── SLIPS ───────────────────────────────────────────────────────────────────

@router.get("/slips", response_model=List[IncentiveSlipRead])
async def read_all_incentive_slips(
    current_user: User = Depends(staff_checker)
) -> Any:
    await _require_feature_access(current_user, "incentive_view_all_roles", "You do not have permission to view all incentive slips")

    from app.modules.incentives.service import IncentiveService
    return await IncentiveService().get_all_incentive_slips()

@router.get("/my-slips", response_model=List[IncentiveSlipRead])
async def read_my_incentive_slips(
    current_user: User = Depends(staff_checker)
) -> Any:
    from app.modules.incentives.service import IncentiveService
    return await IncentiveService().get_visible_user_incentive_slips(current_user.id)

@router.get("/slips/{user_id}", response_model=List[IncentiveSlipRead])
async def read_incentive_slips_by_user(
    user_id: PydanticObjectId,
    current_user: User = Depends(staff_checker)
) -> Any:
    can_view_all = (current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)).upper() in await _get_feature_roles("incentive_view_all_roles")
    if not can_view_all and user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
        
    from app.modules.incentives.service import IncentiveService
    return await IncentiveService().get_user_incentive_slips(user_id)

@router.patch("/slips/{slip_id}/remarks", response_model=IncentiveSlipRead)
async def update_incentive_slip_remarks(
    slip_id: PydanticObjectId,
    payload: dict,
    current_user: User = Depends(staff_checker)
) -> Any:
    slip = await IncentiveSlip.get(slip_id)
    if not slip:
        raise HTTPException(status_code=404, detail="Slip not found")

    can_manage = (current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)).upper() in await _get_feature_roles("incentive_manage_roles")
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
        if not slip.is_visible_to_employee:
            raise HTTPException(status_code=400, detail="Remarks can be added only after slip is released")
        if employee_remarks is None:
            raise HTTPException(status_code=400, detail="employee_remarks is required")
        slip.employee_remarks = str(employee_remarks).strip() or None

    await slip.save()
    
    # Enrich for response (Service handles this usually but router can do quick fetch)
    res = IncentiveSlipRead.model_validate(slip)
    from app.modules.users.models import User as UserModel
    u = await UserModel.get(slip.user_id)
    res.user_name = u.name if u else f"User #{slip.user_id}"
    return res

@router.patch("/slips/{slip_id}/visibility", response_model=IncentiveSlipRead)
async def update_incentive_slip_visibility(
    slip_id: PydanticObjectId,
    payload: dict,
    current_user: User = Depends(staff_checker)
) -> Any:
    await _require_feature_access(current_user, "incentive_manage_roles", "You do not have permission to change incentive visibility")

    slip = await IncentiveSlip.get(slip_id)
    if not slip:
        raise HTTPException(status_code=404, detail="Slip not found")

    is_visible = bool(payload.get("is_visible_to_employee", False))
    slip.is_visible_to_employee = is_visible
    await slip.save()

    if is_visible:
        try:
            notif = Notification(
                user_id=slip.user_id,
                title="[Incentive] New Incentive Slip Available",
                message=f"Your incentive slip for period {slip.period} is now available for review."
            )
            await notif.insert()
        except Exception as e:
            print(f"Error creating incentive notification: {e}")

    res = IncentiveSlipRead.model_validate(slip)
    from app.modules.users.models import User as UserModel
    u = await UserModel.get(slip.user_id)
    res.user_name = u.name if u else f"User #{slip.user_id}"
    return res
