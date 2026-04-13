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
        from beanie.operators import Or, In
        from bson import ObjectId
        
        # 1. Evaluate the Admin check
        role_str = str(current_user.role).upper()
        is_admin = "ADMIN" in role_str or "USERROLE.ADMIN" in role_str
        
        # 2. Setup the query
        find_query = Area.find(
            Area.is_archived == False,
            Area.is_deleted == False
        )
        
        # Debug info
        base_count = await find_query.count()
        print("\n" + "="*50)
        print(f"🕵️ DEBUG: Is Admin?  = {is_admin}")
        print(f"🕵️ DEBUG: User ID    = {current_user.id}")
        print(f"🕵️ DEBUG: Areas in DB= {base_count}")
        print("="*50 + "\n")

        if is_admin:
            areas = await find_query.skip(skip).limit(limit).to_list()
        else:
            # Build both ObjectId and string versions of the user's ID for
            # type-safe matching against legacy and new documents
            try:
                user_oid = ObjectId(str(current_user.id))
            except Exception:
                user_oid = current_user.id
            user_str = str(current_user.id)

            # Fetch implicitly assigned areas via Shop relationships (type-safe)
            user_shop_filter = {
                "$or": [
                    {"owner_id": user_oid},
                    {"owner_id": user_str},
                    {"created_by_id": user_oid},
                    {"created_by_id": user_str},
                    {"project_manager_id": user_oid},
                    {"project_manager_id": user_str},
                    {"assigned_owner_ids": {"$in": [user_oid, user_str]}},
                    {"assigned_user_ids": {"$in": [user_oid, user_str]}},
                ]
            }
            user_shops = await Shop.find(user_shop_filter).to_list()
            
            # Collect all area_ids from shops assigned to this user (both ObjectId and str)
            raw_area_ids = [s.area_id for s in user_shops if getattr(s, 'area_id', None)]
            shop_area_obj_ids = []
            for aid in raw_area_ids:
                try:
                    shop_area_obj_ids.append(ObjectId(str(aid)))
                except Exception:
                    pass
            shop_area_obj_ids = list(set(shop_area_obj_ids))
            shop_area_str_ids = list(set([str(aid) for aid in raw_area_ids]))

            print(f"🕵️ DEBUG: shops found for user = {len(user_shops)}")
            print(f"🕵️ DEBUG: shop_area_ids        = {shop_area_obj_ids}")

            # Type-safe area filter: match both ObjectId and string stored IDs
            area_filter = {
                "$and": [
                    {"is_archived": {"$nin": [True, "t", "true", "1"]}},
                    {"is_deleted": {"$nin": [True, "t", "true", "1"]}},
                    {
                        "$or": [
                            # Direct assignment by user ID (both formats)
                            {"assigned_user_ids": {"$in": [user_oid, user_str]}},
                            {"assigned_user_id": {"$in": [user_oid, user_str]}},
                            # Area contains shops assigned to this user
                            {"_id": {"$in": shop_area_obj_ids}} if shop_area_obj_ids else {"_id": {"$in": []}},
                        ]
                    }
                ]
            }
            areas = await Area.find(area_filter).skip(skip).limit(limit).to_list()

            print(f"🕵️ DEBUG: areas found for user = {len(areas)}")
            print("="*50 + "\n")

        import asyncio

        async def enrich_area(area):
            try:
                # Count only active (non-deleted, non-archived) shops for the main view
                area.shops_count = await Shop.find(
            {
                "$or": [
                    {"area_id": area.id}, 
                    {"area_id": str(area.id)}
                ]
            },
            Shop.is_archived == False,
            Shop.is_deleted == False
        ).count()
                
                # Populate creator name
                if area.created_by_id:
                    creator = await User.get(area.created_by_id)
                    area.created_by_name = creator.name if creator else "Data Error"
                else:
                    area.created_by_name = None

                # Populate archived by name
                if area.is_archived and area.archived_by_id:
                    archived_by = await User.get(area.archived_by_id)
                    area.archived_by_name = archived_by.name if archived_by else "Data Error"
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
                elif getattr(area, 'assigned_user_id', None):
                    try:
                        u = await User.get(area.assigned_user_id)
                        if u:
                            assigned_users = [
                                {"id": str(u.id), "name": u.name, "role": u.role.value if hasattr(u.role, 'value') else str(u.role)} 
                            ]
                    except Exception as fallbackError:
                        print(f"Fallback User Get Error: {fallbackError}")
                
                area.assigned_users = assigned_users
            except Exception:
                area.shops_count = 0
                area.created_by_name = "Data Error"
                area.archived_by_name = "Data Error"
                area.assigned_users = []
            return area

        await asyncio.gather(*(enrich_area(area) for area in areas))
        return areas

    async def accept_area(self, area_id: PydanticObjectId, current_user: User):
        area = await Area.get(area_id)
        if not area:
            raise HTTPException(status_code=404, detail="Area not found")
            
        if str(current_user.id) not in [str(uid) for uid in area.assigned_user_ids]:
            raise HTTPException(status_code=403, detail="You are not assigned to this area.")
            
        area.assignment_status = "ACCEPTED"
        area.assigned_user_ids = [current_user.id]
        area.accepted_at = datetime.now(UTC)
        
        # Update child shops sequentially – make query type-safe for both stored formats
        from bson import ObjectId as BsonObjectId
        try:
            area_oid = BsonObjectId(str(area.id))
        except Exception:
            area_oid = area.id
        shops = await Shop.find({"$or": [
            {"area_id": area_oid},
            {"area_id": str(area.id)}
        ]}).to_list()
        for shop in shops:
            shop.assignment_status = "ACCEPTED"
            # Update BOTH id lists so the kanban card shows the correct assignee
            shop.assigned_owner_ids = [current_user.id]
            shop.assigned_user_ids = [current_user.id]
            shop.accepted_at = datetime.now(UTC)
            await shop.save()
        
        await area.save()
        
        area.shops_count = await Shop.find(
            {
                "$or": [
                    {"area_id": area.id}, 
                    {"area_id": str(area.id)}
                ]
            },
            Shop.is_archived == False,
            Shop.is_deleted == False
        ).count()
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
        
        area.shops_count = await Shop.find(
            {
                "$or": [
                    {"area_id": area.id}, 
                    {"area_id": str(area.id)}
                ]
            },
            Shop.is_archived == False,
            Shop.is_deleted == False
        ).count()
        
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
        
        from bson import ObjectId
        
        # Normalize all incoming IDs to PydanticObjectId for consistent MongoDB storage
        # This prevents type mismatch bugs where some docs store ObjectId and others store strings
        normalized_user_ids = []
        for uid in user_ids:
            try:
                normalized_user_ids.append(PydanticObjectId(str(uid)))
            except Exception:
                normalized_user_ids.append(uid)
        user_ids = normalized_user_ids
        
        # Cast to bson ObjectId for querying (Beanie In() needs this)
        user_obj_ids = [ObjectId(str(uid)) for uid in user_ids]
        
        users = await User.find(In(User.id, user_obj_ids)).to_list()
        if not users or len(users) != len(user_ids):
            raise HTTPException(status_code=404, detail="One or more users not found")

        current_user_ids = set(str(x) for x in area.assigned_user_ids)
        new_user_ids_str = set(str(x) for x in user_ids)
        
        # Determine if we need to reset acceptance status
        status_change = len(user_ids) > 1 or new_user_ids_str != current_user_ids

        primary_owner_id = user_ids[0]
        
        # Query for shops: handle both string and ObjectId formats defensively
        area_filter = {"$or": [{"area_id": area_id}, {"area_id": str(area_id)}]}
        
        if shop_ids is not None:
            shop_obj_ids = [ObjectId(sid) if isinstance(sid, str) else sid for sid in shop_ids]
            # Granular assignment: Update specific shops only
            shops_to_assign = await Shop.find(
                area_filter,
                In(Shop.id, shop_obj_ids)
            ).to_list()
            
            for shop in shops_to_assign:
                shop.owner_id = primary_owner_id
                shop.assigned_user_ids = user_ids
                shop.assigned_owner_ids = user_ids # consistency
                if status_change:
                    shop.assignment_status = "PENDING"
                    shop.assigned_by_id = current_user.id
                    shop.accepted_at = None
                await shop.save()
            
            # Update Area assignments: use normalized user_ids list
            area.assigned_user_ids = user_ids
            area.assigned_user_id = primary_owner_id
                     
        else:
            # Full assignment: Update area and ALL shops
            area.assigned_user_id = primary_owner_id
            area.assigned_user_ids = user_ids
            
            all_shops = await Shop.find(area_filter).to_list()
            for shop in all_shops:
                shop.owner_id = primary_owner_id
                shop.assigned_user_ids = user_ids
                shop.assigned_owner_ids = user_ids # consistency
                if status_change:
                    shop.assignment_status = "PENDING"
                    shop.assigned_by_id = current_user.id
                    shop.accepted_at = None
                await shop.save()
        
        if status_change:
            area.assignment_status = "PENDING"
            area.assigned_by_id = current_user.id
            area.accepted_at = None

        await area.save()
        
        area.shops_count = await Shop.find(
            {
                "$or": [
                    {"area_id": area.id}, 
                    {"area_id": str(area.id)}
                ]
            },
            Shop.is_archived == False,
            Shop.is_deleted == False
        ).count()
        
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
        await Shop.find({"area_id": str(area_id)}).update(
            {"$set": {"is_archived": True, "archived_by_id": current_user.id}}
        )
        
        return {"detail": f"Area \"{area.name}\" and its shops have been archived"}

    async def get_archived_areas(self, current_user: User):
        find_query = Area.find({"is_archived": {"$in": [True, "t", "true", "1"]}})  # Intentional: archived list wants only explicitly archived docs

        role_str = current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role)
        is_admin = "ADMIN" in str(current_user.role).upper()
        if is_admin:
            areas = await find_query.to_list()
        else:
            from beanie.operators import Or
            areas = await Area.find(
                {"is_archived": {"$in": [True, "t", "true", "1"]}},
                Or(
                    Area.archived_by_id == current_user.id,
                    In(Area.assigned_user_ids, [current_user.id])
                )
            ).to_list()

        import asyncio
        async def enrich_archived_area(area):
            try:
                # For archived areas, we count all shops (they will all be archived anyway)
                area.shops_count = await Shop.find({
                    "$or": [
                        {"area_id": area.id}, 
                        {"area_id": str(area.id)}
                    ]
                }).count()

                if area.archived_by_id:
                    archived_by = await User.get(area.archived_by_id)
                    area.archived_by_name = archived_by.name if archived_by else "Data Error"
                else:
                    area.archived_by_name = None

                if area.created_by_id:
                    creator = await User.get(area.created_by_id)
                    area.created_by_name = creator.name if creator else "Data Error"
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
            except Exception:
                area.shops_count = 0
                area.created_by_name = "Data Error"
                area.archived_by_name = "Data Error"
                area.assigned_users = []
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

        await Shop.find({"area_id": str(area_id)}).update(
            {"$set": {"is_archived": False, "archived_by_id": None}}
        )
        
        area.shops_count = await Shop.find(
            {
                "$or": [
                    {"area_id": area.id}, 
                    {"area_id": str(area.id)}
                ]
            },
            Shop.is_archived == False,
            Shop.is_deleted == False
        ).count()
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
            await Shop.find({"area_id": str(area_id)}).delete()
            await area.delete()
        else:
            area.is_deleted = True
            await area.save()
            await Shop.find({"area_id": str(area_id)}).update({"$set": {"is_deleted": True}})

        return {"detail": f"Area and associated shops {'permanently ' if is_hard else ''}deleted"}
