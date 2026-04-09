# backend/app/modules/clients/router.py
from typing import List, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from beanie import PydanticObjectId
from app.core.dependencies import RoleChecker, get_current_user
from app.modules.users.models import User, UserRole
from app.modules.clients.models import Client
from app.modules.clients.schemas import (
    ClientCreate, ClientRead, ClientUpdate, ClientPMAssign,
    PMWorkloadRead, ClientPMHistoryRead
)
from app.modules.clients.service import ClientService

router = APIRouter()

# Role definitions
admin_checker = RoleChecker([UserRole.ADMIN])
staff_checker = RoleChecker([
    UserRole.ADMIN,
    UserRole.SALES,
    UserRole.TELESALES,
    UserRole.PROJECT_MANAGER,
    UserRole.PROJECT_MANAGER_AND_SALES
])

@router.post("/", response_model=ClientRead, status_code=status.HTTP_201_CREATED)
async def create_client(
    client_in: ClientCreate,
    request: Request,
    current_user: User = Depends(staff_checker)
) -> Any:
    """
    Create a new client. Available for all staff.
    PM is automatically assigned based on current workload.
    """
    service = ClientService()
    # Check email uniqueness
    if client_in.email:
        existing = await Client.find_one(Client.email == client_in.email)
        if existing:
            raise HTTPException(status_code=400, detail=f"Client with email '{client_in.email}' already exists.")

    return await service.create_client(client_in, current_user, request)

@router.get("/", response_model=List[ClientRead])
async def read_clients(
    skip: int = 0,
    limit: Optional[int] = None,
    search: Optional[str] = None,
    status_filter: Optional[str] = None, # renamed from 'status' to avoid conflict
    pm_id: Optional[str] = None,
    sort_by: Optional[str] = "created_at",
    sort_order: Optional[str] = "desc",
    current_user: User = Depends(staff_checker)
) -> Any:
    """
    Retrieve all clients with optional search and pagination.
    PMs only see their assigned clients.
    """
    service = ClientService()
    
    # Normalize status filter
    normalized_status = (status_filter or "").strip().upper()
    if normalized_status in ["ACTIVE", "REFUNDED", "ARCHIVED"]:
        service._target_status = normalized_status
        client_active_status = None
    else:
        client_active_status = True
        if normalized_status in ["INACTIVE", "FALSE"]:
            client_active_status = False
        elif normalized_status == "ALL":
            client_active_status = None

    pm_filter_id = None
    scoped_user_id = None
    scoped_mode = None
    
    if current_user and current_user.role in [UserRole.PROJECT_MANAGER, UserRole.PROJECT_MANAGER_AND_SALES]:
        if current_user.role == UserRole.PROJECT_MANAGER:
            pm_filter_id = current_user.id
            scoped_user_id = current_user.id
            scoped_mode = "pm"
        else:
            scoped_user_id = current_user.id
            scoped_mode = "mixed"
    elif current_user and current_user.role in [UserRole.SALES, UserRole.TELESALES]:
        scoped_user_id = current_user.id
        scoped_mode = "mixed"
    elif pm_id and pm_id not in {"ALL", "all"}:
        try:
            pm_filter_id = PydanticObjectId(pm_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid pm_id format")

    return await service.get_clients(
        skip=skip,
        limit=limit,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        is_active=client_active_status,
        pm_id=pm_filter_id,
        scoped_user_id=scoped_user_id,
        scoped_mode=scoped_mode,
        current_user=current_user,
    )

@router.get("/my-clients", response_model=List[ClientRead])
async def read_my_clients(
    skip: int = 0,
    limit: Optional[int] = None,
    search: Optional[str] = None,
    sort_by: Optional[str] = "created_at",
    sort_order: Optional[str] = "desc",
    current_user: User = Depends(RoleChecker([UserRole.PROJECT_MANAGER, UserRole.PROJECT_MANAGER_AND_SALES]))
) -> Any:
    """Retrieve only the clients assigned to current PM."""
    service = ClientService()
    return await service.get_clients(
        skip=skip,
        limit=limit,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        pm_id=current_user.id
    )

@router.get("/pm-workload", response_model=List[PMWorkloadRead])
async def get_pm_workload(
    current_user: User = Depends(admin_checker)
) -> Any:
    """Admin-only: audit auto-assignment load balancing."""
    return await ClientService().get_pm_workload()

@router.post("/retroactive-balance", status_code=status.HTTP_200_OK)
async def retroactive_balance_clients(
    current_user: User = Depends(admin_checker)
) -> Any:
    """Admin-only: re-balance unassigned clients across PMs."""
    return await ClientService().retroactive_pm_balance()

@router.get("/{client_id}", response_model=ClientRead)
async def read_client_by_id(
    client_id: PydanticObjectId,
    current_user: User = Depends(staff_checker) # using local name from old file logic
) -> Any:
    service = ClientService()
    client = await service.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    if current_user.role != UserRole.ADMIN:
        has_access = (
            client.owner_id == current_user.id
            or client.pm_id == current_user.id
            or client.referred_by_id == current_user.id
        )
        if not has_access:
            raise HTTPException(status_code=403, detail="Access denied")
    return client

@router.patch("/{client_id}", response_model=ClientRead)
async def update_client(
    request: Request,
    client_id: PydanticObjectId,
    client_in: ClientUpdate,
    current_user: User = Depends(staff_checker)
) -> Any:
    service = ClientService()
    return await service.update_client(client_id, client_in, current_user, request)

@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    request: Request,
    client_id: PydanticObjectId,
    current_user: User = Depends(admin_checker)
):
    service = ClientService()
    await service.delete_client(client_id, current_user, request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post("/{client_id}/refund", status_code=status.HTTP_200_OK)
async def refund_client(
    request: Request,
    client_id: PydanticObjectId,
    current_user: User = Depends(admin_checker)
):
    service = ClientService()
    return await service.refund_client(client_id, current_user, request)

@router.post("/{client_id}/archive", status_code=status.HTTP_200_OK)
async def archive_client(
    request: Request,
    client_id: PydanticObjectId,
    current_user: User = Depends(admin_checker)
):
    service = ClientService()
    return await service.archive_client(client_id, current_user, request)

@router.post("/{client_id}/assign-pm", response_model=ClientRead)
async def assign_pm(
    request: Request,
    client_id: PydanticObjectId,
    assign_in: ClientPMAssign,
    current_user: User = Depends(admin_checker)
) -> Any:
    service = ClientService()
    return await service.assign_pm(client_id, assign_in.pm_id, current_user, request)

@router.get("/{client_id}/pm-history", response_model=List[ClientPMHistoryRead])
async def get_client_pm_history(
    client_id: PydanticObjectId,
    current_user: User = Depends(staff_checker)
) -> Any:
    service = ClientService()
    client = await service.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return await service.get_pm_history(client_id)
