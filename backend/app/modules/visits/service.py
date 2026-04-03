# backend/app/modules/visits/service.py
import os
import shutil
from pathlib import Path
from beanie import PydanticObjectId
from beanie.operators import In, Or, And
from fastapi import HTTPException, UploadFile, Request
from datetime import datetime, UTC, timedelta
from typing import List, Optional

from app.modules.visits.models import Visit, VisitStatus
from app.modules.visits.schemas import VisitCreate, VisitUpdate
from app.modules.users.models import User, UserRole
from app.modules.shops.models import Shop
from app.modules.activity_logs.service import ActivityLogger
from app.modules.activity_logs.models import ActionType, EntityType
from app.core.enums import MasterPipelineStage

BASE_DIR = Path(__file__).parent.parent.parent.parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads" / "visits"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

class VisitService:
    def __init__(self):
        # ActivityLogger now expects Beanie-ready async operations
        self.activity_logger = ActivityLogger()

    async def _populate_visit_metadata(self, visit: Visit):
        """Sequential lookup for shop and user names (NoSQL join replacement)."""
        if visit.shop_id:
            shop = await Shop.get(visit.shop_id)
            if shop:
                visit.shop_name = shop.name
                visit.shop_status = str(shop.pipeline_stage.value) if hasattr(shop.pipeline_stage, "value") else str(shop.pipeline_stage)
                visit.shop_demo_stage = shop.demo_stage
                
                # Project Manager Name lookup
                if shop.project_manager_id:
                    pm = await User.get(shop.project_manager_id)
                    visit.project_manager_name = pm.name if pm else "Unknown PM"

                # Area lookup for fully qualified shop info
                from app.modules.areas.models import Area
                if shop.area_id:
                    area = await Area.get(shop.area_id)
                    if area:
                        visit.area_name = area.name
        
        if visit.user_id:
            user = await User.get(visit.user_id)
            if user:
                visit.user_name = user.name or user.email
        return visit

    async def get_visit(self, visit_id: PydanticObjectId) -> Optional[Visit]:
        """Fetches a single visit with enriched metadata."""
        visit = await Visit.find_one(Visit.id == visit_id, Visit.is_deleted == False)
        if visit:
            await self._populate_visit_metadata(visit)
        return visit

    async def get_visits(
        self, 
        skip: int = 0, 
        limit: Optional[int] = None, 
        current_user: User = None, 
        shop_id: Optional[PydanticObjectId] = None, 
        user_id: Optional[PydanticObjectId] = None,
        area_id: Optional[PydanticObjectId] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Visit]:
        """Fetches filtered visits with RBAC enforcement and manual joins."""
        q = Visit.find(Visit.is_deleted == False)
        
        if shop_id:
            q = q.find(Visit.shop_id == shop_id)
            # Override: show all visits for a specific shop regardless of user filter
            if current_user and current_user.role != UserRole.ADMIN:
                user_id = None 
        
        if user_id:
            q = q.find(Visit.user_id == user_id)
            
        if area_id and str(area_id).upper() != "ALL":
            raw_ids = await Shop.get_pymongo_collection().distinct("_id", {"area_id": PydanticObjectId(area_id)})
            shop_ids_in_area = [PydanticObjectId(rid) for rid in raw_ids if rid]
            q = q.find(In(Visit.shop_id, shop_ids_in_area))
            
        if status and status.upper() != "ALL":
            q = q.find(Visit.status == status.upper())
            
        if start_date:
            q = q.find(Visit.visit_date >= start_date)
        if end_date:
            q = q.find(Visit.visit_date <= (end_date + timedelta(days=1)))

        # --- SECURITY ENFORCEMENT (RBAC) ---
        if current_user and current_user.role != UserRole.ADMIN and not shop_id:
            raw_owned_ids = await Shop.get_pymongo_collection().distinct("_id", {
                "$or": [
                    {"owner_id": current_user.id},
                    {"assigned_owner_ids": {"$in": [current_user.id]}}
                ]
            })
            owned_shop_ids = [PydanticObjectId(rid) for rid in raw_owned_ids if rid]
            
            q = q.find(
                Or(
                    Visit.user_id == current_user.id,
                    In(Visit.shop_id, owned_shop_ids)

                )
            )

        # Build query — only apply limit when explicitly provided
        query = q.sort("-visit_date").skip(skip)
        if limit is not None:
            query = query.limit(limit)
        visits = await query.to_list()
        for v in visits:
            await self._populate_visit_metadata(v)
        return visits

    async def create_visit(
        self, 
        visit_in: VisitCreate, 
        current_user: User, 
        request: Request, 
        storefront_photo: Optional[UploadFile] = None, 
        selfie_photo: Optional[UploadFile] = None
    ):
        """Creates a visit, handles file uploads, and updates shop pipeline state."""
        shop = await Shop.get(visit_in.shop_id)
        if not shop:
            raise HTTPException(status_code=404, detail="Shop not found")
            
        visit_dict = visit_in.model_dump()
        visit = Visit(**visit_dict, user_id=current_user.id)

        # Handle Photo Uploads
        timestamp = int(datetime.now(UTC).timestamp())
        
        if storefront_photo:
            try:
                ext = storefront_photo.filename.split(".")[-1]
                fname = f"visit_{visit_in.shop_id}_{current_user.id}_store_{timestamp}.{ext}"
                file_path = UPLOAD_DIR / fname
                with file_path.open("wb") as buffer:
                    shutil.copyfileobj(storefront_photo.file, buffer)
                visit.storefront_photo_url = f"/backend_static/uploads/visits/{fname}"
                visit.photo_url = visit.storefront_photo_url
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Storefront upload failed: {str(e)}")

        if selfie_photo:
            try:
                ext = selfie_photo.filename.split(".")[-1]
                fname = f"visit_{visit_in.shop_id}_{current_user.id}_selfie_{timestamp}.{ext}"
                file_path = UPLOAD_DIR / fname
                with file_path.open("wb") as buffer:
                    shutil.copyfileobj(selfie_photo.file, buffer)
                visit.selfie_photo_url = f"/backend_static/uploads/visits/{fname}"
                if not visit.photo_url:
                    visit.photo_url = visit.selfie_photo_url
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Selfie upload failed: {str(e)}")

        await visit.insert()

        # --- Automated Shop Pipeline Transitions ---
        v_status = str(visit.status).replace('VisitStatus.', '')
        
        if v_status == "ACCEPT":
            shop.pipeline_stage = MasterPipelineStage.DELIVERY
            from app.modules.shops.service import ShopService
            await ShopService._cancel_pending_demos(
                shop, 
                current_user=current_user,
                reason="System Auto-Canceled: Advanced to Delivery via Visit"
            )
        elif v_status in ["SATISFIED", "TAKE_TIME_TO_THINK", "OTHER"]:
            if shop.pipeline_stage == MasterPipelineStage.LEAD or shop.pipeline_stage is None:
                shop.pipeline_stage = MasterPipelineStage.PITCHING
        elif v_status == "DECLINE":
            shop.is_deleted = True
            shop.assignment_status = "UNASSIGNED"

        await shop.save()

        # Activity Logging
        await self.activity_logger.log_activity(
            user_id=current_user.id,
            user_role=current_user.role,
            action=ActionType.CREATE,
            entity_type=EntityType.VISIT,
            entity_id=visit.id,
            new_data=visit_in.model_dump(mode='json'),
            request=request
        )
        
        return await self._populate_visit_metadata(visit)

    async def update_visit(self, visit_id: PydanticObjectId, visit_in: VisitUpdate, current_user: User, request: Request):
        """Updates visit notes/status and logs the change."""
        visit = await Visit.get(visit_id)
        if not visit:
            raise HTTPException(status_code=404, detail="Visit not found")

        old_data = {"status": str(visit.status), "remarks": visit.remarks}
        
        update_data = visit_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(visit, field, value)

        await visit.save()

        await self.activity_logger.log_activity(
            user_id=current_user.id,
            user_role=current_user.role,
            action=ActionType.UPDATE,
            entity_type=EntityType.VISIT,
            entity_id=visit.id,
            old_data=old_data,
            new_data=update_data,
            request=request
        )
        return await self._populate_visit_metadata(visit)
