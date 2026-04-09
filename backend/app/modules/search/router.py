# backend/app/modules/search/router.py
from fastapi import APIRouter, Depends, Query
from typing import Any
from app.modules.search.service import SearchService
from app.core.dependencies import RoleChecker
from app.modules.users.models import UserRole

router = APIRouter()

# Allow all authenticated staff to search
staff_checker = RoleChecker([
    UserRole.ADMIN, 
    UserRole.SALES, 
    UserRole.TELESALES, 
    UserRole.PROJECT_MANAGER, 
    UserRole.PROJECT_MANAGER_AND_SALES
])

@router.get("/")
async def global_search(
    q: str = Query(..., min_length=2),
    current_user = Depends(staff_checker)
) -> Any:
    """Perform a global search across Users, Clients, Shops, and Areas."""
    service = SearchService()
    return await service.global_search(q)
