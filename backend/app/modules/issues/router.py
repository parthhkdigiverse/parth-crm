# backend/app/modules/issues/router.py
from typing import List, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response, BackgroundTasks, Request
from beanie import PydanticObjectId
from beanie.operators import In
from app.core.dependencies import RoleChecker, get_current_user
from app.modules.users.models import User, UserRole
from app.modules.clients.models import Client
from app.modules.issues.models import Issue
from app.modules.settings.models import SystemSettings
from app.modules.issues.schemas import IssueCreate, IssueRead, IssueUpdate
from app.modules.issues.service import IssueService

router = APIRouter()       # mounted at /clients prefix
global_router = APIRouter() # mounted at /issues prefix

# Role definitions
admin_checker = RoleChecker([UserRole.ADMIN])
staff_checker = RoleChecker([
    UserRole.ADMIN, 
    UserRole.SALES, 
    UserRole.TELESALES, 
    UserRole.PROJECT_MANAGER, 
    UserRole.PROJECT_MANAGER_AND_SALES
])

DEFAULT_FEATURE_ACCESS = {
    "issue_create_roles": ["ADMIN", "SALES", "TELESALES", "PROJECT_MANAGER", "PROJECT_MANAGER_AND_SALES"],
    "issue_manage_roles": ["ADMIN", "PROJECT_MANAGER", "PROJECT_MANAGER_AND_SALES", "SALES", "TELESALES"],
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

@global_router.get("/", response_model=List[IssueRead])
async def read_global_issues(
    skip: int = 0,
    limit: Optional[int] = None,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    client_id: Optional[PydanticObjectId] = None,
    assigned_to_id: Optional[PydanticObjectId] = None,
    pm_id: Optional[str] = None,
    current_user: User = Depends(staff_checker)
) -> Any:
    """Global issue search with filters."""
    service = IssueService()
    if assigned_to_id is None and pm_id and pm_id not in {"ALL", "all"}:
        try:
            assigned_to_id = PydanticObjectId(pm_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid pm_id")

    return await service.get_all_issues_for_user(
        current_user=current_user,
        skip=skip, limit=limit, status=status, severity=severity, 
        client_id=client_id, assigned_to_id=assigned_to_id
    )

@router.post("/{client_id}/issues", response_model=IssueRead)
async def create_issue(
    client_id: PydanticObjectId,
    issue_in: IssueCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(staff_checker)
) -> Any:
    client = await Client.get(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    await _require_feature_access(current_user, "issue_create_roles", "You do not have permission to create issues")
    
    service = IssueService()
    return await service.create_issue(issue_in, client_id, current_user, request=request, background_tasks=background_tasks)

@router.get("/{client_id}/issues", response_model=List[IssueRead])
async def read_client_issues(
    client_id: PydanticObjectId,
    current_user: User = Depends(staff_checker)
) -> Any:
    client = await Client.get(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
        
    if current_user.role != UserRole.ADMIN:
        has_client_access = (
            client.owner_id == current_user.id
            or client.pm_id == current_user.id
            or client.referred_by_id == current_user.id
        )
        if not has_client_access:
            raise HTTPException(status_code=403, detail="Access denied")

    return await Issue.find(Issue.client_id == client_id, Issue.is_deleted != True).to_list()

@router.patch("/issues/{issue_id}", response_model=IssueRead)
async def update_issue(
    issue_id: PydanticObjectId,
    issue_in: IssueUpdate,
    request: Request,
    current_user: User = Depends(staff_checker)
) -> Any:
    await _require_feature_access(current_user, "issue_manage_roles", "You do not have permission to manage issues")

    service = IssueService()
    return await service.update_issue(issue_id, issue_in, current_user, request)

@router.delete("/issues/{issue_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_issue(
    issue_id: PydanticObjectId,
    request: Request,
    current_user: User = Depends(admin_checker)
):
    await _require_feature_access(current_user, "issue_manage_roles", "You do not have permission to delete issues")

    service = IssueService()
    await service.delete_issue(issue_id, current_user, request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@global_router.post("/batch-delete")
async def batch_delete_issues(
    payload: dict,
    request: Request,
    current_user: User = Depends(admin_checker)
):
    await _require_feature_access(current_user, "issue_manage_roles", "You do not have permission to delete issues")
    
    ids = [PydanticObjectId(i) for i in payload.get("ids", []) if i]
    try:
        res = await Issue.find(In(Issue.id, ids)).set({Issue.is_deleted: True})
        return {"message": f"Successfully deleted {res.modified_count} issues"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/issues/{issue_id}", response_model=IssueRead)
async def get_issue_details(
    issue_id: PydanticObjectId,
    current_user: User = Depends(staff_checker)
) -> Any:
    issue = await Issue.get(issue_id)
    if not issue or issue.is_deleted:
        raise HTTPException(status_code=404, detail="Issue not found")

    service = IssueService()
    if not await service.can_access_issue(issue, current_user):
        raise HTTPException(status_code=403, detail="Access denied")

    # Auto-set opened_at for PMs
    client = await Client.get(issue.client_id)
    if current_user and client and current_user.id == client.pm_id and issue.opened_at is None:
        from datetime import datetime, timezone
        issue.opened_at = datetime.now(timezone.utc)
        await issue.save()
        
    return issue
