# backend/app/modules/shops/router.py
from typing import List, Any, Dict, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, status, Query, HTTPException, Response
from pydantic import BaseModel
from beanie import PydanticObjectId
from app.core.dependencies import RoleChecker, get_current_user
from app.modules.users.models import User, UserRole
from app.modules.shops.schemas import ShopCreate, ShopRead, ShopUpdate, AssignPMRequest
from app.core.enums import MasterPipelineStage
from app.modules.shops.service import ShopService
from app.modules.clients.schemas import ClientRead

class ScheduleDemoRequest(BaseModel):
    scheduled_at: datetime
    title: Optional[str] = None
    demo_type: Optional[str] = None
    notes: Optional[str] = None

router = APIRouter()

# Role checkers
staff_checker = RoleChecker([
    UserRole.ADMIN,
    UserRole.SALES,
    UserRole.TELESALES,
    UserRole.PROJECT_MANAGER,
    UserRole.PROJECT_MANAGER_AND_SALES
])

admin_checker = RoleChecker([UserRole.ADMIN])

pm_checker = RoleChecker([
    UserRole.ADMIN,
    UserRole.PROJECT_MANAGER,
    UserRole.PROJECT_MANAGER_AND_SALES
])

@router.post("/", response_model=ShopRead, status_code=status.HTTP_201_CREATED)
async def create_shop(
    shop_in: ShopCreate,
    current_user: User = Depends(staff_checker)
) -> Any:
    return await ShopService().create_shop(shop_in, current_user)

@router.get("/kanban", response_model=Dict[str, List[ShopRead]])
async def read_kanban_shops(
    my_view: bool = Query(False, description="If true, only return leads assigned to the current user"),
    owner_id: Optional[PydanticObjectId] = Query(None),
    source: Optional[str] = Query(None),
    current_user: User = Depends(staff_checker)
) -> Any:
    employee_roles = {UserRole.SALES, UserRole.TELESALES}
    effective_owner_id = owner_id
    if (current_user and current_user.role in employee_roles) or my_view:
        effective_owner_id = current_user.id if current_user else None
    
    return await ShopService().list_kanban_shops(owner_id=effective_owner_id, source=source)

@router.get("/archived", response_model=List[ShopRead])
async def read_archived_shops(
    current_user: User = Depends(staff_checker)
) -> Any:
    return await ShopService().get_archived_shops(current_user)

@router.get("/demo-queue", response_model=List[ShopRead])
async def read_demo_queue(
    current_user: User = Depends(staff_checker)
) -> Any:
    return await ShopService().get_demo_queue(current_user)

@router.get("/", response_model=List[ShopRead])
async def read_shops(
    skip: int = 0,
    limit: Optional[int] = None,
    pipeline_stage: Optional[MasterPipelineStage] = None,
    owner_id: Optional[PydanticObjectId] = None,
    exclude_leads: bool = Query(False),
    current_user: User = Depends(staff_checker)
) -> Any:
    return await ShopService().list_shops(current_user, skip, limit, pipeline_stage, owner_id, exclude_leads)

@router.get("/suggest-pm")
async def suggest_pm(
    current_user: User = Depends(staff_checker)
) -> Any:
    return await ShopService().suggest_least_busy_pm(current_user)

@router.get("/analytics/pm-pipeline")
async def read_pm_pipeline_analytics(
    current_user: User = Depends(staff_checker)
) -> Any:
    return await ShopService().get_pm_pipeline_analytics()

@router.get("/{shop_id}", response_model=ShopRead)
async def read_shop(
    shop_id: PydanticObjectId,
    current_user: User = Depends(staff_checker)
) -> Any:
    service = ShopService()
    shop = await service.get_shop(shop_id)
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    # Enrichment
    from app.modules.users.models import User as UserModel
    owner_name = None
    if shop.owner_id:
        u = await UserModel.get(shop.owner_id)
        owner_name = u.name if u else None
    
    shop_dict = shop.model_dump()
    shop_dict["id"] = shop.id
    shop_dict["owner_name"] = owner_name
    return shop_dict

@router.patch("/{shop_id}", response_model=ShopRead)
async def update_shop(
    shop_id: PydanticObjectId,
    shop_in: ShopUpdate,
    current_user: User = Depends(staff_checker)
) -> Any:
    return await ShopService().update_shop(shop_id, shop_in)

@router.post("/{shop_id}/accept", response_model=ShopRead)
async def accept_shop(
    shop_id: PydanticObjectId,
    current_user: User = Depends(staff_checker)
) -> Any:
    return await ShopService().accept_shop(shop_id, current_user)

@router.post("/{shop_id}/assign-pm", response_model=ShopRead)
async def assign_pm(
    shop_id: PydanticObjectId,
    body: AssignPMRequest,
    current_user: User = Depends(staff_checker)
) -> Any:
    return await ShopService().assign_pm(shop_id, body, current_user)

@router.post("/{shop_id}/auto-assign", response_model=ShopRead)
async def auto_assign_shop(
    shop_id: PydanticObjectId,
    current_user: User = Depends(staff_checker)
) -> Any:
    return await ShopService().auto_assign_shop(shop_id, current_user)

@router.post("/{shop_id}/schedule-demo", response_model=ShopRead)
async def schedule_demo(
    shop_id: PydanticObjectId,
    body: ScheduleDemoRequest,
    current_user: User = Depends(pm_checker)
) -> Any:
    return await ShopService().schedule_demo(shop_id, body, current_user)

@router.post("/{shop_id}/complete-demo", response_model=ShopRead)
async def complete_demo(
    shop_id: PydanticObjectId,
    current_user: User = Depends(pm_checker)
) -> Any:
    return await ShopService().complete_demo(shop_id, current_user)

@router.post("/{shop_id}/cancel-demo", response_model=ShopRead)
async def cancel_demo(
    shop_id: PydanticObjectId,
    current_user: User = Depends(pm_checker)
) -> Any:
    return await ShopService().cancel_demo(shop_id, current_user)

@router.post("/{shop_id}/approve", response_model=ClientRead)
async def approve_pipeline(
    shop_id: PydanticObjectId,
    current_user: User = Depends(staff_checker)
) -> Any:
    return await ShopService().approve_pipeline_entry(shop_id)

@router.delete("/{shop_id}", status_code=status.HTTP_200_OK)
async def archive_shop(
    shop_id: PydanticObjectId,
    current_user: User = Depends(staff_checker)
) -> Any:
    return await ShopService().archive_shop(shop_id, current_user)

@router.patch("/{shop_id}/unarchive", response_model=ShopRead)
async def unarchive_shop(
    shop_id: PydanticObjectId,
    current_user: User = Depends(staff_checker)
) -> Any:
    return await ShopService().unarchive_shop(shop_id, current_user)

@router.delete("/{shop_id}/hard-delete", status_code=status.HTTP_200_OK)
async def hard_delete_shop(
    shop_id: PydanticObjectId,
    current_user: User = Depends(admin_checker)
) -> Any:
    return await ShopService().hard_delete_shop(shop_id)

@router.post("/batch-delete")
async def batch_delete_shops(
    payload: dict,
    current_user: User = Depends(admin_checker)
):
    from app.modules.shops.models import Shop
    from beanie.operators import In
    try:
        ids = [PydanticObjectId(i) for i in payload.get("ids", []) if i]
        res = await Shop.find(In(Shop.id, ids)).delete()
        return {"message": f"Successfully deleted {res.deleted_count} leads"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/accepted/history")
async def read_accepted_leads_history(
    current_user: User = Depends(staff_checker)
) -> Any:
    return await ShopService().get_accepted_leads(current_user)

@router.get("/public/lookup/{phone}")
async def lookup_shop_by_phone(phone: str):
    import re
    # 1. Standardize incoming phone (digits only)
    clean_phone = re.sub(r"\D", "", phone)
    if len(clean_phone) < 10:
        return {"name": None}
    
    # 2. Resilient pattern: matches digits separated by any chars (spaces, dashes, etc.)
    flexible_pattern = "[^\\d]*" + "[^\\d]*".join(list(clean_phone)) + "[^\\d]*$"
    regex_query = re.compile(flexible_pattern, re.IGNORECASE)
    
    # Check Shops (Leads)
    from app.modules.shops.models import Shop
    shop = await Shop.find_one({"phone": regex_query}, Shop.is_deleted != True)
    if shop:
        return {"name": shop.name}
        
    # Check Clients (Active Organizations)
    from app.modules.clients.models import Client
    client = await Client.find_one({"phone": regex_query}, Client.is_deleted != True)
    if client:
        return {"name": client.organization or client.name}

    return {"name": None}

@router.get("/public/names")
async def get_all_shop_names(current_user: User = Depends(staff_checker)):
    from app.modules.shops.models import Shop
    # Unique active shop names sorted alphabetically
    shops = await Shop.find(Shop.is_deleted != True).to_list()
    names = sorted(list(set(s.name for s in shops if s.name)))
    return names
