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

    async def get_client(self, client_id: PydanticObjectId) -> Optional[Client]:
        return await Client.find_one(Client.id == client_id, Client.is_deleted == False)

    async def get_clients(
        self,
        skip: int = 0,
        limit: Optional[int] = None,
        search: str = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        include_inactive: bool = False,
        pm_id: PydanticObjectId = None,
        is_active: Optional[bool] = True,
        current_user: User = None,
        scoped_user_id: PydanticObjectId = None,
        **kwargs
    ) -> List[Client]:
        try:
            q = Client.find(Client.is_deleted == False)

            if scoped_user_id:
                q = q.find(Client.owner_id == scoped_user_id)
            
            if is_active is True:
                q = q.find(Client.is_active == True, Client.status == 'ACTIVE')
            elif is_active is False:
                q = q.find(Client.is_active == False)
            elif not include_inactive:
                q = q.find(Client.is_active == True, Client.status == 'ACTIVE')

            if current_user and current_user.role != UserRole.ADMIN:
                # Scoped view: Owner, PM, or via Billing link
                # bridge view: find clients associated with invoices created by current user
                billed_phones = await Bill.get_pymongo_collection().distinct(
                    "invoice_client_phone", 
                    {"created_by_id": current_user.id}
                )
                
                q = q.find(Or(
                    And(Client.owner_id == current_user.id, Client.is_active == True),
                    Client.pm_id == current_user.id,
                    In(Client.phone, billed_phones)
                ))

            if search:
                import re
                pattern = re.compile(f".*{re.escape(search.strip())}.*", re.IGNORECASE)
                q = q.find(Or(
                    {"name": pattern},
                    {"phone": pattern},
                    {"email": pattern},
                    {"organization": pattern}
                ))

            if pm_id:
                q = q.find(Client.pm_id == pm_id)

            # Sorting
            prefix = "-" if sort_order.lower() == "desc" else ""
            # MongoDB uses field names for sorting
            query = q.sort(f"{prefix}{sort_by}").skip(skip)
            if limit is not None:
                query = query.limit(limit)
            clients = await query.to_list()
            
            # Enrich with PM Name sequentially
            for c in clients:
                if c.pm_id:
                    pm = await User.get(c.pm_id)
                    c.pm_name = pm.name if pm else f"PM #{c.pm_id}"
            return clients
        except Exception as e:
            print(f"Error fetching clients: {e}")
            return []

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
                "pm_name": pm.name,
                "pm_email": pm.email,
                "active_client_count": count
            })
        return sorted(results, key=lambda x: x["active_client_count"])

    async def archive_client(self, client_id: PydanticObjectId, current_user: User):
        db_client = await self.get_client(client_id)
        if not db_client: raise HTTPException(status_code=404, detail="Not Found")
        db_client.status = "ARCHIVED"
        db_client.is_active = False
        await db_client.save()
        return {"detail": "Client successfully ARCHIVED."}

    async def refund_client(self, client_id: PydanticObjectId, current_user: User):
        # TODO: Implement MongoDB transactions for financial safety
        db_client = await self.get_client(client_id)
        if not db_client: raise HTTPException(status_code=404, detail="Not Found")
        db_client.status = "REFUNDED"
        db_client.is_active = False
        
        from app.modules.payments.models import Payment, PaymentStatus
        await Payment.find(Payment.client_id == client_id, Payment.status == PaymentStatus.VERIFIED).update(
            {"$set": {"status": PaymentStatus.REFUNDED}}
        )
        
        from app.modules.billing.models import Bill
        await Bill.find(Bill.client_id == client_id).update({"$set": {"invoice_status": "REFUNDED"}})
        
        await db_client.save()
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
        return db_client
