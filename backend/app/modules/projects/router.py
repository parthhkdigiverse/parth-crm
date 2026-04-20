# backend/app/modules/projects/router.py
from typing import List, Any, Optional
from fastapi import APIRouter, Depends, status, Request, Response, HTTPException
from beanie import PydanticObjectId
from app.core.dependencies import RoleChecker
from app.modules.users.models import User, UserRole
from app.modules.projects.schemas import ProjectCreate, ProjectRead, ProjectUpdate
from app.modules.projects.service import ProjectService

router = APIRouter()

admin_access = RoleChecker([UserRole.ADMIN])
staff_access = RoleChecker([
    UserRole.ADMIN, 
    UserRole.SALES, 
    UserRole.TELESALES, 
    UserRole.PROJECT_MANAGER, 
    UserRole.PROJECT_MANAGER_AND_SALES
])
pm_access = RoleChecker([
    UserRole.ADMIN, 
    UserRole.PROJECT_MANAGER, 
    UserRole.PROJECT_MANAGER_AND_SALES
])

@router.post("/", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    request: Request,
    project_in: ProjectCreate,
    current_user: User = Depends(pm_access)
) -> Any:
    service = ProjectService()
    return await service.create_project(project_in, current_user, request)

@router.get("/", response_model=List[ProjectRead])
async def read_projects(
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: User = Depends(staff_access)
) -> Any:
    # ─── RBAC Logic ───
    # Admin: sees all
    # PM: sees projects where they are assigned as PM
    # Sales: sees projects for clients they own/referred
    # PM+Sales: combined visibility (Or condition)
    
    pm_id = None
    client_ids = None
    
    if current_user.role != UserRole.ADMIN:
        from app.modules.clients.models import Client
        
        # 1. Identify PM role context
        if current_user.role in [UserRole.PROJECT_MANAGER, UserRole.PROJECT_MANAGER_AND_SALES]:
            pm_id = current_user.id
            
        # 2. Identify Sales role context
        if current_user.role in [UserRole.SALES, UserRole.TELESALES, UserRole.PROJECT_MANAGER_AND_SALES]:
            owned_clients = await Client.get_pymongo_collection().distinct("_id", {
                "$or": [
                    {"owner_id": current_user.id},
                    {"referred_by_id": current_user.id}
                ],
                "is_deleted": False
            })
            client_ids = [PydanticObjectId(cid) for cid in owned_clients]
            
            # If Sales has NO clients, and they are NOT a PM, they see nothing
            if not client_ids and pm_id is None:
                return []
                
    service = ProjectService()
    return await service.get_projects(skip=skip, limit=limit, pm_id=pm_id, client_ids=client_ids)

@router.get("/{project_id}", response_model=ProjectRead)
async def read_project(
    project_id: PydanticObjectId,
    current_user: User = Depends(staff_access)
) -> Any:
    service = ProjectService()
    project = await service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    # ─── Strict Detail View RBAC ───
    if current_user.role != UserRole.ADMIN:
        from app.modules.clients.models import Client
        is_pm = project.pm_id == current_user.id
        
        # Check client ownership
        client = await Client.get(project.client_id)
        is_owner = False
        if client:
            is_owner = (
                client.owner_id == current_user.id or 
                client.referred_by_id == current_user.id
            )
            
        if not (is_pm or is_owner):
             raise HTTPException(status_code=403, detail="Access denied to this project")
             
    return project

@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    request: Request,
    project_id: PydanticObjectId,
    project_in: ProjectUpdate,
    current_user: User = Depends(staff_access)  # All staff can update project status
) -> Any:
    service = ProjectService()
    return await service.update_project(project_id, project_in, current_user, request)

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    request: Request,
    project_id: PydanticObjectId,
    current_user: User = Depends(admin_access)
) -> Response:
    service = ProjectService()
    await service.delete_project(project_id, current_user, request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
