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
from app.modules.attendance.service import AttendanceService
from app.modules.todos.models import Todo, TodoStatus
from app.modules.meetings.models import MeetingSummary
from app.modules.reports.models import PerformanceNote

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
        today_ist = AttendanceService.get_ist_today()
        # Ensure today_start matches the BSON Date storage (UTC 00:00:00)
        today_start = datetime.combine(today_ist, datetime.min.time()).replace(tzinfo=UTC)
        
        curr_month = now.month
        curr_year = now.year
        current_period = now.strftime('%Y-%m')
        
        # Local time boundaries for meeting queries
        today_local = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_local = today_local + timedelta(days=1)
        
        # Calculate comparison timeframe (MoM)
        prev_month = 12 if curr_month == 1 else curr_month - 1
        prev_year = curr_year - 1 if curr_month == 1 else curr_year
        
        import asyncio

        # Parse dates
        start_dt = None
        end_dt = None
        if start_date:
            try: start_dt = datetime.fromisoformat(str(start_date)).replace(tzinfo=UTC)
            except: pass
        if end_date:
            try: end_dt = datetime.fromisoformat(str(end_date)).replace(tzinfo=UTC)
            except: pass

        # Match expressions for date aggregation with type-safety
        curr_m_expr = {"$and": [{"$eq": [{"$type": "$created_at"}, "date"]}, {"$eq": [{"$month": "$created_at"}, curr_month]}, {"$eq": [{"$year": "$created_at"}, curr_year]}]}
        prev_m_expr = {"$and": [{"$eq": [{"$type": "$created_at"}, "date"]}, {"$eq": [{"$month": "$created_at"}, prev_month]}, {"$eq": [{"$year": "$created_at"}, prev_year]}]}

        # --- 1. Visits Metrics ---
        # 1. Base Filters
        v_match = {
            "is_deleted": False,
            "status": {"$in": [
                VisitStatus.SATISFIED.value, 
                VisitStatus.ACCEPT.value, 
                VisitStatus.DECLINE.value, 
                VisitStatus.TAKE_TIME_TO_THINK.value, 
                VisitStatus.OTHER.value, 
                VisitStatus.MISSED.value
            ]}
        }
        
        # Broader match for "Total Visits" count to match Visits page "Shops Visited" (66)
        v_all_count_match = {"is_deleted": False}

        if user_id: 
            v_match["user_id"] = user_id
            v_all_count_match["user_id"] = user_id
            
        if area_id:
             raw_ids = await Shop.get_pymongo_collection().distinct("_id", {"area_id": PydanticObjectId(area_id) if hasattr(area_id, "id") or type(area_id)==str else area_id})
             shop_ids = [PydanticObjectId(rid) for rid in raw_ids if rid]
             v_match["shop_id"] = {"$in": shop_ids}
             v_all_count_match["shop_id"] = {"$in": shop_ids}

        if start_dt or end_dt:
            date_filter = {}
            if start_dt: date_filter["$gte"] = start_dt
            if end_dt: date_filter["$lte"] = end_dt
            v_match["visit_date"] = date_filter
            v_all_count_match["visit_date"] = date_filter
        
        # Define expressions for Visit counts
        # Redefine expressions to be used after normalization
        v_expr_curr = {"$and": [
            {"$eq": [{"$month": "$v_date_dt"}, curr_month]},
            {"$eq": [{"$year": "$v_date_dt"}, curr_year]}
        ]}
        v_expr_prev = {"$and": [
            {"$eq": [{"$month": "$v_date_dt"}, prev_month]},
            {"$eq": [{"$year": "$v_date_dt"}, prev_year]}
        ]}
        
        c_match = {"status": "ACTIVE", "is_active": True, "is_deleted": False}
        if user_id:
            # Unified scoping: Owner, PM, or previously Billed
            billed_phones = await Bill.get_pymongo_collection().distinct(
                "invoice_client_phone", 
                {"created_by_id": user_id, "is_deleted": False}
            )
            c_match["$or"] = [
                {"owner_id": user_id}, 
                {"pm_id": user_id},
                {"phone": {"$in": billed_phones}}
            ]
        
        if area_id:
            # Correct area filtering for clients: find clients with a shop in this area
            target_area = PydanticObjectId(area_id) if isinstance(area_id, str) or not hasattr(area_id, "id") else area_id
            client_ids_in_area = await Shop.get_pymongo_collection().distinct("client_id", {"area_id": target_area, "is_deleted": False})
            c_match["_id"] = {"$in": [PydanticObjectId(rid) for rid in client_ids_in_area if rid]}
        if start_dt or end_dt:
            date_filter = {}
            if start_dt: date_filter["$gte"] = start_dt
            if end_dt: date_filter["$lte"] = end_dt
            c_match["created_at"] = date_filter
        
        p_match = {"status": GlobalTaskStatus.IN_PROGRESS, "is_deleted": False}
        if user_id: p_match["pm_id"] = user_id
        if start_dt or end_dt:
            date_filter = {}
            if start_dt: date_filter["$gte"] = start_dt
            if end_dt: date_filter["$lte"] = end_dt
            p_match["created_at"] = date_filter

        # Revenue filter: only count confirmed SUCCESSful payments
        b_match = {"status": "SUCCESS", "is_deleted": False}
        if user_id: b_match["created_by_id"] = user_id
        if start_dt or end_dt:
            date_filter = {}
            if start_dt: date_filter["$gte"] = start_dt
            if end_dt: date_filter["$lte"] = end_dt
            b_match["created_at"] = date_filter

        rev_pipeline = [
            {"$match": b_match},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]
        # today_start already defined above
        status_pipeline = [
            {"$match": v_match},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]

        date_normalization = [
            {"$addFields": {
                "v_date_dt": {
                    "$cond": {
                        "if": {"$eq": [{"$type": "$visit_date"}, "date"]},
                        "then": "$visit_date",
                        "else": {
                            "$cond": {
                                "if": {"$eq": [{"$type": "$visit_date"}, "string"]},
                                "then": {"$dateFromString": {"dateString": "$visit_date", "onError": None}},
                                "else": None
                            }
                        }
                    }
                }
            }}
        ]

        v_all_pipe = [{"$match": v_all_count_match}, {"$group": {"_id": "$shop_id"}}, {"$count": "total"}]
        v_curr_pipe = date_normalization + [{"$match": {**v_match, "$expr": v_expr_curr}}, {"$group": {"_id": "$shop_id"}}, {"$count": "total"}]
        v_prev_pipe = date_normalization + [{"$match": {**v_match, "$expr": v_expr_prev}}, {"$group": {"_id": "$shop_id"}}, {"$count": "total"}]

        (
            v_all_res, v_curr_res, v_prev_res,
            active_clients, clients_curr, clients_prev,
            projects_count, projects_curr, projects_prev,
            rev_res,
            present_user_ids,
            open_issues_count,
            visit_status_res,
            incentive_slip_res,
            pending_todos_count,
            meetings_today_count
        ) = await asyncio.gather(
            Visit.get_pymongo_collection().aggregate(v_all_pipe).to_list(length=1),
            Visit.get_pymongo_collection().aggregate(v_curr_pipe).to_list(length=1),
            Visit.get_pymongo_collection().aggregate(v_prev_pipe).to_list(length=1),
            Client.find(c_match).count(), 
            Client.find(c_match, {"$expr": curr_m_expr}).count(), Client.find(c_match, {"$expr": prev_m_expr}).count(),
            Shop.find({"is_deleted": False, "pipeline_stage": {"$in": ["PITCHING", "NEGOTIATION", "DELIVERY"]}}).count(), 
            Shop.find({"is_deleted": False, "pipeline_stage": {"$in": ["PITCHING", "NEGOTIATION", "DELIVERY"]}, "$expr": curr_m_expr}).count(), 
            Shop.find({"is_deleted": False, "pipeline_stage": {"$in": ["PITCHING", "NEGOTIATION", "DELIVERY"]}, "$expr": prev_m_expr}).count(),
            Bill.get_pymongo_collection().aggregate(rev_pipeline).to_list(length=None),
            Attendance.get_pymongo_collection().distinct("user_id", {"date": today_start, "is_deleted": False}),
            Issue.find(Issue.status == GlobalTaskStatus.OPEN, Issue.is_deleted == False).count(),
            Visit.get_pymongo_collection().aggregate(status_pipeline).to_list(length=None),
            IncentiveSlip.find_one(IncentiveSlip.user_id == user_id, IncentiveSlip.period == current_period, IncentiveSlip.is_visible_to_employee == True) if user_id else asyncio.sleep(0),
            Todo.find(Todo.user_id == user_id, Todo.status == TodoStatus.PENDING, Todo.is_deleted == False).count() if user_id else asyncio.sleep(0),
            MeetingSummary.find(MeetingSummary.date >= today_local, MeetingSummary.date < tomorrow_local, MeetingSummary.is_deleted == False, MeetingSummary.status != GlobalTaskStatus.CANCELLED).count() if user_id else asyncio.sleep(0),
        )

        total_visits = v_all_res[0]["total"] if v_all_res else 0
        v_curr = v_curr_res[0]["total"] if v_curr_res else 0
        v_prev = v_prev_res[0]["total"] if v_prev_res else 0

        visits_mom_pct = ReportService._get_mom_pct(v_curr, v_prev)
        active_clients = active_clients
        clients_mom_pct = ReportService._get_mom_pct(clients_curr, clients_prev)
        ongoing_projects = projects_count
        projects_mom_pct = ReportService._get_mom_pct(projects_curr, projects_prev)
        revenue_mtd = rev_res[0]["total"] if rev_res else 0.0
        employees_present = len(present_user_ids)
        visit_status_breakdown = {str(r["_id"]): r["count"] for r in visit_status_res}

        # --- Role-specific KPI values ---
        # Card 3 (My Incentive for Sales/Telesales): use admin-published incentive slip for current month
        my_incentive = 0.0
        if isinstance(incentive_slip_res, IncentiveSlip):
            my_incentive = float(incentive_slip_res.total_incentive or 0.0)

        # Card 4 (Pending Tasks): only PENDING status todos
        pending_todos = int(pending_todos_count) if isinstance(pending_todos_count, int) else 0

        # Card 3 (Meetings Today for PM)
        meetings_today = int(meetings_today_count) if isinstance(meetings_today_count, int) else 0

        # --- 7. Chart Data (Last 6 Months for UI) ---
        six_months_ago = now - timedelta(days=180)
        
        # Visits Trend with Safe Date Normalization
        v_chart_pipeline = date_normalization + [
            {"$match": {**v_match, "v_date_dt": {"$gte": six_months_ago}}},
            {"$group": {"_id": {"year": {"$year": "$v_date_dt"}, "month": {"$month": "$v_date_dt"}}, "count": {"$sum": 1}}},
            {"$sort": {"_id.year": 1, "_id.month": 1}}
        ]
        
        # Revenue Trend
        r_chart_pipeline = [
            {"$addFields": {"c_date_dt": {"$toDate": "$created_at"}}},
            {"$match": {**b_match, "c_date_dt": {"$gte": six_months_ago}}},
            {"$group": {"_id": {"year": {"$year": "$c_date_dt"}, "month": {"$month": "$c_date_dt"}}, "total": {"$sum": "$amount"}}},
            {"$sort": {"_id.year": 1, "_id.month": 1}}
        ]

        v_chart_res, r_chart_res = await asyncio.gather(
            Visit.get_pymongo_collection().aggregate(v_chart_pipeline).to_list(length=None),
            Bill.get_pymongo_collection().aggregate(r_chart_pipeline).to_list(length=None)
        )

        # Helper to pad data for the last 6 months
        def pad_monthly_data(results, key_name, months_count=6):
            padded = {}
            for i in range(months_count - 1, -1, -1):
                dt = now - timedelta(days=i*30)
                month_name = dt.strftime("%b")
                # Find if result exists for this month/year
                match = next((r for r in results if r["_id"]["month"] == dt.month and r["_id"]["year"] == dt.year), None)
                padded[month_name] = float(match[key_name]) if match else 0.0 if key_name == "total" else (match["count"] if match else 0)
            return padded

        visits_chart_data = pad_monthly_data(v_chart_res, "count")
        revenue_by_month = pad_monthly_data(r_chart_res, "total")

        # --- 8. Project / Pipeline Status Breakdown (from Shops) ---
        p_status_pipeline = [
            {"$match": {"is_deleted": False}},
            {"$group": {"_id": "$pipeline_stage", "count": {"$sum": 1}}}
        ]
        project_status_res = await Shop.get_pymongo_collection().aggregate(p_status_pipeline).to_list(length=None)
        project_status_breakdown = {str(r["_id"]): r["count"] for r in project_status_res}

        return {
            "total_visits": int(total_visits),
            "active_clients": int(active_clients),
            "ongoing_projects": int(ongoing_projects),
            "revenue_mtd": float(revenue_mtd),
            "visits_mom_pct": float(visits_mom_pct),
            "clients_mom_pct": float(clients_mom_pct),
            "projects_mom_pct": float(projects_mom_pct),
            "revenue_mom_pct": 0.0,
            "open_issues": int(open_issues_count),
            "employees_present": int(employees_present),
            "visit_status_breakdown": visit_status_breakdown,
            "visits_chart_data": visits_chart_data,
            "presence_mom_pct": 0.0,
            "visits_chart_title": 'Visits Overview',
            "revenue_by_month": revenue_by_month,
            "issue_severity_breakdown": {},
            "visit_outcomes_breakdown": visit_status_breakdown,
            "project_status_breakdown": project_status_breakdown,
            # Role-specific KPI extras (Ensure consistent type)
            "total_incentive": float(my_incentive),
            "pending_todos": int(pending_todos),
            "meetings_today": int(meetings_today),
        }

    @staticmethod
    def _parse_date(date_str, is_end=False):
        if not date_str:
            return None
        formats = ["%Y-%m-%d", "%d-%m-%Y", "%m-%d-%Y"]
        for fmt in formats:
            try:
                dt = datetime.strptime(str(date_str), fmt).replace(tzinfo=UTC)
                if is_end:
                    return dt.replace(hour=23, minute=59, second=59)
                return dt
            except:
                continue
        return None

    @staticmethod
    async def get_employee_performance(requesting_user: User, month: str = None, **kwargs):
        """Refined performance aggregation with custom timeframe support and Pydantic alignment."""
        now = datetime.now(UTC)
        
        # 1. Standardize date parameters from frontend (handle null/empty strings)
        start_date_raw = kwargs.get("start_date")
        end_date_raw = kwargs.get("end_date")
        
        # Consistent parsing: default to last 90 days if missing/empty
        start_dt = ReportService._parse_date(start_date_raw)
        if not start_dt:
            if start_date_raw == "": # Explicit "All Time" hint if passed as empty but handled by logic
                 start_dt = datetime(2000, 1, 1, tzinfo=UTC)
            else:
                 start_dt = now - timedelta(days=90)
                 
        end_dt = ReportService._parse_date(end_date_raw, is_end=True) or now

        match_stage = {"is_deleted": False, "role": {"$ne": "CLIENT"}}

        match_stage = {"is_deleted": False, "role": {"$ne": "CLIENT"}}
        
        # 2. Extract specific user filter from kwargs
        user_id_filter = kwargs.get("user_id")
        
        if requesting_user.role != UserRole.ADMIN:
            # Non-admins can only see their own performance
            match_stage["_id"] = requesting_user.id
        elif user_id_filter:
            # Admins can filter by a specific user if provided
            try:
                match_stage["_id"] = PydanticObjectId(user_id_filter)
            except:
                pass # Invalid ID, ignore filter
            
        pipeline = [
            {"$match": match_stage},
            {
                "$lookup": {
                    "from": "srm_visits",
                    "let": { "u_id": "$_id" },
                    "pipeline": [
                        { "$match": { 
                            "$expr": { "$eq": ["$user_id", "$$u_id"] },
                            "visit_date": { "$gte": start_dt, "$lte": end_dt },
                            "is_deleted": False,
                            "status": {"$in": [
                                "SATISFIED", 
                                "ACCEPT", 
                                "DECLINE", 
                                "TAKE_TIME_TO_THINK", 
                                "OTHER", 
                                "COMPLETED"
                            ]}
                        }}
                    ],
                    "as": "visits"
                }
            },
            {
                "$lookup": {
                    "from": "srm_payments",
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
                    "from": "srm_projects",
                    "localField": "_id",
                    "foreignField": "pm_id",
                    "as": "all_projects"
                }
            },
            {
                "$lookup": {
                    "from": "srm_issues",
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
                    "employee_code": 1,
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
                "target": r.get("target", 0),
                "employee_code": r.get("employee_code", "")
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
        if not projects:
            return []

        # --- BULK FETCH: Clients & Payments ---
        client_ids = list(set(p.client_id for p in projects if p.client_id))
        
        # 1. Fetch Clients in bulk
        clients_list = await Client.find(In(Client.id, client_ids)).to_list()
        client_map = {c.id: c for c in clients_list}
        
        # 2. Aggregate Payments in bulk for all relevant clients
        pay_pipeline = [
            {"$match": {"client_id": {"$in": client_ids}, "status": "VERIFIED"}},
            {"$group": {"_id": "$client_id", "total": {"$sum": "$amount"}}}
        ]
        pay_res = await Payment.get_pymongo_collection().aggregate(pay_pipeline).to_list(length=None)
        payment_map = {r["_id"]: r["total"] for r in pay_res}

        portfolio = []
        for p in projects:
            client = client_map.get(p.client_id)
            if not client: continue
            
            paid_sum = payment_map.get(p.client_id, 0.0)

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

    @staticmethod
    async def generate_csv_response(data: List[dict]) -> str:
        """Converts a list of dictionaries into a CSV string for export."""
        if not data:
            return ""
        
        output = io.StringIO()
        # Use keys from the first dictionary as headers
        keys = data[0].keys()
        dict_writer = csv.DictWriter(output, fieldnames=keys)
        dict_writer.writeheader()
        dict_writer.writerows(data)
        
        return output.getvalue()

    @staticmethod
    async def get_employee_activities(user_id: str, start_date: str = None, end_date: str = None):
        """Fetches a combined log of visits and verified payments for the activity stream."""
        now = datetime.now(UTC)
        s_dt = ReportService._parse_date(start_date) or (now - timedelta(days=30))
        e_dt = ReportService._parse_date(end_date, is_end=True) or now
        
        u_id = PydanticObjectId(user_id)
        activities = []
        
        # 1. Fetch Visits as Activities
        visits = await Visit.find(
            Visit.user_id == u_id,
            Visit.visit_date >= s_dt,
            Visit.visit_date <= e_dt,
            Visit.is_deleted == False
        ).to_list()
        
        for v in visits:
            # Try to get shop name for context
            shop_name = "Direct Visit"
            if v.shop_id:
                shop = await Shop.get(v.shop_id)
                if shop: shop_name = shop.name
            
            activities.append({
                "date": v.visit_date,
                "client": shop_name,
                "type": "Client Visit",
                "status": str(v.status).split('.')[-1]
            })
            
        # 2. Fetch Payments as Activities
        payments = await Payment.find(
            Payment.generated_by_id == u_id,
            Payment.verified_at >= s_dt,
            Payment.verified_at <= e_dt,
            Payment.status == "VERIFIED",
            Payment.is_deleted == False
        ).to_list()
        
        for p in payments:
            client = await Client.get(p.client_id)
            activities.append({
                "date": p.verified_at,
                "client": client.name if client else "Unknown Client",
                "type": f"Payment: ₹{p.amount}",
                "status": "VERIFIED"
            })
            
        # Sort by date descending
        activities.sort(key=lambda x: x["date"], reverse=True)
        return activities

    @staticmethod
    async def save_performance_note(emp_id: str, admin: User, content: str):
        """Saves a performance note for an employee."""
        note = PerformanceNote(
            employee_id=PydanticObjectId(emp_id),
            admin_id=admin.id,
            admin_name=admin.name or admin.email.split("@")[0],
            content=content
        )
        await note.insert()
        return note

    @staticmethod
    async def get_performance_notes(emp_id: str):
        """Fetches all performance notes for an employee, sorted by latest first."""
        notes = await PerformanceNote.find(
            PerformanceNote.employee_id == PydanticObjectId(emp_id)
        ).sort("-created_at").to_list()
        return notes

    @staticmethod
    async def delete_performance_note(note_id: str):
        """Deletes a performance note by ID."""
        note = await PerformanceNote.get(PydanticObjectId(note_id))
        if note:
            await note.delete()
            return True
        return False
