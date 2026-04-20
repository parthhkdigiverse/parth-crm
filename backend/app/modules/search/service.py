# backend/app/modules/search/service.py
from typing import List, Dict, Any, Optional
from beanie import PydanticObjectId
from beanie.operators import In, Or, And, RegEx

from app.modules.clients.models import Client
from app.modules.issues.models import Issue
from app.modules.projects.models import Project
from app.modules.shops.models import Shop
from app.modules.users.models import User
from app.modules.payments.models import Payment
from app.modules.areas.models import Area
from app.modules.meetings.models import MeetingSummary

class SearchService:
    def __init__(self):
        # No db session needed in Beanie!
        pass

    async def global_search(self, query: str, current_user: User, limit: int = 15) -> Dict[str, List[Dict[str, Any]]]:
        """Performs a case-insensitive multi-collection search across the entire CRM system with RBAC enforcement."""
        from app.modules.users.models import UserRole
        from app.modules.billing.models import Bill

        if not query or len(query) < 2:
            return {
                "clients": [], "issues": [], "projects": [], "employees": [],
                "leads": [], "payments": [], "areas": [], "meetings": []
            }

        is_admin = current_user.role == UserRole.ADMIN
        results = {}

        # ─── Auth Context for non-admins ───
        auth_client_ids = []
        auth_shop_ids = []
        if not is_admin:
            # 1. Invoice Bridge
            billed_phones = await Bill.get_pymongo_collection().distinct(
                "invoice_client_phone", {"created_by_id": current_user.id}
            )
            # 2. Shops/Leads Bridge (Demo PM or Assigned)
            shops = await Shop.find(Or(
                Shop.owner_id == current_user.id,
                Shop.project_manager_id == current_user.id,
                Shop.created_by_id == current_user.id,
                In(Shop.assigned_user_ids, [current_user.id]),
                In(Shop.assigned_owner_ids, [current_user.id])
            )).to_list()
            auth_shop_ids = [s.id for s in shops]
            shop_client_ids = [s.client_id for s in shops if s.client_id]

            # 3. Consolidated Client List
            clients_q = await Client.find(Or(
                Client.owner_id == current_user.id,
                Client.pm_id == current_user.id,
                In(Client.phone, billed_phones),
                In(Client.id, shop_client_ids)
            )).to_list()
            auth_client_ids = [c.id for c in clients_q]

        # ─── 1. Search Clients ───────────────────────────────────────
        client_f = Client.find(Client.is_active == True, Client.is_deleted == False)
        if not is_admin: client_f = client_f.find(In(Client.id, auth_client_ids))
        clients = await client_f.find(Or(
            RegEx(Client.name, query, "i"),
            RegEx(Client.phone, query, "i"),
            RegEx(Client.organization, query, "i")
        )).limit(limit).to_list()
        results["clients"] = [{"id": str(c.id), "name": c.name, "type": "client", "subtext": (c.organization or c.phone)} for c in clients]

        # ─── 2. Search Issues ────────────────────────────────────────
        issue_f = Issue.find(Issue.is_deleted == False)
        if not is_admin:
            # Accessible via direct involvement or related client
            issue_f = issue_f.find(Or(
                Issue.reporter_id == current_user.id,
                Issue.assigned_to_id == current_user.id,
                In(Issue.client_id, auth_client_ids)
            ))
        issues = await issue_f.find(Or(
            RegEx(Issue.title, query, "i"),
            RegEx(Issue.description, query, "i")
        )).limit(limit).to_list()
        results["issues"] = [{"id": str(i.id), "name": i.title, "type": "issue", "subtext": str(i.status)} for i in issues]

        # ─── 3. Search Projects ──────────────────────────────────────
        project_f = Project.find(Project.is_deleted == False)
        if not is_admin: project_f = project_f.find(In(Project.client_id, auth_client_ids))
        projects = await project_f.find(RegEx(Project.name, query, "i")).limit(limit).to_list()
        results["projects"] = [{"id": str(p.id), "name": p.name, "type": "project", "subtext": str(p.status)} for p in projects]

        # ─── 4. Search Users (Employees) ───────────────────────────────
        users = await User.find(
            User.is_active == True, User.is_deleted == False,
            Or(RegEx(User.name, query, "i"), RegEx(User.email, query, "i"))
        ).limit(limit).to_list()
        results["employees"] = [{"id": str(u.id), "name": u.name, "type": "employee", "subtext": str(u.role)} for u in users]

        # ─── 5. Search Leads (Shops) ───────────────────────────────────
        shop_f = Shop.find(Shop.is_deleted == False)
        if not is_admin: shop_f = shop_f.find(In(Shop.id, auth_shop_ids))
        shops = await shop_f.find(Or(
            RegEx(Shop.name, query, "i"),
            RegEx(Shop.address, query, "i"),
            RegEx(Shop.contact_person, query, "i")
        )).limit(limit).to_list()
        results["leads"] = [{"id": str(l.id), "name": l.name, "type": "lead", "subtext": l.address} for l in shops]

        # ─── 6. Search Payments ───────────────────────────────────────
        pay_f = Payment.find()
        if not is_admin: pay_f = pay_f.find(In(Payment.client_id, auth_client_ids))
        
        payment_criteria = [RegEx(Payment.status, query, "i")]
        try:
            amt_val = float(query)
            payment_criteria.append(Payment.amount == amt_val)
        except ValueError: pass
            
        payments = await pay_f.find(Or(*payment_criteria)).limit(limit).to_list()
        results["payments"] = [{"id": str(p.id), "name": f"Payment: ₹{p.amount:,.2f}", "type": "payment", "subtext": f"Status: {p.status}"} for p in payments]

        # ─── 7. Search Areas ──────────────────────────────────────────
        areas = await Area.find(Or(
            RegEx(Area.name, query, "i"),
            RegEx(Area.pincode, query, "i"),
            RegEx(Area.city, query, "i")
        )).limit(limit).to_list()
        results["areas"] = [{"id": str(a.id), "name": a.name, "type": "area", "subtext": f"{a.city or ''} {a.pincode or ''}".strip()} for a in areas]

        # ─── 8. Search Meetings ───────────────────────────────────────
        meet_f = MeetingSummary.find(MeetingSummary.is_deleted == False)
        if not is_admin:
            meet_f = meet_f.find(Or(
                MeetingSummary.host_id == current_user.id,
                In(MeetingSummary.attendee_ids, [current_user.id]),
                In(MeetingSummary.client_id, auth_client_ids),
                In(MeetingSummary.project_id, auth_shop_ids)
            ))
        meetings = await meet_f.find(Or(
            RegEx(MeetingSummary.title, query, "i"),
            RegEx(MeetingSummary.content, query, "i")
        )).limit(limit).to_list()
        results["meetings"] = [{"id": str(m.id), "name": m.title, "type": "meeting", "subtext": m.date.strftime('%d %b %Y') if m.date else "TBD"} for m in meetings]

        return results
