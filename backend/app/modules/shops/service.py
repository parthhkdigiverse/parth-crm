# backend/app/modules/shops/service.py
from beanie import PydanticObjectId
from beanie.operators import In
from fastapi import HTTPException, status
from app.modules.shops.models import Shop
from app.core.enums import MasterPipelineStage, GlobalTaskStatus
from app.modules.shops.schemas import ShopCreate, ShopUpdate
from app.modules.clients.models import Client
from app.modules.users.models import User
from app.modules.notifications.models import Notification
from app.modules.areas.models import Area
from app.core.cache import get_or_set, invalidate
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# ── Cached Helpers (shared across ShopService methods) ───────────────────────
async def _get_user_map(user_ids: list) -> dict:
    """Fetch users by IDs, served from 90-second RAM cache."""
    if not user_ids: return {}
    cache_key = "user_map:" + ",".join(sorted(str(i) for i in user_ids))
    async def _fetch():
        users = await User.find(In(User.id, user_ids)).to_list()
        return {str(u.id): u.name for u in users}
    return await get_or_set(cache_key, _fetch, ttl_seconds=90)

async def _get_area_map(area_ids: list) -> dict:
    """Fetch areas by IDs, served from 5-minute RAM cache (areas rarely change)."""
    if not area_ids: return {}
    cache_key = "area_map:" + ",".join(sorted(str(i) for i in area_ids))
    async def _fetch():
        areas = await Area.find(In(Area.id, area_ids)).to_list()
        return {str(a.id): a.name for a in areas}
    return await get_or_set(cache_key, _fetch, ttl_seconds=300)
# ─────────────────────────────────────────────────────────────────────────────

class ShopService:
    @staticmethod
    async def create_shop(shop_in: ShopCreate, current_user: User):
        from app.modules.users.models import UserRole
        from datetime import datetime, UTC
        
        db_shop = Shop(**shop_in.model_dump())
        db_shop.created_by_id = current_user.id
        
        # Only assign a PM if explicitly provided during creation. Default to None.
        db_shop.project_manager_id = getattr(shop_in, 'project_manager_id', None)
        
        # Auto-Assign if not Admin
        if current_user.role != UserRole.ADMIN:
            db_shop.assigned_user_ids = [current_user.id]
            db_shop.assignment_status = "ACCEPTED"
            db_shop.accepted_at = datetime.now(UTC)
            db_shop.assigned_by_id = current_user.id
            
        await db_shop.insert()
        
        # Enrich for Read schema
        db_shop.created_by_name = current_user.name
        
        # Map assigned users for frontend UI
        db_shop.assigned_users = [
            {"id": str(current_user.id), "name": current_user.name, "role": str(current_user.role)}
        ] if current_user.role != UserRole.ADMIN else []
        
        return db_shop

    @staticmethod
    async def get_shop(shop_id: PydanticObjectId):
        shop = await Shop.find_one(Shop.id == shop_id, Shop.is_deleted != True)
        if not shop:
            raise HTTPException(status_code=404, detail="Shop not found")
        return shop

    @staticmethod
    async def list_shops(current_user: User, skip: int = 0, limit: Optional[int] = None, pipeline_stage: MasterPipelineStage = None, owner_id: PydanticObjectId = None, exclude_leads: bool = False):
        query = Shop.find(Shop.is_deleted != True)
        
        if pipeline_stage:
            query = query.find(Shop.pipeline_stage == pipeline_stage)
            
        if exclude_leads:
            query = query.find(Shop.pipeline_stage != MasterPipelineStage.LEAD)

        # If Admin, return all shops unless owner_id filter is applied
        if current_user.role != "ADMIN":
            from beanie.operators import In
            # Logic: Assigned owners or PMs (simplified for migration)
            query = query.find({"$or": [
                {"assigned_user_ids": current_user.id},
                {"project_manager_id": current_user.id}
            ]})
        elif owner_id:
            query = query.find(Shop.owner_id == owner_id)

        # Build query — only apply limit when explicitly provided
        executable_query = query.skip(skip)
        if limit is not None:
            executable_query = executable_query.limit(limit)
        results = await executable_query.to_list()
        
        # --- OPTIMIZATION: Cached bulk fetch of required users ---
        user_ids = set()
        for shop in results:
            if shop.owner_id: user_ids.add(shop.owner_id)
            if shop.project_manager_id: user_ids.add(shop.project_manager_id)
            if shop.created_by_id: user_ids.add(shop.created_by_id)
            for uid in getattr(shop, 'assigned_user_ids', []):
                if uid: user_ids.add(uid)
        
        user_map = await _get_user_map(list(user_ids))
        
        # Sequential enrichment for Shop attributes
        for shop in results:
            # 1. Owner Name
            if shop.owner_id:
                shop.owner_name = user_map.get(str(shop.owner_id), "Unassigned")
            else:
                shop.owner_name = "Unassigned"
            
            # 2. PM Name
            if shop.project_manager_id:
                shop.project_manager_name = user_map.get(str(shop.project_manager_id), "Unassigned")
                shop.pm_name = shop.project_manager_name
                shop.assigned_pm_name = shop.project_manager_name
            else:
                shop.project_manager_name = "Unassigned"
                shop.pm_name = "Unassigned"
                shop.assigned_pm_name = "Unassigned"

            # 3. Created By Name
            if shop.created_by_id:
                shop.created_by_name = user_map.get(str(shop.created_by_id), "System")
            else:
                shop.created_by_name = "System"

            # 4. Map assigned users
            shop.assigned_users = [
                {
                    "id": str(uid), 
                    "name": user_map.get(str(uid), "Unknown"), 
                    "role": "STAFF"
                }
                for uid in getattr(shop, 'assigned_user_ids', []) if uid
            ]
            
        return results

    @staticmethod
    async def list_kanban_shops(owner_id: PydanticObjectId = None, source: str = None):
        query = Shop.find(Shop.is_deleted != True)
        
        if owner_id:
            from beanie.operators import Or
            query = query.find(Or(
                Shop.owner_id == owner_id,
                Shop.project_manager_id == owner_id,
                Shop.created_by_id == owner_id,
                Shop.assigned_user_ids == owner_id
            ))
            
        if source and source not in {"ALL", "all"}:
            query = query.find(Shop.source == source)
            
        results = await query.to_list()
        
        kanban = {
            "LEAD": [], "PITCHING": [], "NEGOTIATION": [], "DELIVERY": [], "MAINTENANCE": []
        }
        
        # --- BULK FETCH ---
        user_ids = set()
        area_ids = set()
        for shop in results:
            if shop.owner_id: user_ids.add(shop.owner_id)
            if shop.project_manager_id: user_ids.add(shop.project_manager_id)
            if shop.created_by_id: user_ids.add(shop.created_by_id)
            if shop.area_id: area_ids.add(shop.area_id)
            for uid in getattr(shop, 'assigned_user_ids', []):
                if uid: user_ids.add(uid)

        from beanie.operators import In
        user_map = {}
        if user_ids:
            users = await User.find(In(User.id, list(user_ids))).to_list()
            user_map = {str(u.id): u.name for u in users}
            
        area_map = {}
        if area_ids:
            areas = await Area.find(In(Area.id, list(area_ids))).to_list()
            area_map = {str(a.id): a.name for a in areas}
        
        for shop in results:
            shop_data = shop.model_dump()
            shop_data["id"] = shop.id
            shop_data["owner_name"] = user_map.get(str(shop.owner_id), "Unassigned") if shop.owner_id else "Unassigned"
            shop_data["area_name"] = area_map.get(str(shop.area_id), "No Area Assigned") if shop.area_id else "No Area Assigned"
            shop_data["last_visitor_name"] = getattr(shop, "last_visitor_name", None)
            shop_data["last_visit_status"] = None 
            
            shop_data["assigned_users"] = [
                {
                    "id": str(uid), 
                    "name": user_map.get(str(uid), "Unknown"), 
                    "role": "STAFF"
                } 
                for uid in getattr(shop, 'assigned_user_ids', []) if uid
            ]
            
            stage_val = str(shop.pipeline_stage.value) if hasattr(shop.pipeline_stage, "value") else str(shop.pipeline_stage)
            if stage_val in kanban:
                kanban[stage_val].append(shop_data)
                
        return kanban


    @staticmethod
    async def update_shop(shop_id: PydanticObjectId, shop_in: ShopUpdate):
        db_shop = await ShopService.get_shop(shop_id)
        update_data = shop_in.model_dump(exclude_unset=True)
        
        # Auto-cancel pending demos if moving to DELIVERY (but not yet in DELIVERY)
        new_stage = update_data.get('pipeline_stage')
        if new_stage == MasterPipelineStage.DELIVERY and db_shop.pipeline_stage != MasterPipelineStage.DELIVERY:
            if db_shop.demo_scheduled_at:
                await ShopService._cancel_pending_demos(
                    db_shop, 
                    reason="System Auto-Canceled: Lead advanced directly to Delivery"
                )

        for field, value in update_data.items():
            setattr(db_shop, field, value)
        
        await db_shop.save()
        return db_shop

    # ── Pipeline Entry (Lead -> Delivery) ──
    @staticmethod
    async def approve_pipeline_entry(shop_id: PydanticObjectId):
        db_shop = await ShopService.get_shop(shop_id)
        
        if db_shop.pipeline_stage == MasterPipelineStage.DELIVERY:
            raise HTTPException(status_code=400, detail="Entry already approved and converted to project")
            
        # Check if client already exists with this phone
        existing_client = await Client.find_one(Client.phone == db_shop.phone)
        
        if existing_client:
            if db_shop.demo_scheduled_at:
                await ShopService._cancel_pending_demos(
                    db_shop, 
                    reason="System Auto-Canceled: Lead advanced directly to Delivery"
                )
            db_shop.pipeline_stage = MasterPipelineStage.DELIVERY
            db_shop.client_id = existing_client.id
            await db_shop.save()
            return existing_client

        # Create new client
        db_client = Client(
            name=db_shop.contact_person or db_shop.name,
            email=db_shop.email or f"converted_{db_shop.id}@srm.internal", 
            phone=db_shop.phone,
            organization=db_shop.name,
            owner_id=db_shop.owner_id
        )
        await db_client.insert()

        if db_shop.demo_scheduled_at:
            await ShopService._cancel_pending_demos(
                db_shop, 
                reason="System Auto-Canceled: Lead advanced directly to Delivery"
            )
        db_shop.pipeline_stage = MasterPipelineStage.DELIVERY
        db_shop.client_id = db_client.id
        await db_shop.save()
        return db_client

    @staticmethod
    async def archive_shop(shop_id: PydanticObjectId, current_user: User):
        db_shop = await ShopService.get_shop(shop_id)

        # Check permissions
        if current_user.role != "ADMIN":
            if current_user.id not in getattr(db_shop, 'assigned_user_ids', []):
                 raise HTTPException(status_code=403, detail="Not authorized to archive this shop")

        db_shop.is_deleted = True
        await db_shop.save()
        return {"detail": f"Shop \"{db_shop.name}\" has been archived"}

    # ── Archived Listing ──
    @staticmethod
    async def get_archived_shops(current_user: User):
        query = Shop.find(Shop.is_deleted == True)

        if current_user.role != "ADMIN":
            query = query.find({"assigned_user_ids": current_user.id})

        results = await query.to_list()
        
        # --- BULK FETCH ---
        user_ids = set()
        for shop in results:
            if shop.owner_id: user_ids.add(shop.owner_id)
            for uid in getattr(shop, 'assigned_user_ids', []):
                if uid: user_ids.add(uid)
        
        user_map = {}
        if user_ids:
            from beanie.operators import In
            users = await User.find(In(User.id, list(user_ids))).to_list()
            user_map = {str(u.id): u.name for u in users}
        
        shops = []
        for shop in results:
            shop_data = shop.model_dump()
            shop_data["id"] = shop.id
            shop_data["owner_name"] = user_map.get(str(shop.owner_id), "Unassigned") if shop.owner_id else "Unassigned"
            shop_data["area_name"] = shop.area_name
            shop_data["created_by_name"] = "System"
            shop_data["assigned_users"] = [
                {
                    "id": str(uid), 
                    "name": user_map.get(str(uid), "Unknown"), 
                    "role": "STAFF"
                } 
                for uid in getattr(shop, 'assigned_user_ids', []) if uid
            ]
            shops.append(shop_data)
        return shops

    # ── Unarchive ──
    @staticmethod
    async def unarchive_shop(shop_id: PydanticObjectId, current_user: User):
        db_shop = await Shop.get(shop_id)
        if not db_shop:
            raise HTTPException(status_code=404, detail="Shop not found")

        # Check permissions
        if current_user.role != "ADMIN":
            if current_user.id not in getattr(db_shop, 'assigned_user_ids', []):
                 raise HTTPException(status_code=403, detail="Not authorized to unarchive this shop")

        db_shop.is_deleted = False
        await db_shop.save()
        return db_shop

    # ── Hard Delete (Admin only) ──
    @staticmethod
    async def hard_delete_shop(shop_id: PydanticObjectId):
        db_shop = await Shop.get(shop_id)
        if not db_shop:
            raise HTTPException(status_code=404, detail="Shop not found")
        
        # Check if client already exists with this phone
        if db_shop.phone:
            client_exists = await Client.find_one(Client.phone == db_shop.phone)
            if client_exists:
                raise HTTPException(status_code=400, detail="Cannot delete shop that has been converted to a client")

        await db_shop.delete()
        return {"detail": "Shop permanently deleted"}

    # ── Accept Shop (Staff claims the shop) ──
    @staticmethod
    async def accept_shop(shop_id: PydanticObjectId, current_user: User):
        shop = await Shop.get(shop_id)
        if not shop:
            raise HTTPException(status_code=404, detail="Shop not found")
            
        if current_user.id not in getattr(shop, 'assigned_user_ids', []):
            raise HTTPException(status_code=403, detail="You are not assigned to this shop.")
            
        from datetime import datetime, UTC
        shop.assignment_status = "ACCEPTED"
        shop.assigned_user_ids = [current_user.id]
        shop.accepted_at = datetime.now(UTC)
        
        await shop.save()
        
        shop_data = shop.model_dump()
        shop_data["id"] = shop.id
        shop_data["owner_name"] = None
        shop_data["area_name"] = shop.area_name
        
        shop_data["assigned_users"] = [
            {"id": str(current_user.id), "name": current_user.name, "role": str(current_user.role)}
        ]
        return shop_data

    @staticmethod
    async def get_accepted_leads(current_user: User):
        from app.modules.users.models import UserRole
        from app.modules.visits.models import Visit

        is_admin = (current_user.role == UserRole.ADMIN)

        # For staff: only exclude leads visited by them; for admin: exclude any visit
        # We'll fetch the IDs of shops already visited to filter them out
        if is_admin:
            visited_shop_ids = await Visit.get_pymongo_collection().distinct("shop_id")
        else:
            visited_shop_ids = await Visit.get_pymongo_collection().distinct("shop_id", {"user_id": current_user.id})

        from beanie.operators import NotIn
        query = Shop.find(
            Shop.assignment_status == "ACCEPTED",
            Shop.pipeline_stage == MasterPipelineStage.LEAD,
            NotIn(Shop.id, visited_shop_ids),
            Shop.is_deleted == False
        )

        # Staff can only see their own assigned shops
        if not is_admin:
            query = query.find({"assigned_user_ids": current_user.id})

        results = await query.sort(-Shop.accepted_at).to_list()

        # --- BULK FETCH USERS ---
        needed_uids = set()
        for shop in results:
            if shop.assigned_user_ids:
                needed_uids.add(shop.assigned_user_ids[0])
        
        from beanie.operators import In
        user_objects_map = {}
        if needed_uids:
            users_list = await User.find(In(User.id, list(needed_uids))).to_list()
            user_objects_map = {u.id: u.name for u in users_list}

        history = []
        for shop in results:
            assigned_to_name = "Unknown"
            if shop.assigned_user_ids:
                assigned_to_name = user_objects_map.get(shop.assigned_user_ids[0], "Unknown")

            history.append({
                "shop_id": str(shop.id),
                "area_name": shop.area_name or "N/A",
                "shop_name": shop.name,
                "assigned_to_name": assigned_to_name,
                "assigned_by_name": "System", 
                "accepted_at": shop.accepted_at
            })
        return history

    # ── Assign PM ──
    @staticmethod
    async def assign_pm(shop_id: PydanticObjectId, body, current_user: User):
        from app.modules.users.models import UserRole
        shop = await Shop.find_one(Shop.id == shop_id, Shop.is_deleted != True)
        if not shop:
            raise HTTPException(status_code=404, detail="Shop not found")

        pm = await User.get(body.pm_id)
        if not pm:
            raise HTTPException(status_code=404, detail="User not found")

        shop.project_manager_id = body.pm_id
        shop.pipeline_stage = MasterPipelineStage.NEGOTIATION
        if body.demo_scheduled_at:
            shop.demo_scheduled_at = body.demo_scheduled_at
            shop.scheduled_by_id = current_user.id

        await shop.save()

        # Notify PM
        try:
            notif = Notification(
                user_id=body.pm_id,
                title=f"[Lead] New Lead Assigned: {shop.name}",
                message=f"You have been assigned as the Project Manager for lead '{shop.name}'."
            )
            await notif.insert()
        except Exception as e:
            print(f"Error creating lead assignment notification: {e}")

        shop_data = shop.model_dump()
        shop_data["id"] = shop.id
        shop_data["project_manager_name"] = pm.name
        return shop_data

    # ── Auto-Assign PM ──
    @staticmethod
    async def auto_assign_shop(shop_id: PydanticObjectId, current_user: User):
        from app.modules.users.models import UserRole
        from app.modules.projects.models import Project
        import random
        
        shop = await Shop.find_one(Shop.id == shop_id, Shop.is_deleted != True)
        if not shop:
            raise HTTPException(status_code=404, detail="Shop not found")

        # Fetch active PMs
        pms = await User.find(
            User.is_active == True,
            {"role": {"$in": [UserRole.PROJECT_MANAGER.value, UserRole.PROJECT_MANAGER_AND_SALES.value]}}
        ).to_list()
        
        if not pms:
            raise HTTPException(status_code=400, detail="No active Project Managers found to assign")

        pm_scores = {}
        for pm in pms:
            active_shops_count = await Shop.find(
                Shop.project_manager_id == pm.id,
                Shop.is_deleted != True,
                {"pipeline_stage": {"$in": [MasterPipelineStage.LEAD.value, MasterPipelineStage.PITCHING.value]}}
            ).count()
            
            active_projects_count = await Project.find(
                Project.pm_id == pm.id,
                {"status": {"$in": [GlobalTaskStatus.OPEN.value, GlobalTaskStatus.IN_PROGRESS.value]}}
            ).count()
            
            pm_scores[pm.id] = active_shops_count + active_projects_count
            
        min_score = min(pm_scores.values())
        tied_pms = [pm_id for pm_id, score in pm_scores.items() if score == min_score]
        
        selected_pm_id = random.choice(tied_pms)
        selected_pm = next((pm for pm in pms if pm.id == selected_pm_id), None)
        
        shop.project_manager_id = selected_pm_id
        shop.pipeline_stage = MasterPipelineStage.NEGOTIATION
        await shop.save()

        # Notify PM
        try:
            notif = Notification(
                user_id=selected_pm_id,
                title=f"[Lead] New Lead Assigned: {shop.name}",
                message=f"You have been auto-assigned as the Project Manager for lead '{shop.name}'."
            )
            await notif.insert()
        except Exception as e:
            print(f"Error creating lead auto-assignment notification: {e}")

        shop_data = shop.model_dump()
        shop_data["id"] = shop.id
        shop_data["project_manager_name"] = selected_pm.name
        return shop_data

    # ── Auto-Suggest PM with lowest workload ──
    @staticmethod
    async def suggest_least_busy_pm(current_user: User):
        from app.modules.users.models import UserRole
        from app.modules.projects.models import Project
        import random

        # Fetch active PMs
        pms = await User.find(
            User.is_active == True,
            {"role": {"$in": [UserRole.PROJECT_MANAGER.value, UserRole.PROJECT_MANAGER_AND_SALES.value]}}
        ).to_list()
        
        if not pms:
            raise HTTPException(status_code=400, detail="No active Project Managers found to suggest")

        pm_scores = {}
        for pm in pms:
            active_shops_count = await Shop.find(
                Shop.project_manager_id == pm.id,
                Shop.is_archived != True,
                {"pipeline_stage": {"$in": [MasterPipelineStage.LEAD.value, MasterPipelineStage.PITCHING.value]}}
            ).count()
            
            active_projects_count = await Project.find(
                Project.pm_id == pm.id,
                {"status": {"$in": [GlobalTaskStatus.OPEN.value, GlobalTaskStatus.IN_PROGRESS.value]}}
            ).count()
            
            pm_scores[pm.id] = active_shops_count + active_projects_count
            
        min_score = min(pm_scores.values())
        tied_pms = [pm_id for pm_id, score in pm_scores.items() if score == min_score]
        
        selected_pm_id = random.choice(tied_pms)
        selected_pm = next((pm for pm in pms if pm.id == selected_pm_id), None)
        
        return {
            "suggested_pm_id": str(selected_pm.id),
            "name": selected_pm.name
        }

    # ── Demo Operations ──
    @staticmethod
    async def complete_demo(shop_id: PydanticObjectId, current_user: User):
        from app.modules.visits.models import Visit, VisitStatus
        from app.modules.timetable.models import TimetableEvent
        from datetime import timedelta

        shop = await Shop.find_one(Shop.id == shop_id, Shop.is_deleted != True)
        if not shop:
            raise HTTPException(status_code=404, detail="Shop not found")

        demo_time = shop.demo_scheduled_at
        pm_id = shop.project_manager_id or (current_user.id if current_user else None)

        if demo_time and pm_id:
            archive_visit = Visit(
                shop_id=shop.id,
                user_id=pm_id,
                status=VisitStatus.COMPLETED,
                remarks="Product Demo Session Completed Successfully.",
                visit_date=demo_time
            )
            await archive_visit.insert()

        shop.demo_stage = (shop.demo_stage or 0) + 1
        shop.demo_scheduled_at = None 

        if shop.demo_stage == 1:
            shop.pipeline_stage = MasterPipelineStage.NEGOTIATION

        await shop.save()
        return shop

    @staticmethod
    async def _cancel_pending_demos(shop: Shop, reason: str = "Product Demo Session was Cancelled."):
        from app.modules.visits.models import Visit, VisitStatus
        demo_time = shop.demo_scheduled_at
        pm_id = shop.project_manager_id

        if demo_time and pm_id:
            archive_visit = Visit(
                shop_id=shop.id,
                user_id=pm_id,
                status=VisitStatus.CANCELLED,
                remarks=reason,
                visit_date=demo_time
            )
            await archive_visit.insert()

        shop.demo_scheduled_at = None
        # Other demo fields clearing...


    @staticmethod
    async def cancel_demo(shop_id: PydanticObjectId, current_user: User):
        shop = await Shop.find_one(Shop.id == shop_id, Shop.is_deleted == False)
        if not shop:
            raise HTTPException(status_code=404, detail="Shop not found")

        await ShopService._cancel_pending_demos(shop)
        await shop.save()
        return shop

    @staticmethod
    async def schedule_demo(shop_id: PydanticObjectId, payload, current_user: User):
        shop = await Shop.find_one(Shop.id == shop_id, Shop.is_deleted == False)
        if not shop:
            raise HTTPException(status_code=404, detail="Shop not found")

        shop.demo_scheduled_at = payload.scheduled_at
        shop.demo_title = payload.title
        shop.demo_type = payload.demo_type
        shop.demo_notes = payload.notes
        shop.scheduled_by_id = current_user.id

        if not shop.project_manager_id:
            shop.project_manager_id = current_user.id

        await shop.save()

        # Notify PM
        if shop.project_manager_id and shop.scheduled_by_id != shop.project_manager_id:
            try:
                notif = Notification(
                    user_id=shop.project_manager_id,
                    title=f"[Demo] Product Demo Scheduled: {shop.name}",
                    message=f"A product demo has been scheduled for '{shop.name}'."
                )
                await notif.insert()
            except Exception as e:
                print(f"Error creating demo schedule notification: {e}")

        return shop

    @staticmethod
    async def get_demo_queue(current_user: User):
        from app.modules.users.models import UserRole
        from app.modules.clients.models import Client as ClientModel

        query = Shop.find(
            Shop.is_deleted != True,
            Shop.project_manager_id != None
        )

        # Non-admin PMs only see their own queue
        if current_user.role not in [UserRole.ADMIN]:
            query = query.find(Shop.project_manager_id == current_user.id)

        results = await query.sort(-Shop.id).to_list()
        
        # --- BULK FETCH ---
        user_ids = set()
        area_ids = set()
        for shop in results:
            if shop.owner_id: user_ids.add(shop.owner_id)
            if shop.project_manager_id: user_ids.add(shop.project_manager_id)
            if shop.area_id: area_ids.add(shop.area_id)
            for uid in getattr(shop, 'assigned_user_ids', []):
                if uid: user_ids.add(uid)

        from beanie.operators import In
        user_map = {}
        if user_ids:
            users_list = await User.find(In(User.id, list(user_ids))).to_list()
            user_map = {str(u.id): u.name for u in users_list}
            
        area_map = {}
        if area_ids:
            areas_list = await Area.find(In(Area.id, list(area_ids))).to_list()
            area_map = {str(a.id): a.name for a in areas_list}

        shops = []
        for shop in results:
            shop_data = shop.model_dump()
            shop_data["id"] = shop.id
            shop_data["owner_name"] = user_map.get(str(shop.owner_id), "Unassigned") if shop.owner_id else "Unassigned"
            shop_data["area_name"] = area_map.get(str(shop.area_id), "No Area Assigned") if shop.area_id else "No Area Assigned"
            
            pm_name = user_map.get(str(shop.project_manager_id), "Unassigned") if shop.project_manager_id else "Unassigned"
            shop_data["project_manager_name"] = pm_name
            shop_data["assigned_pm_name"] = pm_name
            
            shop_data["created_by_name"] = "System"
            shop_data["scheduled_by_name"] = "System"
            shop_data["archived_by_name"] = "System"
            shop_data["last_visitor_name"] = getattr(shop, "last_visitor_name", None)
            
            shop_data["assigned_users"] = [
                {
                    "id": str(uid), 
                    "name": user_map.get(str(uid), "Unknown"), 
                    "role": "STAFF"
                }
                for uid in getattr(shop, 'assigned_user_ids', []) if uid
            ]
            shops.append(shop_data)
        return shops

    @staticmethod
    async def get_pm_pipeline_analytics():
        from app.core.enums import MasterPipelineStage
        
        # Use aggregation for efficiency
        pipeline = [
            {"$match": {"is_deleted": False, "project_manager_id": {"$ne": None}}},
            {"$lookup": {
                "from": "srm_users",
                "localField": "project_manager_id",
                "foreignField": "_id",
                "as": "pm"
            }},
            {"$unwind": "$pm"},
            {"$group": {
                "_id": {"$ifNull": ["$pm.name", "$pm.email"]},
                "in_demo": {"$sum": {"$cond": [{"$eq": ["$pipeline_stage", "NEGOTIATION"]}, 1, 0]}},
                "meeting_set": {"$sum": {"$cond": [{"$eq": ["$pipeline_stage", "PITCHING"]}, 1, 0]}},
                "converted": {"$sum": {"$cond": [{"$eq": ["$pipeline_stage", "DELIVERY"]}, 1, 0]}}
            }},
            {"$project": {
                "pm_name": "$_id",
                "in_demo": 1,
                "meeting_set": 1,
                "converted": 1,
                "_id": 0
            }},
            {"$sort": {"pm_name": 1}}
        ]
        
        results = await Shop.get_pymongo_collection().aggregate(pipeline).to_list(length=None)
        return results
