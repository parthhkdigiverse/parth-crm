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

    async def global_search(self, query: str, limit: int = 15) -> Dict[str, List[Dict[str, Any]]]:
        """Performs a case-insensitive multi-collection search across the entire CRM system."""
        if not query or len(query) < 2:
            return {
                "clients": [],
                "issues": [],
                "projects": [],
                "employees": [],
                "leads": [],
                "payments": [],
                "areas": [],
                "meetings": []
            }

        # Case-insensitive regex pattern
        results = {}

        # 1. Search Clients
        clients = await Client.find(
            Client.is_active == True,
            Or(
                RegEx(Client.name, query, "i"),
                RegEx(Client.phone, query, "i"),
                RegEx(Client.organization, query, "i")
            )
        ).limit(limit).to_list()
        results["clients"] = [{"id": str(c.id), "name": c.name, "type": "client", "subtext": (c.organization or c.phone)} for c in clients]

        # 2. Search Issues
        issues = await Issue.find(
            Or(
                RegEx(Issue.title, query, "i"),
                RegEx(Issue.description, query, "i")
            )
        ).limit(limit).to_list()
        results["issues"] = [{"id": str(i.id), "name": i.title, "type": "issue", "subtext": str(i.status)} for i in issues]

        # 3. Search Projects
        projects = await Project.find(
            RegEx(Project.name, query, "i")
        ).limit(limit).to_list()
        results["projects"] = [{"id": str(p.id), "name": p.name, "type": "project", "subtext": str(p.status)} for p in projects]

        # 4. Search Users (Employees)
        users = await User.find(
            User.is_active == True,
            User.is_deleted == False,
            Or(
                RegEx(User.name, query, "i"),
                RegEx(User.email, query, "i")
            )
        ).limit(limit).to_list()
        results["employees"] = [{"id": str(u.id), "name": u.name, "type": "employee", "subtext": str(u.role)} for u in users]

        # 5. Search Leads (Shops)
        shops = await Shop.find(
            Or(
                RegEx(Shop.name, query, "i"),
                RegEx(Shop.address, query, "i"),
                RegEx(Shop.contact_person, query, "i")
            )
        ).limit(limit).to_list()
        results["leads"] = [{"id": str(l.id), "name": l.name, "type": "lead", "subtext": l.address} for l in shops]

        # 6. Search Payments (Handling numeric amount vs string status)
        payment_criteria = [RegEx(Payment.status, query, "i")]
        try:
            amt_val = float(query)
            payment_criteria.append(Payment.amount == amt_val)
        except ValueError:
            pass
            
        payments = await Payment.find(Or(*payment_criteria)).limit(limit).to_list()
        results["payments"] = [{"id": str(p.id), "name": f"Payment: ₹{p.amount:,.2f}", "type": "payment", "subtext": f"Status: {p.status}"} for p in payments]

        # 7. Search Areas
        areas = await Area.find(
            Or(
                RegEx(Area.name, query, "i"),
                RegEx(Area.pincode, query, "i"),
                RegEx(Area.city, query, "i")
            )
        ).limit(limit).to_list()
        results["areas"] = [{"id": str(a.id), "name": a.name, "type": "area", "subtext": f"{a.city or ''} {a.pincode or ''}".strip()} for a in areas]

        # 8. Search Meetings
        meetings = await MeetingSummary.find(
            Or(
                RegEx(MeetingSummary.title, query, "i"),
                RegEx(MeetingSummary.content, query, "i")
            )
        ).limit(limit).to_list()
        results["meetings"] = [{"id": str(m.id), "name": m.title, "type": "meeting", "subtext": m.date.strftime('%d %b %Y') if m.date else "TBD"} for m in meetings]

        return results
