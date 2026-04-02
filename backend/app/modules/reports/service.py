# backend/app/modules/reports/service.py
from typing import List, Optional, Union, Any
from beanie import PydanticObjectId
from beanie.operators import In, Or, And
from datetime import datetime, timedelta, UTC
import calendar
import io
import csv
from collections import defaultdict

from app.modules.clients.models import Client
from app.modules.issues.models import Issue, IssueSeverity
from app.modules.visits.models import Visit, VisitStatus
from app.modules.users.models import User, UserRole
from app.modules.projects.models import Project
from app.modules.shops.models import Shop
from app.core.enums import GlobalTaskStatus
from app.modules.payments.models import Payment, PaymentStatus
from app.modules.billing.models import Bill
from app.modules.salary.models import SalarySlip
from app.modules.incentives.models import IncentiveSlip
from app.modules.attendance.models import Attendance
from app.modules.todos.models import Todo, TodoStatus
from app.modules.meetings.models import MeetingSummary

class ReportService:
    @staticmethod
    def _get_mom_pct(curr_val, prev_val):
        if not prev_val or prev_val == 0:
            return 100.0 if curr_val > 0 else 0.0
        return round(((curr_val - prev_val) / prev_val) * 100, 1)

    @staticmethod
    async def get_dashboard_stats(
        requesting_user: User,
        area_id: Optional[PydanticObjectId] = None, 
        user_id: Optional[PydanticObjectId] = None, 
        start_date: Optional[str] = None, 
        end_date: Optional[str] = None
    ):
        """Asynchronously aggregates CRM metrics using MongoDB pipelines."""
        if requesting_user.role != UserRole.ADMIN:
            user_id = requesting_user.id

        now = datetime.now(UTC)
        curr_month = now.month
        curr_year = now.year
        
        # Calculate comparison timeframe (MoM)
        prev_month = 12 if curr_month == 1 else curr_month - 1
        prev_year = curr_year - 1 if curr_month == 1 else curr_year
        
        # Match expressions for date aggregation with type-safety
        curr_m_expr = {"$and": [{"$eq": [{"$type": "$created_at"}, "date"]}, {"$eq": [{"$month": "$created_at"}, curr_month]}, {"$eq": [{"$year": "$created_at"}, curr_year]}]}
        prev_m_expr = {"$and": [{"$eq": [{"$type": "$created_at"}, "date"]}, {"$eq": [{"$month": "$created_at"}, prev_month]}, {"$eq": [{"$year": "$created_at"}, prev_year]}]}

        # --- 1. Visits Metrics ---
        v_match = {"is_deleted": False}
        if user_id: v_match["user_id"] = user_id
        if area_id:
             raw_ids = await Shop.get_pymongo_collection().distinct("_id", {"area_id": PydanticObjectId(area_id) if hasattr(area_id, "id") or type(area_id)==str else area_id})
             shop_ids = [PydanticObjectId(rid) for rid in raw_ids if rid]
             v_match["shop_id"] = {"$in": shop_ids}
        
        total_visits = await Visit.find(v_match).count()
        v_curr = await Visit.find(v_match, {"$expr": {"$and": [{"$eq": [{"$type": "$visit_date"}, "date"]}, {"$eq": [{"$month": "$visit_date"}, curr_month]}, {"$eq": [{"$year": "$visit_date"}, curr_year]}]}}).count()
        v_prev = await Visit.find(v_match, {"$expr": {"$and": [{"$eq": [{"$type": "$visit_date"}, "date"]}, {"$eq": [{"$month": "$visit_date"}, prev_month]}, {"$eq": [{"$year": "$visit_date"}, prev_year]}]}}).count()
        visits_mom_pct = ReportService._get_mom_pct(v_curr, v_prev)

        # --- 2. Client Metrics ---
        c_match = {"status": "ACTIVE", "is_deleted": False}
        if user_id: c_match["owner_id"] = user_id
        if area_id: c_match["area_id"] = area_id
        
        active_clients = await Client.find(c_match).count()
        c_curr = await Client.find(c_match, {"$expr": curr_m_expr}).count()
        c_prev = await Client.find(c_match, {"$expr": prev_m_expr}).count()
        clients_mom_pct = ReportService._get_mom_pct(c_curr, c_prev)

        # --- 3. Project Metrics ---
        p_match = {"status": GlobalTaskStatus.IN_PROGRESS, "is_deleted": False}
        if user_id: p_match["pm_id"] = user_id
        
        ongoing_projects = await Project.find(p_match).count()
        p_curr = await Project.find(p_match, {"$expr": curr_m_expr}).count()
        p_prev = await Project.find(p_match, {"$expr": prev_m_expr}).count()
        projects_mom_pct = ReportService._get_mom_pct(p_curr, p_prev)

        # --- 4. Revenue Aggregation (using Bill model) ---
        b_match = {"invoice_status": "SENT", "is_deleted": False}
        if user_id: b_match["created_by_id"] = user_id
        
        rev_pipeline = [
            {"$match": b_match},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]
        rev_res = await Bill.get_pymongo_collection().aggregate(rev_pipeline).to_list(length=None)
        revenue_mtd = rev_res[0]["total"] if rev_res else 0.0

        # --- 5. Staff Presence ---
        today_start = datetime.combine(now.date(), datetime.min.time())
        employees_present = len(await Attendance.get_pymongo_collection().distinct("user_id", {"date": today_start, "is_deleted": False}))

        # --- 6. Breakdown Analytics (Donut Chart) ---
        status_pipeline = [
            {"$match": v_match},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]
        visit_status_res = await Visit.get_pymongo_collection().aggregate(status_pipeline).to_list(length=None)
        visit_status_breakdown = {str(r["_id"]): r["count"] for r in visit_status_res}

        # --- 7. Chart Data (Last 12 Months for better visibility) ---
        one_year_ago = now - timedelta(days=365)
        
        # Visits Trend
        v_chart_pipeline = [
            {"$addFields": {"v_date_dt": {"$toDate": "$visit_date"}}},
            {"$match": {**v_match, "v_date_dt": {"$gte": one_year_ago}}},
            {"$group": {
                "_id": {
                    "year": {"$year": "$v_date_dt"},
                    "month": {"$month": "$v_date_dt"}
                },
                "count": {"$sum": 1}
            }},
            {"$sort": {"_id.year": 1, "_id.month": 1}},
            {"$limit": 12}
        ]
        v_chart_res = await Visit.get_pymongo_collection().aggregate(v_chart_pipeline).to_list(length=None)
        visits_chart_data = {datetime(r["_id"]["year"], r["_id"]["month"], 1).strftime("%b"): r["count"] for r in v_chart_res}

        # Revenue Trend
        r_chart_pipeline = [
            {"$addFields": {"c_date_dt": {"$toDate": "$created_at"}}},
            {"$match": {**b_match, "c_date_dt": {"$gte": one_year_ago}}},
            {"$group": {
                "_id": {
                    "year": {"$year": "$c_date_dt"},
                    "month": {"$month": "$c_date_dt"}
                },
                "total": {"$sum": "$amount"}
            }},
            {"$sort": {"_id.year": 1, "_id.month": 1}},
            {"$limit": 12}
        ]
        r_chart_res = await Bill.get_pymongo_collection().aggregate(r_chart_pipeline).to_list(length=None)
        revenue_by_month = {datetime(r["_id"]["year"], r["_id"]["month"], 1).strftime("%b"): float(r["total"]) for r in r_chart_res}

        return {
            "total_visits": total_visits,
            "active_clients": active_clients,
            "ongoing_projects": ongoing_projects,
            "revenue_mtd": float(revenue_mtd),
            "visits_mom_pct": visits_mom_pct,
            "clients_mom_pct": clients_mom_pct,
            "projects_mom_pct": projects_mom_pct,
            "revenue_mom_pct": 0.0,
            "open_issues": await Issue.find(Issue.status == GlobalTaskStatus.OPEN, Issue.is_deleted == False).count(),
            "employees_present": employees_present,
            "visit_status_breakdown": visit_status_breakdown,
            "visits_chart_data": visits_chart_data,
            "presence_mom_pct": 0.0,
            "visits_chart_title": 'Visits Overview',
            "revenue_by_month": revenue_by_month,
            "issue_severity_breakdown": {},
            "visit_outcomes_breakdown": visit_status_breakdown
        }

    @staticmethod
    async def get_employee_performance(requesting_user: User, month: str = None, **kwargs):
        """Refined performance aggregation with custom timeframe support and Pydantic alignment."""
        # 1. Parse timeframe from kwargs
        start_date_str = kwargs.get("start_date")
        end_date_str = kwargs.get("end_date")
        
        now = datetime.now(UTC)
        start_dt = datetime(now.year, now.month, 1, tzinfo=UTC)
        end_dt = now
        
        if start_date_str:
             try: start_dt = datetime.fromisoformat(str(start_date_str)).replace(tzinfo=UTC)
             except: pass
        if end_date_str:
             try: end_dt = datetime.fromisoformat(str(end_date_str)).replace(tzinfo=UTC)
             except: pass

        match_stage = {"is_deleted": False, "role": {"$ne": "CLIENT"}}
        if requesting_user.role != UserRole.ADMIN:
            match_stage["_id"] = requesting_user.id
            
        pipeline = [
            {"$match": match_stage},
            {
                "$lookup": {
                    "from": "visits",
                    "let": { "u_id": "$_id" },
                    "pipeline": [
                        { "$match": { 
                            "$expr": { "$eq": ["$user_id", "$$u_id"] },
                            "visit_date": { "$gte": start_dt, "$lte": end_dt },
                            "is_deleted": False
                        }}
                    ],
                    "as": "visits"
                }
            },
            {
                "$lookup": {
                    "from": "payments",
                    "let": { "u_id": "$_id" },
                    "pipeline": [
                        { "$match": { 
                            "$expr": { "$eq": ["$generated_by_id", "$$u_id"] },
                            "verified_at": { "$gte": start_dt, "$lte": end_dt },
                            "status": "VERIFIED",
                            "is_deleted": False
                        }}
                    ],
                    "as": "payments"
                }
            },
            {
                "$lookup": {
                    "from": "projects",
                    "localField": "_id",
                    "foreignField": "pm_id",
                    "as": "all_projects"
                }
            },
            {
                "$lookup": {
                    "from": "issues",
                    "localField": "_id",
                    "foreignField": "assigned_to_id",
                    "as": "all_issues"
                }
            },
            {
                "$project": {
                    "name": 1,
                    "email": 1,
                    "role": 1,
                    "target": 1,
                    "total_visits": {"$size": "$visits"},
                    "total_leads": {"$size": {"$filter": {"input": "$visits", "cond": {"$eq": ["$$this.status", "COMPLETED"]}}}},
                    "revenue": {"$sum": "$payments.amount"},
                    "total_projects": {"$size": {"$filter": {"input": "$all_projects", "cond": {"$eq": ["$$this.is_deleted", False]}}}},
                    "total_open_issues": {"$size": {"$filter": {"input": "$all_issues", "cond": {"$and": [{"$eq": ["$$this.status", "OPEN"]}, {"$eq": ["$$this.is_deleted", False]}]}}}}
                }
            }
        ]
        
        results = await User.get_pymongo_collection().aggregate(pipeline).to_list(length=None)
        
        performance = []
        for r in results:
            tv = r.get("total_visits", 0)
            tl = r.get("total_leads", 0)
            rev = float(r.get("revenue", 0.0))
            u_id = str(r["_id"])
            performance.append({
                "user_id": u_id,
                "id": u_id,
                "name": r.get("name") or r.get("email", "").split("@")[0],
                "email": r.get("email", ""),
                "role": r.get("role"),
                "total_visits": tv,
                "total_leads": tl,
                "success_rate": round((tl / tv * 100), 1) if tv > 0 else 0.0,
                "total_sales": rev,
                "total_revenue": rev,
                "total_incentive": round(rev * 0.05, 2),
                "total_projects": r.get("total_projects", 0),
                "total_open_issues": r.get("total_open_issues", 0),
                "target": r.get("target", 0)
            })
        return performance

    @staticmethod
    async def get_project_portfolio(requesting_user: User):
        """Fetches project health and financial standing across all active engagements."""
        q = Project.find(Project.is_deleted == False)
        if requesting_user.role != UserRole.ADMIN:
            # Manual filtering across clients
            raw_c_ids = await Client.get_pymongo_collection().distinct("_id", {
                "$or": [{"owner_id": requesting_user.id}, {"pm_id": requesting_user.id}]
            })
            owned_clients = [PydanticObjectId(rid) for rid in raw_c_ids if rid]
            q = q.find(Or(Project.pm_id == requesting_user.id, In(Project.client_id, owned_clients)))
        
        projects = await q.to_list()
        portfolio = []
        for p in projects:
            client = await Client.get(p.client_id)
            if not client: continue
            
            # Sum verified payments
            paid_res = await Payment.get_pymongo_collection().aggregate([
                {"$match": {"client_id": p.client_id, "status": "VERIFIED"}},
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
            ]).to_list(length=None)
            paid_sum = paid_res[0]["total"] if paid_res else 0.0

            portfolio.append({
                "id": str(p.id),
                "fullName": client.name,
                "org": client.organization or "Individual",
                "project": p.name,
                "priority": str(p.priority),
                "totalAmount": float(p.budget or 0.0),
                "paidAmount": float(paid_sum),
                "outstanding": max(0.0, float(p.budget or 0) - float(paid_sum)),
                "status": str(p.status)
            })
        return portfolio

    @staticmethod
    async def get_business_summary(month: str = None):
        """High-level financial P&L aggregation for the requested month."""
        if not month: month = datetime.now(UTC).strftime('%Y-%m')
        year, m = map(int, month.split('-'))
        
        # Revenue from verified payments
        rev_res = await Payment.get_pymongo_collection().aggregate([
            {"$match": {"status": "VERIFIED", "$expr": {"$and": [{"$eq": [{"$type": "$verified_at"}, "date"]}, {"$eq": [{"$month": "$verified_at"}, m]}, {"$eq": [{"$year": "$verified_at"}, year]}]}}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]).to_list(length=None)
        
        # Expenses from salary and incentives
        sal_res = await SalarySlip.get_pymongo_collection().aggregate([{"$match": {"month": month}}, {"$group": {"_id": None, "total": {"$sum": "$final_salary"}}}]).to_list(length=None)
        inc_res = await IncentiveSlip.get_pymongo_collection().aggregate([{"$match": {"period": month}}, {"$group": {"_id": None, "total": {"$sum": "$total_incentive"}}}]).to_list(length=None)
        
        revenue = rev_res[0]["total"] if rev_res else 0.0
        expenses = (sal_res[0]["total"] if sal_res else 0.0) + (inc_res[0]["total"] if inc_res else 0.0)
        
        return {
            "month": month,
            "total_revenue": float(revenue),
            "total_expenses": float(expenses),
            "net_profit": float(revenue - expenses),
            "new_clients": await Client.find({"$expr": {"$and": [{"$eq": [{"$type": "$created_at"}, "date"]}, {"$eq": [{"$month": "$created_at"}, m]}, {"$eq": [{"$year": "$created_at"}, year]}]}}).count()
        }
