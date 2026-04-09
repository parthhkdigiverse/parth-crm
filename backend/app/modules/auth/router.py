# backend/app/modules/auth/router.py
from datetime import timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from beanie import PydanticObjectId
from app.core.config import settings
from app.core.security import create_access_token, get_password_hash, verify_password
from app.core.dependencies import get_current_user, RoleChecker
from app.modules.users.models import User, UserRole
from app.modules.auth.schemas import Token, ChangePasswordRequest, UpdatePreferencesRequest
from app.modules.users.schemas import UserCreate, UserRead, UserProfileUpdate
from app.modules.auth.models import PasswordResetRequest
from app.modules.notifications.models import Notification
from app.modules.activity_logs.service import ActivityLogger
from app.modules.activity_logs.models import ActionType, EntityType
from app.modules.settings.models import SystemSettings

router = APIRouter()

# ──────────────────────────────────────────────────────────────────────────────
# DEMO / FALLBACK account — used when the database is not yet configured.
# ──────────────────────────────────────────────────────────────────────────────
_DEMO_EMAIL    = "admin@example.com"
_DEMO_PASSWORD = "password123"
# Synthetic ID for demo mode - must be a valid 24-char hex string for PydanticObjectId
_DEMO_USER_ID  = "000000000000000000000000"

@router.post("/login", response_model=Token)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    # ── Try the real database first ───────────────────────────────────────────
    db_error = None
    try:
        user = await User.find_one({"email": form_data.username})
    except Exception as db_err:
        # ── Database is not reachable — fall back to demo account ─────────────
        import traceback
        print(f"[ERROR] Database unavailable: {db_err}")
        traceback.print_exc()
        user = None
        db_error = db_err

    if not user:
        if (
            form_data.username == _DEMO_EMAIL
            and form_data.password == _DEMO_PASSWORD
        ):
            print(f"[DEMO MODE] Demo login granted for {_DEMO_EMAIL}")
            access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
            refresh_token_expires = timedelta(days=30)
            return {
                "access_token": create_access_token(
                    _DEMO_USER_ID, expires_delta=access_token_expires
                ),
                "refresh_token": create_access_token(
                    _DEMO_USER_ID, expires_delta=refresh_token_expires
                ),
                "token_type": "bearer",
            }
            
        if db_error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available. Ensure MongoDB is running and initialized.",
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    
    is_password_correct = verify_password(form_data.password, user.hashed_password)

    if not is_password_correct:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account inactive. Contact administrator.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if user.role == UserRole.CLIENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Clients are not allowed to log in to this portal.",
        )
    
    # Log Login
    activity_logger = ActivityLogger()
    await activity_logger.log_activity(
        user_id=user.id,
        user_role=user.role,
        action=ActionType.LOGIN,
        entity_type=EntityType.USER,
        entity_id=user.id,
        request=request
    )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(days=30)
    return {
        "access_token": create_access_token(
            str(user.id), expires_delta=access_token_expires
        ),
        "refresh_token": create_access_token(
            str(user.id), expires_delta=refresh_token_expires
        ),
        "token_type": "bearer",
    }

@router.post("/register")
async def register(
    request: Request,
    user_in: UserCreate
) -> Any:
    user = await User.find_one(User.email == user_in.email)
    user_existed = user is not None
    
    from app.modules.users.service import UserService
    user_service = UserService()
    
    # Handle Employee Code
    if not user_existed and user_in.role != UserRole.CLIENT and not user_in.employee_code:
        emp_code, current_seq = await user_service.get_next_employee_code()
        if emp_code:
            user_in.employee_code = emp_code
            await user_service.increment_employee_code_seq(current_seq)

    if user_existed:
        update_data = user_in.model_dump(exclude_unset=True)
        if "password" in update_data:
            update_data["hashed_password"] = get_password_hash(update_data.pop("password"))
        
        for k, v in update_data.items():
            setattr(user, k, v)
        await user.save()
    else:
        user = User(
            **user_in.model_dump(exclude={"password"}),
            hashed_password=get_password_hash(user_in.password)
        )
        await user.insert()

    # Generate Referral Code
    await user_service.generate_referral_code(user.id)

    # Log Registration/Update
    activity_logger = ActivityLogger()
    await activity_logger.log_activity(
        user_id=user.id,
        user_role=user.role,
        action=ActionType.UPDATE if user_existed else ActionType.CREATE,
        entity_type=EntityType.USER,
        entity_id=user.id,
        request=request
    )

    message = "User profile updated successfully" if user_existed else "User account created successfully"
    return {"message": message, "user": UserRead.model_validate(user)}

@router.post("/refresh", response_model=Token)
async def refresh_token(
    current_user: User = Depends(get_current_user),
) -> Any:
    user_id = str(current_user.id) if current_user else _DEMO_USER_ID
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(days=30)
    return {
        "access_token": create_access_token(
            user_id, expires_delta=access_token_expires
        ),
        "refresh_token": create_access_token(
            user_id, expires_delta=refresh_token_expires
        ),
        "token_type": "bearer",
    }

@router.get("/me", response_model=UserRead)
async def read_current_user(
    current_user: User = Depends(get_current_user)
) -> Any:
    if current_user is None or str(current_user.id) == _DEMO_USER_ID:
        return {
            "id": _DEMO_USER_ID, "email": _DEMO_EMAIL, "name": "Tisha Admin",
            "role": "ADMIN", "is_active": True, "phone": None
        }
    return current_user

@router.get("/profile", response_model=UserRead)
async def read_profile(current_user: User = Depends(get_current_user)) -> Any:
    if current_user is None or str(current_user.id) == _DEMO_USER_ID:
        return {
            "id": _DEMO_USER_ID, "email": _DEMO_EMAIL, "name": "Tisha Admin",
            "role": "ADMIN", "is_active": True, "phone": None
        }
    return current_user

@router.patch("/profile", response_model=UserRead)
async def update_profile(
    request: Request,
    profile_in: UserProfileUpdate,
    current_user: User = Depends(get_current_user)
) -> Any:
    if current_user is None or str(current_user.id) == _DEMO_USER_ID:
         return {
            "id": _DEMO_USER_ID, "email": _DEMO_EMAIL, "name": profile_in.name or "Tisha Admin",
            "role": "ADMIN", "is_active": True, "phone": profile_in.phone
        }

    old_data = {"name": current_user.name, "phone": current_user.phone}
    update_data = profile_in.model_dump(exclude_unset=True)
    
    if "password" in update_data:
        current_user.hashed_password = get_password_hash(update_data.pop("password"))
        
    for field, value in update_data.items():
        setattr(current_user, field, value)
        
    await current_user.save()
    
    activity_logger = ActivityLogger()
    await activity_logger.log_activity(
        user_id=current_user.id,
        user_role=current_user.role,
        action=ActionType.UPDATE,
        entity_type=EntityType.USER,
        entity_id=current_user.id,
        old_data=old_data,
        new_data={"name": current_user.name, "phone": current_user.phone},
        request=request
    )
    return current_user

@router.post("/change-password")
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user)
):
    if current_user is None or str(current_user.id) == _DEMO_USER_ID:
        raise HTTPException(status_code=400, detail="Demo account cannot change password")
        
    if not verify_password(body.old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect current password")
        
    current_user.hashed_password = get_password_hash(body.new_password)
    await current_user.save()
    
    activity_logger = ActivityLogger()
    await activity_logger.log_activity(
        user_id=current_user.id,
        user_role=current_user.role,
        action=ActionType.UPDATE,
        entity_type=EntityType.USER,
        entity_id=current_user.id,
        new_data={"password_changed": True},
        request=request
    )
    return {"message": "Password updated successfully"}

@router.post("/forgot-password")
async def forgot_password(
    request: Request,
    body: dict
):
    email = body.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
        
    user = await User.find_one(User.email == email, User.is_deleted == False)
    
    # Always return 200 to prevent email enumeration, but only act if user exists
    if user and user.role != UserRole.ADMIN:
        # Check if a pending request already exists
        existing_req = await PasswordResetRequest.find_one(
            PasswordResetRequest.user_id == user.id,
            PasswordResetRequest.status == "PENDING"
        )
        
        if not existing_req:
            new_req = PasswordResetRequest(user_id=user.id)
            await new_req.insert()
            
        # Notify admins
        admins = await User.find(User.role == UserRole.ADMIN, User.is_active == True, User.is_deleted == False).to_list()
        for admin in admins:
            notif = Notification(
                user_id=admin.id,
                title="[Request] Password Reset",
                message=f"User {user.name} ({user.email}) has requested a password reset. Go to Users & Roles to action it.",
                is_read=False
            )
            await notif.insert()
            
    return {"message": "If this email is registered, an admin has been notified."}

@router.get("/reset-requests")
async def get_reset_requests(
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    requests = await PasswordResetRequest.find(PasswordResetRequest.status == "PENDING").to_list()
    
    # Enrich with user details
    result = []
    for req in requests:
        user = await User.get(req.user_id)
        if user:
            result.append({
                "id": str(req.id),
                "user_id": str(req.user_id),
                "requested_at": req.requested_at,
                "status": req.status,
                "user_name": user.name,
                "user_email": user.email,
                "user_role": user.role.value if hasattr(user.role, "value") else str(user.role)
            })
            
    return result

@router.delete("/reset-requests/{request_id}")
async def resolve_reset_request(
    request_id: PydanticObjectId,
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    req = await PasswordResetRequest.get(request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
        
    from datetime import datetime, UTC
    req.status = "RESOLVED"
    req.resolved_by = current_user.id
    req.resolved_at = datetime.now(UTC)
    await req.save()
    
    return {"message": "Request resolved"}

@router.patch("/preferences")
async def update_preferences(
    request: Request,
    body: UpdatePreferencesRequest,
    current_user: User = Depends(get_current_user)
):
    if current_user is None or str(current_user.id) == _DEMO_USER_ID:
        return {"message": "Preferences updated (Demo Mode)"}
        
    current_prefs = current_user.preferences or {}
    current_user.preferences = {**current_prefs, **body.preferences}
    await current_user.save()
    return {"message": "Preferences updated successfully", "preferences": current_user.preferences}

@router.post("/logout")
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    if current_user and str(current_user.id) != _DEMO_USER_ID:
        activity_logger = ActivityLogger()
        await activity_logger.log_activity(
            user_id=current_user.id,
            user_role=current_user.role,
            action=ActionType.LOGOUT,
            entity_type=EntityType.USER,
            entity_id=current_user.id,
            request=request
        )
    return {"message": "Logged out successfully"}
