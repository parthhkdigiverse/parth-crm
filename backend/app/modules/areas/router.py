# backend/app/modules/areas/router.py
from typing import List, Any, Optional
from fastapi import APIRouter, Depends, status
from beanie import PydanticObjectId
from app.core.dependencies import RoleChecker
from app.modules.users.models import User, UserRole
from app.modules.areas.schemas import AreaCreate, AreaRead, AreaAssign, AreaUpdate
from app.modules.areas.service import AreaService

router = APIRouter()

# Role Checkers
admin_access = RoleChecker([UserRole.ADMIN])
staff_access = RoleChecker([
    UserRole.ADMIN, UserRole.SALES, UserRole.TELESALES,
    UserRole.PROJECT_MANAGER, UserRole.PROJECT_MANAGER_AND_SALES
])

@router.post("/", response_model=AreaRead, status_code=status.HTTP_201_CREATED)
async def create_area(
    area_in: AreaCreate,
    current_user: User = Depends(staff_access)
) -> Any:
    """
    Create a new Area. Available to staff.
    """
    service = AreaService()
    return await service.create_area(area_in, current_user)

@router.patch("/{area_id}", response_model=AreaRead)
async def update_area(
    area_id: PydanticObjectId,
    area_in: AreaUpdate,
    current_user: User = Depends(admin_access)
) -> Any:
    """
    Update an existing Area's name, description, or coordinates. Admin only.
    """
    service = AreaService()
    return await service.update_area(area_id, area_in)

@router.get("/archived", response_model=List[AreaRead])
async def read_archived_areas(
    current_user: User = Depends(staff_access)
) -> Any:
    """
    Get all archived areas. Staff scope limited by permissions.
    """
    service = AreaService()
    return await service.get_archived_areas(current_user)

@router.get("/", response_model=List[AreaRead])
async def read_areas(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(staff_access)
) -> Any:
    """
    Fetch active areas with pagination. Admin/Staff read scope.
    """
    service = AreaService()
    return await service.get_areas(current_user, skip, limit)

@router.patch("/{area_id}/assign", response_model=AreaRead)
async def assign_area(
    area_id: PydanticObjectId,
    assign_in: AreaAssign,
    current_user: User = Depends(admin_access)
) -> Any:
    """
    Assign an area to users. Admin only.
    """
    service = AreaService()
    return await service.assign_area(area_id, assign_in.user_ids, current_user, assign_in.shop_ids)

@router.post("/{area_id}/accept", response_model=AreaRead)
async def accept_area(
    area_id: PydanticObjectId,
    current_user: User = Depends(staff_access)
) -> Any:
    """
    Accept an area assignment. User must be in the assigned list.
    """
    service = AreaService()
    return await service.accept_area(area_id, current_user)

@router.delete("/{area_id}", status_code=status.HTTP_200_OK)
async def archive_area(
    area_id: PydanticObjectId,
    current_user: User = Depends(staff_access)
) -> Any:
    """
    Soft-delete (archive) an area and its shops. Available to staff.
    """
    service = AreaService()
    return await service.archive_area(area_id, current_user)

@router.patch("/{area_id}/unarchive", response_model=AreaRead)
async def unarchive_area(
    area_id: PydanticObjectId,
    current_user: User = Depends(staff_access)
) -> Any:
    """
    Unarchive an area. Staff scope limited to owners/assignees.
    """
    service = AreaService()
    return await service.unarchive_area(area_id, current_user)

@router.delete("/{area_id}/hard-delete", status_code=status.HTTP_200_OK)
async def hard_delete_area(
    area_id: PydanticObjectId,
    current_user: User = Depends(admin_access)
) -> Any:
    """
    Permanently delete an area and all associated shops. Admin only.
    """
    service = AreaService()
    return await service.hard_delete_area(area_id)
