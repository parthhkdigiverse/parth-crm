# backend/app/modules/users/router.py
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from beanie import PydanticObjectId
from beanie.operators import In
from app.core.dependencies import RoleChecker, get_current_active_user
from app.modules.users.models import User, UserRole
from app.modules.users.schemas import UserRead, UserProfileUpdate
from app.modules.activity_logs.service import ActivityLogger
from app.modules.activity_logs.models import ActionType, EntityType
from app.core.cache import get_or_set, invalidate
from pydantic import BaseModel
import uuid
from datetime import date as dt_date
from app.modules.settings.models import SystemSettings, AppSetting

class UserStatusUpdate(BaseModel):
    is_active: bool

class UserRoleUpdate(BaseModel):
    role: UserRole

class UserIncentiveEligibilityUpdate(BaseModel):
    enabled: bool

class RoleIncentiveEligibilityUpdate(BaseModel):
    role: UserRole
    enabled: bool

DEFAULT_ACCESS_POLICY = {
    "page_access": {
        "ADMIN": ["*"],
        "SALES": ["dashboard.html", "timetable.html", "todo.html", "leads.html", "visits.html", "areas.html", "clients.html", "billing.html", "leaves.html", "salary.html", "salary_slip_view.html", "search.html", "notifications.html", "profile.html", "settings.html", "issues.html", "incentives.html", "employees.html", "projects.html", "projects_demo.html", "employee_report.html", "client_report.html"],
        "TELESALES": ["dashboard.html", "timetable.html", "todo.html", "leads.html", "visits.html", "clients.html", "billing.html", "leaves.html", "salary.html", "salary_slip_view.html", "search.html", "notifications.html", "profile.html", "settings.html", "issues.html", "incentives.html", "employees.html", "projects.html", "projects_demo.html"],
        "PROJECT_MANAGER": ["dashboard.html", "timetable.html", "todo.html", "projects.html", "projects_demo.html", "meetings.html", "issues.html", "clients.html", "billing.html", "feedback.html", "employee_report.html", "client_report.html", "leaves.html", "salary.html", "salary_slip_view.html", "search.html", "notifications.html", "profile.html", "settings.html", "incentives.html", "employees.html"],
        "PROJECT_MANAGER_AND_SALES": ["dashboard.html", "timetable.html", "todo.html", "leads.html", "visits.html", "areas.html", "projects.html", "projects_demo.html", "meetings.html", "issues.html", "clients.html", "billing.html", "feedback.html", "employee_report.html", "client_report.html", "leaves.html", "salary.html", "salary_slip_view.html", "search.html", "notifications.html", "profile.html", "settings.html", "incentives.html", "employees.html"],
        "CLIENT": ["dashboard.html", "projects.html", "billing.html", "feedback.html", "profile.html"]
    },
    "feature_access": {
        "issue_create_roles": ["ADMIN", "SALES", "TELESALES", "PROJECT_MANAGER", "PROJECT_MANAGER_AND_SALES"],
        "issue_manage_roles": ["ADMIN", "PROJECT_MANAGER", "PROJECT_MANAGER_AND_SALES", "SALES", "TELESALES"],
        "invoice_creator_roles": ["ADMIN", "SALES", "TELESALES", "PROJECT_MANAGER_AND_SALES"],
        "invoice_verifier_roles": ["ADMIN"],
        "leave_apply_roles": ["SALES", "TELESALES", "PROJECT_MANAGER", "PROJECT_MANAGER_AND_SALES"],
        "leave_edit_own_roles": ["SALES", "TELESALES", "PROJECT_MANAGER", "PROJECT_MANAGER_AND_SALES"],
        "leave_cancel_own_roles": ["SALES", "TELESALES", "PROJECT_MANAGER", "PROJECT_MANAGER_AND_SALES"],
        "leave_manage_roles": ["ADMIN"],
        "salary_manage_roles": ["ADMIN"],
        "salary_view_all_roles": ["ADMIN"],
        "incentive_manage_roles": ["ADMIN"],
        "incentive_view_all_roles": ["ADMIN"],
        "employee_manage_roles": ["ADMIN"]
    }
}

def _normalize_role_list(roles: Any, fallback: list[str]) -> list[str]:
    valid_roles = {r.value for r in UserRole}
    if roles is None or not isinstance(roles, list):
        return fallback
    normalized = []
    for role in roles:
        role_name = str(role).upper().strip()
        if role_name in valid_roles and role_name not in normalized:
            normalized.append(role_name)
    return normalized

async def _load_access_policy() -> dict:
    async def _fetch():
        row = await SystemSettings.find_one()
        if not row or not row.access_policy:
            return DEFAULT_ACCESS_POLICY
        try:
            data = row.access_policy
            if not isinstance(data, dict):
                return DEFAULT_ACCESS_POLICY
            page_access = data.get("page_access") or {}
            feature_access = data.get("feature_access") or {}

            merged_page_access = {}
            for role, pages in DEFAULT_ACCESS_POLICY["page_access"].items():
                custom_pages = page_access.get(role)
                if isinstance(custom_pages, list):
                    merged = [str(p).strip() for p in custom_pages if str(p).strip()]
                    if ("salary.html" in merged or "salary" in merged) and "salary_slip_view.html" not in merged:
                        merged.append("salary_slip_view.html")
                    merged_page_access[role] = merged
                else:
                    merged_page_access[role] = pages

            merged_feature_access = {}
            for key, roles in DEFAULT_ACCESS_POLICY["feature_access"].items():
                merged_feature_access[key] = _normalize_role_list(feature_access.get(key), roles)

            if "ADMIN" not in merged_feature_access["invoice_verifier_roles"]:
                merged_feature_access["invoice_verifier_roles"].append("ADMIN")
            if "ADMIN" not in merged_feature_access["invoice_creator_roles"]:
                merged_feature_access["invoice_creator_roles"].append("ADMIN")

            return {
                "page_access": merged_page_access,
                "feature_access": merged_feature_access,
            }
        except Exception:
            return DEFAULT_ACCESS_POLICY
    # Cache access policy for 60 seconds
    return await get_or_set("access_policy", _fetch, ttl_seconds=60)

async def _save_access_policy(policy: dict) -> None:
    row = await SystemSettings.find_one()
    if row:
        row.access_policy = policy
        row.policy_version = (row.policy_version or 1) + 1
        await row.save()
    else:
        await SystemSettings(access_policy=policy, policy_version=2).insert()

async def _sync_billing_role_settings(policy: dict) -> None:
    feature_access = policy.get("feature_access") or {}
    creator_roles = feature_access.get("invoice_creator_roles") or ["ADMIN", "SALES", "TELESALES", "PROJECT_MANAGER_AND_SALES"]
    verifier_roles = feature_access.get("invoice_verifier_roles") or ["ADMIN"]

    for key, roles in [
        ("invoice_creator_roles", creator_roles),
        ("invoice_verifier_roles", verifier_roles),
    ]:
        row = await AppSetting.find_one(AppSetting.key == key)
        value = ",".join(sorted({str(r).upper() for r in roles if str(r).strip()}))
        if not value:
            value = "ADMIN"
        if row:
            row.value = value
            await row.save()
        else:
            await AppSetting(key=key, value=value).insert()

router = APIRouter()
admin_checker = RoleChecker([UserRole.ADMIN])

@router.get("/access-policy/status")
async def get_access_policy_status(
    current_user: User = Depends(get_current_active_user)
) -> Any:
    row = await SystemSettings.find_one()
    version = row.policy_version if row else 1
    role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    return {
        "policy_version": version,
        "role": role,
        "user_id": str(current_user.id),
        "is_active": current_user.is_active
    }

@router.get("/access-policy")
async def get_access_policy(
    current_user: User = Depends(admin_checker)
) -> Any:
    return await _load_access_policy()

@router.put("/access-policy")
async def update_access_policy(
    payload: dict,
    current_user: User = Depends(admin_checker)
) -> Any:
    page_access = payload.get("page_access")
    feature_access = payload.get("feature_access")

    if not isinstance(page_access, dict) or not isinstance(feature_access, dict):
        raise HTTPException(status_code=400, detail="page_access and feature_access are required")

    normalized_page_access = {}
    valid_roles = {r.value for r in UserRole}
    if not page_access:
        page_access = {}
    for role, pages in page_access.items():
        role_name = str(role).upper()
        if role_name not in valid_roles:
            continue
        if not isinstance(pages, list):
            continue
        normalized_page_access[role_name] = [str(p).strip() for p in pages if str(p).strip()]

    normalized_feature_access = {
        key: _normalize_role_list(feature_access.get(key), roles)
        for key, roles in DEFAULT_ACCESS_POLICY["feature_access"].items()
    }
    if "ADMIN" not in normalized_feature_access["invoice_verifier_roles"]:
        normalized_feature_access["invoice_verifier_roles"].append("ADMIN")
    if "ADMIN" not in normalized_feature_access["invoice_creator_roles"]:
        normalized_feature_access["invoice_creator_roles"].append("ADMIN")

    new_policy = {
        "page_access": normalized_page_access or DEFAULT_ACCESS_POLICY["page_access"],
        "feature_access": normalized_feature_access,
    }
    await _save_access_policy(new_policy)
    await _sync_billing_role_settings(new_policy)
    return new_policy

@router.get("/access-policy/effective")
async def get_effective_access_policy(
    current_user: User = Depends(get_current_active_user)
) -> Any:
    policy = await _load_access_policy()
    role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    allowed_pages = (policy.get("page_access") or {}).get(role, [])
    if role == "ADMIN" and "*" not in allowed_pages:
        allowed_pages = ["*"]
    feature_access = policy.get("feature_access") or {}
    return {
        "role": role,
        "allowed_pages": allowed_pages,
        "feature_access": feature_access,
        "policy": policy,
    }

@router.get("/", response_model=List[UserRead])
async def list_users(
    current_user: User = Depends(get_current_active_user)
) -> Any:
    if current_user.role != UserRole.ADMIN:
        return [current_user]
    # Cached for 90 seconds — invalidated on any user mutation
    return await get_or_set(
        "all_users_list",
        lambda: User.find(User.is_deleted != True).to_list(),
        ttl_seconds=90
    )

@router.get("/project-managers", response_model=List[UserRead])
async def list_project_managers(
    current_user: User = Depends(get_current_active_user)
) -> Any:
    pm_roles = [UserRole.PROJECT_MANAGER, UserRole.PROJECT_MANAGER_AND_SALES, UserRole.ADMIN]
    return await get_or_set(
        "pm_users_list",
        lambda: User.find(User.is_deleted != True, In(User.role, pm_roles)).to_list(),
        ttl_seconds=90
    )

@router.patch("/incentive-eligibility/by-role")
async def update_role_incentive_eligibility(
    payload: RoleIncentiveEligibilityUpdate,
    current_user: User = Depends(admin_checker)
) -> Any:
    if payload.role == UserRole.CLIENT:
        raise HTTPException(status_code=400, detail="CLIENT role cannot receive incentives")

    update_result = await User.find(
        User.is_deleted != True,
        User.role == payload.role
    ).set({"incentive_enabled": payload.enabled})
    
    return {
        "updated": update_result.modified_count,
        "role": payload.role,
        "incentive_enabled": payload.enabled
    }

@router.patch("/{user_id}/incentive-eligibility", response_model=UserRead)
async def update_user_incentive_eligibility(
    user_id: PydanticObjectId,
    payload: UserIncentiveEligibilityUpdate,
    current_user: User = Depends(admin_checker)
) -> Any:
    user = await User.find_one(User.id == user_id, User.is_deleted != True)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == UserRole.CLIENT:
        raise HTTPException(status_code=400, detail="CLIENT role cannot receive incentives")

    user.incentive_enabled = payload.enabled
    await user.save()
    return user

@router.patch("/{user_id}/role", response_model=UserRead)
async def update_user_role(
    user_id: PydanticObjectId,
    role_in: UserRoleUpdate,
    request: Request,
    current_user: User = Depends(admin_checker)
) -> Any:
    user = await User.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    old_role = user.role
    user.role = role_in.role
    await user.save()
    invalidate("all_users_list"); invalidate("pm_users_list"); invalidate("user_map:")

    activity_logger = ActivityLogger()
    await activity_logger.log_activity(
        user_id=current_user.id if current_user else None,
        user_role=current_user.role if current_user else UserRole.ADMIN,
        action=ActionType.UPDATE,
        entity_type=EntityType.USER,
        entity_id=user.id,
        old_data={"role": old_role},
        new_data={"role": user.role},
        request=request
    )

    return user

@router.patch("/{user_id}/status", response_model=UserRead)
async def update_user_status(
    user_id: PydanticObjectId,
    status_in: UserStatusUpdate,
    request: Request,
    current_user: User = Depends(admin_checker)
) -> Any:
    user = await User.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    old_status = user.is_active
    user.is_active = status_in.is_active
    await user.save()
    invalidate("all_users_list"); invalidate("user_map:")

    activity_logger = ActivityLogger()
    await activity_logger.log_activity(
        user_id=current_user.id if current_user else None,
        user_role=current_user.role if current_user else UserRole.ADMIN,
        action=ActionType.UPDATE,
        entity_type=EntityType.USER,
        entity_id=user.id,
        old_data={"is_active": old_status},
        new_data={"is_active": user.is_active},
        request=request
    )

    return user

@router.get("/config/employee-code")
async def get_employee_code_settings(
    current_user: User = Depends(admin_checker)
) -> Any:
    from app.modules.users.service import UserService
    return await UserService().get_employee_code_settings()

@router.put("/config/employee-code")
async def update_employee_code_settings(
    payload: dict,
    current_user: User = Depends(admin_checker)
) -> Any:
    from app.modules.users.service import UserService
    enabled = payload.get("enabled", True)
    prefix = payload.get("prefix")
    next_seq = payload.get("next_seq")
    if prefix is None or next_seq is None:
        raise HTTPException(status_code=400, detail="prefix and next_seq are required")
    
    try:
        next_seq = int(next_seq)
    except ValueError:
        raise HTTPException(status_code=400, detail="next_seq must be an integer")
        
    return await UserService().update_employee_code_settings(enabled, prefix, next_seq)

@router.patch("/{user_id}/profile", response_model=UserRead)
async def admin_update_user_profile(
    user_id: PydanticObjectId,
    profile_in: UserProfileUpdate,
    request: Request,
    current_user: User = Depends(admin_checker)
) -> Any:
    user = await User.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    old_name = user.name
    update_data = profile_in.model_dump(exclude_unset=True)
    if "password" in update_data and update_data["password"]:
        from app.core.security import get_password_hash
        update_data["hashed_password"] = get_password_hash(update_data.pop("password"))
        
        from app.modules.auth.models import PasswordResetRequest
        from datetime import datetime, UTC
        pending_reqs = await PasswordResetRequest.find(PasswordResetRequest.user_id == user.id, PasswordResetRequest.status == "PENDING").to_list()
        for req in pending_reqs:
            req.status = "RESOLVED"
            req.resolved_by = current_user.id
            req.resolved_at = datetime.now(UTC)
            await req.save()
    else:
        update_data.pop("password", None)

    for field, value in update_data.items():
        setattr(user, field, value)

    # Check for uniqueness if employee_code changed
    if "employee_code" in update_data:
        existing = await User.find_one(User.employee_code == user.employee_code, User.id != user.id)
        if existing:
            raise HTTPException(
                status_code=400, 
                detail=f"Employee code '{user.employee_code}' is already in use by another user"
            )

    await user.save()

    activity_logger = ActivityLogger()
    await activity_logger.log_activity(
        user_id=current_user.id if current_user else None,
        user_role=current_user.role if current_user else UserRole.ADMIN,
        action=ActionType.UPDATE,
        entity_type=EntityType.USER,
        entity_id=user.id,
        old_data={"name": old_name},
        new_data={"name": user.name},
        request=request
    )

    return user

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: PydanticObjectId,
    request: Request,
    current_user: User = Depends(admin_checker)
):
    user = await User.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    old_deleted_status = user.is_deleted
    user.is_deleted = True
    await user.save()

    activity_logger = ActivityLogger()
    await activity_logger.log_activity(
        user_id=current_user.id if current_user else None,
        user_role=current_user.role if current_user else UserRole.ADMIN,
        action=ActionType.DELETE,
        entity_type=EntityType.USER,
        entity_id=user_id,
        old_data={"is_deleted": old_deleted_status},
        new_data={"is_deleted": True},
        request=request
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post("/batch-delete")
async def batch_delete_users(
    ids: List[PydanticObjectId],
    request: Request,
    current_user: User = Depends(admin_checker)
):
    from beanie.operators import In
    try:
        await User.find(In(User.id, ids)).set({"is_deleted": True})
        
        activity_logger = ActivityLogger()
        await activity_logger.log_activity(
            user_id=current_user.id if current_user else None,
            user_role=current_user.role if current_user else UserRole.ADMIN,
            action=ActionType.DELETE,
            entity_type=EntityType.USER,
            entity_id=PydanticObjectId("000000000000000000000000"), 
            old_data={"batch_ids": [str(i) for i in ids]},
            new_data={"is_deleted": True},
            request=request
        )
        return {"message": f"Successfully deleted {len(ids)} users"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{user_id}/referral-code")
async def generate_referral_code(
    user_id: PydanticObjectId,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    user = await User.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    allowed_roles = [
        UserRole.SALES,
        UserRole.TELESALES,
        UserRole.PROJECT_MANAGER,
        UserRole.PROJECT_MANAGER_AND_SALES,
        UserRole.ADMIN
    ]
    if user.role not in allowed_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Referral codes can only be generated for SALES, TELESALES, or PROJECT MANAGER roles"
        )

    if user.referral_code:
        return {"user_id": str(user.id), "code": user.referral_code}

    code = f"REF-{str(user.id)[-6:]}-{str(uuid.uuid4())[:8].upper()}"
    existing = await User.find_one(User.referral_code == code, User.id != user.id)
    if existing:
        raise HTTPException(status_code=400, detail="Referral code collision; try again")

    user.referral_code = code
    await user.save()
    return {"user_id": str(user.id), "code": user.referral_code}

@router.get("/{user_id}/referral-code")
async def get_referral_code(
    user_id: PydanticObjectId,
    current_user: User = Depends(admin_checker)
) -> Any:
    user = await User.get(user_id)
    if not user or not user.referral_code:
        raise HTTPException(status_code=404, detail="Referral code not set for this user")
    return {"user_id": str(user.id), "code": user.referral_code}

@router.get("/public/lookup/{ref_code}")
async def lookup_user_by_referral(
    ref_code: str
) -> Any:
    import re
    user = await User.find_one(
        {"referral_code": re.compile(f"^{ref_code}$", re.IGNORECASE)},
        User.is_deleted != True
    )
    if not user:
        raise HTTPException(status_code=404, detail="Invalid referral code")
    
    return {
        "name": user.name,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role)
    }

@router.get("/lookup/{ref_code}")
async def lookup_user_by_referral_alias(
    ref_code: str
) -> Any:
    return await lookup_user_by_referral(ref_code)

@router.get("/suggest-pm")
async def suggest_pm(
    current_user: User = Depends(get_current_active_user)
) -> Any:
    from app.modules.users.service import UserService
    result = await UserService().suggest_pm()
    if not result:
        raise HTTPException(status_code=404, detail="No Project Managers found")
    return result

@router.get("/{pm_id}/availability")
async def get_pm_availability(
    pm_id: PydanticObjectId,
    date: dt_date,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    from app.modules.users.service import UserService
    result = await UserService().get_pm_availability(pm_id, date)
    if not result:
        raise HTTPException(status_code=404, detail="Project Manager not found")
    return result

class GroupAvailabilityRequest(BaseModel):
    user_ids: List[PydanticObjectId]
    date: dt_date

@router.post("/availability/group")
async def get_group_availability(
    payload: GroupAvailabilityRequest,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    from app.modules.users.service import UserService
    result = await UserService().get_group_availability(payload.user_ids, payload.date)
    if not result:
        raise HTTPException(status_code=404, detail="Users not found or invalid data")
    return result
