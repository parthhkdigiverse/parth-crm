# backend/app/modules/visits/router.py
from datetime import date as dt_date, datetime, timezone
from typing import List, Any, Optional
from fastapi import APIRouter, Depends, status as http_status, Request, UploadFile, File, Form, HTTPException
from beanie import PydanticObjectId
from app.core.dependencies import RoleChecker, get_current_user
from app.modules.users.models import User, UserRole
from app.modules.visits.schemas import VisitCreate, VisitRead, VisitUpdate, VisitStatus
from app.modules.visits.service import VisitService

router = APIRouter()

# Role Access
create_access = RoleChecker([UserRole.ADMIN, UserRole.SALES, UserRole.TELESALES])
read_access = RoleChecker([
    UserRole.ADMIN, 
    UserRole.SALES, 
    UserRole.TELESALES, 
    UserRole.PROJECT_MANAGER, 
    UserRole.PROJECT_MANAGER_AND_SALES
])

@router.post("/", response_model=VisitRead, status_code=http_status.HTTP_201_CREATED)
async def create_visit(
    request: Request,
    shop_id: PydanticObjectId = Form(...),
    remarks: str = Form(...),
    status: str = Form(...),
    visit_date: Optional[str] = Form(None),
    decline_remarks: Optional[str] = Form(None),
    duration_seconds: int = Form(0),
    is_follow_up: Optional[str] = Form("false"),
    storefront_photo: Optional[UploadFile] = File(None),
    selfie_photo: Optional[UploadFile] = File(None),
    current_user: User = Depends(create_access)
) -> Any:
    """
    Create a visit. Accepts multipart/form-data.
    """
    follow_up = str(is_follow_up).lower() == "true"
    
    # Validation for Sales visits — photos required for all outcomes EXCEPT ACCEPT (deal won)
    if current_user.role in [UserRole.SALES, UserRole.PROJECT_MANAGER_AND_SALES]:
        if not follow_up and status != 'ACCEPT' and not (storefront_photo or selfie_photo):
            raise HTTPException(status_code=400, detail="At least one photo (Storefront or Selfie) is mandatory for Sales visits")

    # Date Parsing
    parsed_date = None
    if visit_date:
        try:
            parsed_date = datetime.fromisoformat(visit_date.replace('Z', '+00:00'))
        except Exception:
            parsed_date = datetime.now(timezone.utc)
    else:
        parsed_date = datetime.now(timezone.utc)

    # Status Enum
    try:
        status_enum = VisitStatus(status)
    except ValueError:
        status_enum = VisitStatus.SATISFIED

    visit_in = VisitCreate(
        shop_id=shop_id,
        visit_date=parsed_date,
        remarks=remarks,
        decline_remarks=decline_remarks,
        status=status_enum,
        duration_seconds=duration_seconds
    )

    service = VisitService()
    return await service.create_visit(
        visit_in, 
        current_user, 
        request, 
        storefront_photo=storefront_photo, 
        selfie_photo=selfie_photo
    )

@router.get("/", response_model=List[VisitRead])
async def read_visits(
    skip: int = 0,
    limit: Optional[int] = None,
    shop_id: Optional[PydanticObjectId] = None,
    user_id: Optional[PydanticObjectId] = None,
    area_id: Optional[PydanticObjectId] = None,
    status: Optional[str] = None,
    start_date: Optional[dt_date] = None,
    end_date: Optional[dt_date] = None,
    current_user: User = Depends(read_access)
) -> Any:
    """Get visits with optional filtering. Scoped by user role."""
    # If the user is Sales or Telesales, they can only view their own visits.
    effective_user_id = user_id
    if current_user and current_user.role in [UserRole.SALES, UserRole.TELESALES]:
        effective_user_id = current_user.id
        
    service = VisitService()
    return await service.get_visits(
        skip, limit, 
        current_user=current_user, 
        user_id=effective_user_id, 
        shop_id=shop_id,
        area_id=area_id,
        status=status,
        start_date=start_date,
        end_date=end_date
    )

@router.patch("/{visit_id}", response_model=VisitRead)
async def update_visit(
    request: Request,
    visit_id: PydanticObjectId,
    visit_in: VisitUpdate,
    current_user: User = Depends(create_access)
) -> Any:
    """Update a specific visit entry."""
    service = VisitService()
    return await service.update_visit(visit_id, visit_in, current_user, request)
