# backend/app/modules/clients/service.py
from typing import List, Optional, Dict, Any
from beanie import PydanticObjectId
from beanie.operators import In, Or, And
from fastapi import HTTPException, status, Request
from app.modules.clients.models import Client, ClientPMHistory
from app.modules.clients.schemas import ClientCreate, ClientUpdate
from app.modules.users.models import User, UserRole
from app.modules.billing.models import Bill
from app.utils.notify_helpers import create_notification
from datetime import datetime, UTC
import random

class ClientService:
    def __init__(self):
        # No db session needed in Beanie!
        pass

    async def get_client(self, client_id: PydanticObjectId, current_user: User = None) -> Optional[Client]:
        """Fetch a single client with RBAC checks."""
        client = await Client.find_one(Client.id == client_id, Client.is_deleted == False)
        if not client:
            return None
            
        if current_user and current_user.role != UserRole.ADMIN:
            # 1. Direct Owner or PM
            if client.owner_id == current_user.id or client.pm_id == current_user.id or client.referred_by_id == current_user.id:
                return client
                
            # 2. Invoice Bridge (Phone Match)
            billed_phones = await Bill.get_pymongo_collection().distinct(
                "invoice_client_phone", {"created_by_id": current_user.id}
            )
            if client.phone in billed_phones:
                return client
                
            # 3. Demo PM Bridge (via Shop)
            from app.modules.shops.models import Shop
            is_demo_pm = await Shop.find_one(
                Shop.client_id == client.id, 
                Shop.project_manager_id == current_user.id,
                Shop.is_deleted == False
            )
            if is_demo_pm:
                return client
                
            raise HTTPException(status_code=403, detail="Access denied to this client.")
            
        return client

    async def get_clients(
        self,
        skip: int = 0,
        limit: Optional[int] = None,
        search: str = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        include_inactive: bool = False,
        pm_id: PydanticObjectId = None,
        status: Optional[str] = "ACTIVE",
        current_user: User = None,
        scoped_user_id: PydanticObjectId = None,
        **kwargs
    ) -> tuple[List[Client], int]:
        try:
            # 1. Base Criteria
            criteria = [Client.is_deleted == False]
            
            # 2. Status Filters
            if status == "ALL":
                pass
            elif status == "ACTIVE":
                criteria.append(Client.status == "ACTIVE")
                # criteria.append(Client.is_active == True) # Relaxing this to see if it's the culprit
                if current_user and current_user.role != UserRole.ADMIN:
                    criteria.append({"archived_by_ids": {"$ne": current_user.id}})
            elif status == "REFUNDED":
                criteria.append(Client.status == "REFUNDED")
            elif status == "ARCHIVED":
                if current_user and current_user.role != UserRole.ADMIN:
                    criteria.append(Or(
                        Client.status == "ARCHIVED",
                        {"archived_by_ids": current_user.id}
                    ))
                else:
                    criteria.append(Client.status == "ARCHIVED")
            else:
                criteria.append(Client.status == "ACTIVE")

            # 3. Role-Based Access Control (RBAC)
            if current_user and current_user.role != UserRole.ADMIN:
                from app.modules.shops.models import Shop
                billed_phones = await Bill.get_pymongo_collection().distinct(
                    "invoice_client_phone", 
                    {"created_by_id": current_user.id}
                )
                demo_shop_client_ids = await Shop.get_pymongo_collection().distinct(
                    "client_id", 
                    {"project_manager_id": current_user.id, "is_deleted": False}
                )
                managed_client_ids = [PydanticObjectId(cid) for cid in demo_shop_client_ids if cid]
                
                criteria.append(Or(
                    Client.owner_id == current_user.id,
                    Client.pm_id == current_user.id,
                    In(Client.phone, billed_phones),
                    In(Client.id, managed_client_ids)
                ))

            # 4. Search & Filters
            if search:
                import re
                pattern = re.compile(f".*{re.escape(search.strip())}.*", re.IGNORECASE)
                criteria.append(Or(
                    {"name": pattern},
                    {"phone": pattern},
                    {"email": pattern},
                    {"organization": pattern}
                ))

            if pm_id:
                criteria.append(Client.pm_id == pm_id)

            # 5. Execute Query
            q = Client.find(*criteria)
            total = await q.count()
            
            print(f"DEBUG [get_clients]: criteria={criteria}, skip={skip}, limit={limit}, status={status}, total_found={total}")
            
            prefix = "-" if sort_order.lower() == "desc" else ""
            query = q.sort(f"{prefix}{sort_by}").skip(skip)
            if limit:
                query = query.limit(limit)
                
            clients = await query.to_list()
            print(f"DEBUG [get_clients]: Successfully fetched {len(clients)} clients")
            
            # Enrich with PM Name in bulk for efficiency (removes N+1 query problem)
            pm_ids = {c.pm_id for c in clients if c.pm_id}
            if pm_ids:
                pms = await User.find(In(User.id, list(pm_ids))).to_list()
                pm_map = {p.id: p.name for p in pms}
                for c in clients:
                    if c.pm_id:
                        c.pm_name = pm_map.get(c.pm_id, f"PM #{c.pm_id}")

            # NEW: Enrich with Refund Eligibility (Bulk check latest invoices)
            client_ids = [c.id for c in clients]
            # Find latest invoice for each client in the current page
            latest_bills_cursor = Bill.get_pymongo_collection().aggregate([
                {"$match": {"client_id": {"$in": client_ids}}},
                {"$sort": {"created_at": -1}},
                {"$group": {"_id": "$client_id", "latest_created_at": {"$first": "$created_at"}}}
            ])
            latest_bills_map = {doc["_id"]: doc["latest_created_at"] async for doc in latest_bills_cursor}

            now = datetime.now(UTC)
            for c in clients:
                latest_inv_date = latest_bills_map.get(c.id)
                base_date = latest_inv_date or c.created_at
                days_passed = (now - base_date).days
                
                if days_passed > 10:
                    c.can_refund = False
                    c.refund_message = f"Refund window expired ({days_passed} days ago)"
                else:
                    c.can_refund = True
                    c.refund_message = f"Refund window active ({10 - days_passed} days left)"

            return clients, total
        except Exception as e:
            print(f"Error fetching clients: {e}")
            return [], 0

    async def create_client(self, client_in: ClientCreate, current_user: User, request: Request) -> Client:
        # Check duplicates
        if client_in.phone:
            exists = await Client.find_one(Client.phone == client_in.phone.strip(), Client.is_deleted == False)
            if exists:
                raise HTTPException(status_code=400, detail=f"Client with phone '{client_in.phone}' already exists.")
        
        if client_in.email:
            exists = await Client.find_one(Client.email == client_in.email.strip(), Client.is_deleted == False)
            if exists:
                raise HTTPException(status_code=400, detail=f"Client with email '{client_in.email}' already exists.")

        db_client = Client(**client_in.model_dump())
        db_client.owner_id = current_user.id
        
        # PM Auto-Assign
        assigned_pm = await self._get_auto_assign_pm()
        if assigned_pm:
            db_client.pm_id = assigned_pm.id
            db_client.pm_assigned_by_id = current_user.id
            # Embedding initial history on the document
            db_client.pm_history = [ClientPMHistory(pm_id=assigned_pm.id, assigned_at=datetime.now(UTC))]

        await db_client.insert()

        if assigned_pm:
            try:
                await create_notification(
                    assigned_pm.id,
                    "🧑‍💼 New Client Assigned",
                    f"Client '{db_client.name}' has been auto-assigned to you.",
                    actor_id=current_user.id
                )
            except Exception as e: print(f"Notif failed: {e}")

        # Reload for UI consistency
        fresh = await self.get_client(db_client.id)
        if fresh and fresh.pm_id:
            pm = await User.get(fresh.pm_id)
            fresh.pm_name = pm.name if pm else None
        return fresh

    async def update_client(self, client_id: PydanticObjectId, client_update: ClientUpdate, current_user: User, request: Request) -> Client:
        db_client = await self.get_client(client_id)
        if not db_client:
            raise HTTPException(status_code=404, detail="Client not found")

        update_data = client_update.model_dump(exclude_unset=True)
        pm_changed = "pm_id" in update_data and update_data["pm_id"] != db_client.pm_id
        
        if pm_changed:
            new_pm_id = update_data["pm_id"]
            if new_pm_id:
                new_pm = await User.get(new_pm_id)
                if not new_pm or not new_pm.is_active:
                    raise HTTPException(status_code=400, detail="Invalid PM")
                
                # Append to embedded history directly
                if not db_client.pm_history: db_client.pm_history = []
                db_client.pm_history.append(ClientPMHistory(pm_id=new_pm_id, assigned_at=datetime.now(UTC)))
                db_client.pm_assigned_by_id = current_user.id
                
                # Sync PM to Shop
                from app.modules.shops.models import Shop
                await Shop.find(Shop.client_id == db_client.id).update({"$set": {"project_manager_id": new_pm_id}})

        for key, value in update_data.items():
            setattr(db_client, key, value)
            
        await db_client.save()
        return db_client

    async def _get_auto_assign_pm(self) -> Optional[User]:
        active_pms = await User.find(
            In(User.role, [UserRole.PROJECT_MANAGER, UserRole.PROJECT_MANAGER_AND_SALES]),
            User.is_active == True,
            User.is_deleted == False
        ).to_list()
        
        if not active_pms:
            return await User.find_one(User.is_active == True)

        min_load = float('inf')
        least_loaded = []
        
        for pm in active_pms:
            count = await Client.find(Client.pm_id == pm.id, Client.is_active == True).count()
            if count < min_load:
                min_load = count
                least_loaded = [pm]
            elif count == min_load:
                least_loaded.append(pm)
        
        return random.choice(least_loaded) if least_loaded else None

    async def get_pm_workload(self) -> List[Dict]:
        active_pms = await User.find(
            In(User.role, [UserRole.PROJECT_MANAGER, UserRole.PROJECT_MANAGER_AND_SALES]),
            User.is_active == True,
            User.is_deleted == False
        ).to_list()
        
        results = []
        for pm in active_pms:
            count = await Client.find(Client.pm_id == pm.id, Client.is_active == True).count()
            results.append({
                "pm_id": str(pm.id),
                "pm_name": pm.name or pm.email or f"PM {str(pm.id)[:8]}",
                "pm_email": pm.email,
                "role": str(pm.role.value) if hasattr(pm.role, "value") else str(pm.role),
                "active_client_count": count
            })
        return sorted(results, key=lambda x: x["active_client_count"])

    async def archive_client(self, client_id: PydanticObjectId, current_user: User, request: Request = None):
        db_client = await self.get_client(client_id)
        if not db_client: raise HTTPException(status_code=404, detail="Not Found")
        
        if current_user.role == UserRole.ADMIN:
            # Global Archive
            db_client.status = "ARCHIVED"
            db_client.is_active = False
            await db_client.save()
            return {"detail": "Client successfully ARCHIVED globally."}
        else:
            # Personal Archive (for non-admins)
            if not db_client.archived_by_ids:
                db_client.archived_by_ids = []
            
            if current_user.id not in db_client.archived_by_ids:
                db_client.archived_by_ids.append(current_user.id)
                await db_client.save()
                return {"detail": "Client archived in your view."}
            else:
                return {"detail": "Client is already archived in your view."}

    async def refund_client(self, client_id: PydanticObjectId, current_user: User, request: Request = None):
        # TODO: Implement MongoDB transactions for financial safety
        db_client = await self.get_client(client_id)
        if not db_client: raise HTTPException(status_code=404, detail="Not Found")
        
        # Enforce 10-day refund window based on latest invoice
        from app.modules.billing.models import Bill
        latest_bill = await Bill.find(Bill.client_id == client_id).sort("-created_at").first_or_none()
        if latest_bill:
            days_since_creation = (datetime.now(UTC) - latest_bill.created_at).days
            if days_since_creation > 10:
                raise HTTPException(
                    status_code=400,
                    detail=f"Refund window expired. This client's latest invoice was created {days_since_creation} days ago (Max: 10 days)."
                )
        else:
            # If no invoice exists, maybe check client creation?
            days_since_client_creation = (datetime.now(UTC) - db_client.created_at).days
            if days_since_client_creation > 10:
                raise HTTPException(
                    status_code=400,
                    detail=f"Refund window expired. Client was created {days_since_client_creation} days ago (Max: 10 days)."
                )

        db_client.status = "REFUNDED"
        db_client.is_active = False
        
        from app.modules.payments.models import Payment, PaymentStatus
        await Payment.find(Payment.client_id == client_id, Payment.status == PaymentStatus.VERIFIED).update(
            {"$set": {"status": PaymentStatus.REFUNDED}}
        )
        
        from app.modules.billing.models import Bill
        await Bill.find(Bill.client_id == client_id).update({"$set": {"invoice_status": "REFUNDED", "status": "REFUNDED"}})
        
        # Archive associated Lead/Shop
        from app.modules.shops.models import Shop
        await Shop.find(Shop.client_id == client_id, Shop.is_deleted == False).update(
            {"$set": {"is_archived": True, "archived_by_id": current_user.id}}
        )
        
        await db_client.save()

        # Activity Log
        try:
            from app.modules.activity_logs.service import ActivityLogger
            from app.modules.activity_logs.models import ActionType, EntityType
            await ActivityLogger().log_activity(
                user_id=current_user.id,
                user_role=current_user.role,
                action=ActionType.STATUS_CHANGE,
                entity_type=EntityType.CLIENT,
                entity_id=client_id,
                new_data={"status": "REFUNDED", "archived_linked_shops": True},
                request=request
            )
        except Exception as log_err:
            print(f"[RefundClient] Activity log failed: {log_err}")

        return {"detail": "Client marked as REFUNDED. Revenue and metrics updated."}

    async def assign_pm(self, client_id: PydanticObjectId, pm_id: PydanticObjectId, current_user: User, request: Request):
        db_client = await self.get_client(client_id)
        if not db_client: raise HTTPException(status_code=404, detail="Not Found")
        
        pm = await User.get(pm_id)
        if not pm or not pm.is_active:
             raise HTTPException(status_code=400, detail="Invalid PM")

        if db_client.pm_id != pm_id:
            if not db_client.pm_history: db_client.pm_history = []
            db_client.pm_history.append(ClientPMHistory(pm_id=pm_id, assigned_at=datetime.now(UTC)))
            db_client.pm_id = pm_id
            db_client.pm_assigned_by_id = current_user.id
            await db_client.save()
        
        # Enrich with name for UI
        pm = await User.get(pm_id)
        if pm:
            db_client.pm_name = pm.name
            
        return db_client
