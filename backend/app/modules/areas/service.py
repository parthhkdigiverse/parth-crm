# backend/app/modules/areas/service.py
from typing import List, Optional
from beanie import PydanticObjectId
from beanie.operators import In
from fastapi import HTTPException
from app.modules.areas.models import Area
from app.modules.areas.schemas import AreaCreate
from app.modules.users.models import User, UserRole
from app.modules.shops.models import Shop 
from datetime import datetime, UTC

class AreaService:
    def __init__(self):
        # No db session needed in Beanie!
        pass

    async def get_areas(self, current_user: User, skip: int = 0, limit: int = 100):
        # Base query: non-archived areas
        # Import here so the enrich_area nested closure can always access In/Or
        from beanie.operators import Or, In
        find_query = Area.find(Area.is_archived != True)

        is_admin = "ADMIN" in str(current_user.role).upper()
        if is_admin:
            areas = await find_query.skip(skip).limit(limit).to_list()
        else:
            
            # Fetch implicitly assigned areas via Shop relationships
            shop_query = Shop.find(Or(
                Shop.owner_id == current_user.id,
                Shop.created_by_id == current_user.id,
                Shop.project_manager_id == current_user.id,
                In(Shop.assigned_owner_ids, [current_user.id]),
                In(Shop.assigned_user_ids, [current_user.id])
            ))
            user_shops = await shop_query.to_list()
            shop_area_ids = list(set([s.area_id for s in user_shops if getattr(s, 'area_id', None)]))

            # Sales/Telesales: Can see areas they are assigned to OR areas containing shops they own/manage
            areas = await Area.find(
                Area.is_archived != True,
                Or(
                    In(Area.assigned_user_ids, [current_user.id]),
                    In(Area.id, shop_area_ids)
                )
            ).skip(skip).limit(limit).to_list()

        import asyncio
        async def enrich_area(area):
            # Count only active (non-deleted, non-archived) shops for the main view
            area.shops_count = await Shop.find(Shop.area_id == area.id, Shop.is_deleted != True, Shop.is_archived != True).count()
            
            # Populate creator name
            if area.created_by_id:
                creator = await User.get(area.created_by_id)
                area.created_by_name = creator.name if creator else None
            else:
                area.created_by_name = None

            # Populate archived by name
            if area.is_archived and area.archived_by_id:
                archived_by = await User.get(area.archived_by_id)
                area.archived_by_name = archived_by.name if archived_by else None
            else:
                area.archived_by_name = None

            # Populate assigned users list for UI dropdowns/tables
            assigned_users = []
            if area.assigned_user_ids:
                users = await User.find(In(User.id, area.assigned_user_ids)).to_list()
                assigned_users = [
                    {"id": str(u.id), "name": u.name, "role": u.role.value if hasattr(u.role, 'value') else str(u.role)} 
                    for u in users
                ]
            area.assigned_users = assigned_users
            return area

        await asyncio.gather(*(enrich_area(area) for area in areas))
        return areas

    async def accept_area(self, area_id: PydanticObjectId, current_user: User):
        area = await Area.get(area_id)
        if not area:
            raise HTTPException(status_code=404, detail="Area not found")
            
        if current_user.id not in area.assigned_user_ids:
            raise HTTPException(status_code=403, detail="You are not assigned to this area.")
            
        area.assignment_status = "ACCEPTED"
        area.assigned_user_ids = [current_user.id]
        area.accepted_at = datetime.now(UTC)
        
        # Update child shops sequentially
        shops = await Shop.find(Shop.area_id == area.id).to_list()
        for shop in shops:
            shop.assignment_status = "ACCEPTED"
            shop.assigned_owner_ids = [current_user.id]
            shop.accepted_at = datetime.now(UTC)
            await shop.save()
        
        await area.save()
        
        area.shops_count = await Shop.find(Shop.area_id == area.id, Shop.is_deleted != True, Shop.is_archived != True).count()
        if area.archived_by_id:
            archived_by = await User.get(area.archived_by_id)
            area.archived_by_name = archived_by.name if archived_by else None
        else:
            area.archived_by_name = None
            
        assigned_users_out = [
            {"id": str(current_user.id), "name": current_user.name, "role": current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role)}
        ]
        area.assigned_users = assigned_users_out
        return area

    async def create_area(self, area_in: AreaCreate, current_user: User):
        area_dict = area_in.model_dump()
        area = Area(**area_dict)
        area.created_by_id = current_user.id
        
        # Auto-Assign if not Admin
        is_admin = "ADMIN" in str(current_user.role).upper()
        if not is_admin:
            area.assigned_user_ids = [current_user.id]
            area.assignment_status = "ACCEPTED"
            area.accepted_at = datetime.now(UTC)
            area.assigned_by_id = current_user.id
        
        await area.insert()
        
        area.shops_count = 0
        area.archived_by_name = None
        area.created_by_name = current_user.name
        
        assigned_users = []
        if area.assigned_user_ids:
            users = await User.find(In(User.id, area.assigned_user_ids)).to_list()
            assigned_users = [
                {"id": str(u.id), "name": u.name, "role": u.role.value if hasattr(u.role, 'value') else str(u.role)} 
                for u in users
            ]
        area.assigned_users = assigned_users
        return area

    async def update_area(self, area_id: PydanticObjectId, area_in):
        area = await Area.get(area_id)
        if not area:
            raise HTTPException(status_code=404, detail="Area not found")
        update_data = area_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(area, field, value)
        await area.save()
        
        area.shops_count = await Shop.find(Shop.area_id == area.id, Shop.is_deleted != True, Shop.is_archived != True).count()
        
        if area.archived_by_id:
            archived_by = await User.get(area.archived_by_id)
            area.archived_by_name = archived_by.name if archived_by else None
        else:
            area.archived_by_name = None
            
        assigned_users = []
        if area.assigned_user_ids:
            users = await User.find(In(User.id, area.assigned_user_ids)).to_list()
            assigned_users = [
                {"id": str(u.id), "name": u.name, "role": u.role.value if hasattr(u.role, 'value') else str(u.role)} 
                for u in users
            ]
        area.assigned_users = assigned_users
        return area

    async def assign_area(self, area_id: PydanticObjectId, user_ids: List[PydanticObjectId], current_user: User, shop_ids: List[PydanticObjectId] = None):
        if not user_ids:
            raise HTTPException(status_code=400, detail="At least one user must be selected for assignment.")
            
        area = await Area.get(area_id)
        if not area:
            raise HTTPException(status_code=404, detail="Area not found")
        
        users = await User.find(In(User.id, user_ids)).to_list()
        if not users or len(users) != len(user_ids):
            raise HTTPException(status_code=404, detail="One or more users not found")

        current_user_ids = set(area.assigned_user_ids)
        new_user_ids = set(user_ids)
        
        if len(new_user_ids) > 1 or new_user_ids != current_user_ids:
            area.assignment_status = "PENDING"
            area.assigned_by_id = current_user.id
            area.accepted_at = None

        primary_owner_id = user_ids[0]
        
        if shop_ids is not None:
            # Granular assignment: Update specific shops only
            shops_to_assign = await Shop.find(
                Shop.area_id == area_id,
                In(Shop.id, shop_ids)
            ).to_list()
            
            for shop in shops_to_assign:
                shop.owner_id = primary_owner_id
                shop.assigned_owner_ids = user_ids
                if len(new_user_ids) > 1 or new_user_ids != current_user_ids:
                    shop.assignment_status = "PENDING"
                    shop.assigned_by_id = current_user.id
                    shop.accepted_at = None
                await shop.save()
            
            # Update Area assignments
            for uid in user_ids:
                if uid not in area.assigned_user_ids:
                    area.assigned_user_ids.append(uid)
                    
            if not getattr(area, 'assigned_user_id', None):
                 area.assigned_user_id = primary_owner_id
                 
        else:
            # Full assignment: Update area and ALL shops
            area.assigned_user_id = primary_owner_id
            area.assigned_user_ids = user_ids
            
            all_shops = await Shop.find(Shop.area_id == area_id).to_list()
            for shop in all_shops:
                shop.owner_id = primary_owner_id
                shop.assigned_owner_ids = user_ids
                if len(new_user_ids) > 1 or new_user_ids != current_user_ids:
                    shop.assignment_status = "PENDING"
                    shop.assigned_by_id = current_user.id
                    shop.accepted_at = None
                await shop.save()
        
        await area.save()
        
        area.shops_count = await Shop.find(Shop.area_id == area.id, Shop.is_deleted != True, Shop.is_archived != True).count()
        
        if area.archived_by_id:
            archived_by = await User.get(area.archived_by_id)
            area.archived_by_name = archived_by.name if archived_by else None
        else:
            area.archived_by_name = None

        assigned_users_out = [
            {"id": str(u.id), "name": u.name, "role": u.role.value if hasattr(u.role, 'value') else str(u.role)} 
            for u in users
        ]
        area.assigned_users = assigned_users_out
        return area

    async def archive_area(self, area_id: PydanticObjectId, current_user: User):
        area = await Area.get(area_id)
        if not area:
            raise HTTPException(status_code=404, detail="Area not found")
        
        role_str = current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role)
        is_admin = "ADMIN" in str(current_user.role).upper()
        if not is_admin:
            if current_user.id not in area.assigned_user_ids:
                raise HTTPException(status_code=403, detail="Not authorized to archive this area")
        
        area.is_archived = True
        area.archived_by_id = current_user.id
        await area.save()

        # Update child shops
        await Shop.find(Shop.area_id == area_id).update(
            {"$set": {"is_archived": True, "archived_by_id": current_user.id}}
        )
        
        return {"detail": f"Area \"{area.name}\" and its shops have been archived"}

    async def get_archived_areas(self, current_user: User):
        find_query = Area.find(Area.is_archived == True)  # Intentional: archived list wants only explicitly archived docs

        role_str = current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role)
        is_admin = "ADMIN" in str(current_user.role).upper()
        if is_admin:
            areas = await find_query.to_list()
        else:
            from beanie.operators import Or
            areas = await Area.find(
                Area.is_archived == True,
                Or(
                    Area.archived_by_id == current_user.id,
                    In(Area.assigned_user_ids, [current_user.id])
                )
            ).to_list()

        import asyncio
        async def enrich_archived_area(area):
            # For archived areas, we count all shops (they will all be archived anyway)
            area.shops_count = await Shop.find(Shop.area_id == area.id).count()

            if area.archived_by_id:
                archived_by = await User.get(area.archived_by_id)
                area.archived_by_name = archived_by.name if archived_by else None
            else:
                area.archived_by_name = None

            if area.created_by_id:
                creator = await User.get(area.created_by_id)
                area.created_by_name = creator.name if creator else None
            else:
                area.created_by_name = None

            assigned_users = []
            if area.assigned_user_ids:
                users = await User.find(In(User.id, area.assigned_user_ids)).to_list()
                assigned_users = [
                    {"id": str(u.id), "name": u.name, "role": u.role.value if hasattr(u.role, 'value') else str(u.role)} 
                    for u in users
                ]
            area.assigned_users = assigned_users
            return area

        await asyncio.gather(*(enrich_archived_area(area) for area in areas))
        return areas

    async def unarchive_area(self, area_id: PydanticObjectId, current_user: User):
        area = await Area.get(area_id)
        if not area:
            raise HTTPException(status_code=404, detail="Area not found")
        
        role_str = current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role)
        is_admin = "ADMIN" in str(current_user.role).upper()
        if not is_admin:
            if area.archived_by_id != current_user.id and current_user.id not in area.assigned_user_ids:
                 raise HTTPException(status_code=403, detail="Not authorized to unarchive this area")
        
        area.is_archived = False
        area.archived_by_id = None
        await area.save()

        await Shop.find(Shop.area_id == area_id).update(
            {"$set": {"is_archived": False, "archived_by_id": None}}
        )
        
        area.shops_count = await Shop.find(Shop.area_id == area.id, Shop.is_deleted != True, Shop.is_archived != True).count()
        area.archived_by_name = None
        
        assigned_users = []
        if area.assigned_user_ids:
            users = await User.find(In(User.id, area.assigned_user_ids)).to_list()
            assigned_users = [
                {"id": str(u.id), "name": u.name, "role": u.role.value if hasattr(u.role, 'value') else str(u.role)} 
                for u in users
            ]
        area.assigned_users = assigned_users
        return area

    async def hard_delete_area(self, area_id: PydanticObjectId):
        area = await Area.get(area_id)
        if not area:
            raise HTTPException(status_code=404, detail="Area not found")
        
        from app.modules.settings.models import AppSetting
        policy = await AppSetting.find_one({"key": "delete_policy"})
        is_hard = policy and policy.value == "HARD"

        if is_hard:
            await Shop.find(Shop.area_id == area_id).delete()
            await area.delete()
        else:
            area.is_deleted = True
            await area.save()
            await Shop.find(Shop.area_id == area_id).update({"$set": {"is_deleted": True}})

        return {"detail": f"Area and associated shops {'permanently ' if is_hard else ''}deleted"}
