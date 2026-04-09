# backend/app/modules/idcards/router.py
from typing import List, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.responses import HTMLResponse
from beanie import PydanticObjectId
from app.core.dependencies import RoleChecker, get_current_user
from app.modules.users.models import User, UserRole
from app.modules.idcards.service import IDCardService

router = APIRouter()

# Role checkers
admin_access = RoleChecker([UserRole.ADMIN])
staff_access = RoleChecker([
    UserRole.ADMIN,
    UserRole.SALES,
    UserRole.TELESALES,
    UserRole.PROJECT_MANAGER,
    UserRole.PROJECT_MANAGER_AND_SALES
])

@router.get("/{user_id}/html", response_class=HTMLResponse)
async def get_idcard_html(
    user_id: PydanticObjectId,
    current_user: User = Depends(staff_access)
) -> Any:
    """Generate printable HTML ID card for a user."""
    # Ensure current user is either admin or the user themselves
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    service = IDCardService()
    html_content = await service.generate_idcard_html(user_id)
    if not html_content:
        raise HTTPException(status_code=404, detail="User not found")
    return HTMLResponse(content=html_content)

@router.get("/my/html", response_class=HTMLResponse)
async def get_my_idcard_html(
    current_user: User = Depends(get_current_user)
) -> Any:
    """Generate printable HTML ID card for current user."""
    service = IDCardService()
    html_content = await service.generate_idcard_html(current_user.id)
    if not html_content:
        raise HTTPException(status_code=404, detail="User profile not found")
    return HTMLResponse(content=html_content)

@router.get("/{user_id}/preview")
async def preview_idcard_data(
    user_id: PydanticObjectId,
    current_user: User = Depends(staff_access)
) -> Any:
    """Returns the user data formatted for ID Card display."""
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    service = IDCardService()
    return await service.get_idcard_data(user_id)
