# backend/app/modules/incentives/service.py
from beanie import PydanticObjectId
from beanie.operators import In, Or, And
from fastapi import HTTPException
from datetime import datetime, UTC, timedelta
from typing import List, Optional, Dict, Any

from app.modules.incentives.models import IncentiveSlab, IncentiveSlip
from app.modules.incentives.schemas import IncentiveCalculationRequest, IncentiveSlipRead
from app.modules.users.models import User, UserRole
from app.modules.clients.models import Client

class IncentiveService:
    def __init__(self):
        # No db session needed in Beanie!
        pass

    @staticmethod
    def _user_display_name(user: Optional[User], user_id: PydanticObjectId) -> str:
        if not user:
            return f"Employee #{user_id}"
        return user.name or f"Employee #{user_id}"

    @staticmethod
    def _get_period_bounds(period: str) -> tuple[datetime, datetime]:
        year, month = map(int, period.split('-'))
        period_start = datetime(year, month, 1, tzinfo=UTC)
        if month == 12:
            next_month_start = datetime(year + 1, 1, 1, tzinfo=UTC)
        else:
            next_month_start = datetime(year, month + 1, 1, tzinfo=UTC)
        return period_start, next_month_start

    def _apply_role_scope_query(self, user: User):
        """Returns a Beanie query for clients based on user role permission profiling."""
        q = Client.find(Client.is_active == True, Client.is_deleted == False)
        if user.role == UserRole.TELESALES or user.role == UserRole.SALES:
            return q.find(Client.owner_id == user.id)
        if user.role == UserRole.PROJECT_MANAGER:
            return q.find(Client.pm_id == user.id)
        if user.role == UserRole.PROJECT_MANAGER_AND_SALES:
            return q.find(Or(Client.owner_id == user.id, Client.pm_id == user.id))
        # Default: restricted view (e.g. for purely administrative users without client handling)
        return q.find(Client.id == PydanticObjectId("000000000000000000000000"))

    async def _calculate_stepped_incentive(self, batch_count: int, offset: int = 0) -> dict:
        """Logic to distribute unit count across progressive incentive slabs and calculate total reward."""
        if batch_count <= 0:
            return {
                "incentive_per_unit": 0.0,
                "slab_bonus": 0.0,
                "total_incentive": 0.0,
                "applied_slab_label": f"Offset: {offset}" if offset > 0 else None,
                "offset": offset
            }

        all_slabs = await IncentiveSlab.find_all().sort("min_units").to_list()
        
        total_incentive = 0.0
        total_bonus = 0.0
        total_units_end = offset + batch_count
        
        for slab in all_slabs:
            # Units falling into this slab's range
            units_before = max(0, min(offset, slab.max_units) - slab.min_units + 1)
            units_total = max(0, min(total_units_end, slab.max_units) - slab.min_units + 1)
            units_to_pay = units_total - units_before
            
            if units_to_pay > 0:
                total_incentive += (units_to_pay * slab.incentive_per_unit)
                # Apply bonus if milestone reached in this current calculation batch
                if total_units_end >= slab.max_units and offset < slab.max_units:
                    total_bonus += slab.slab_bonus
                    total_incentive += slab.slab_bonus

        applied_slab_label = f"Continuous ({offset + 1}nd–{total_units_end}th)" if offset > 0 else f"Incremental (1–{batch_count})"
        avg_rate = (total_incentive - total_bonus) / batch_count if batch_count > 0 else 0.0

        return {
            "incentive_per_unit": round(avg_rate, 2),
            "slab_bonus": round(total_bonus, 2),
            "total_incentive": round(total_incentive, 2),
            "applied_slab_label": applied_slab_label,
            "offset": offset
        }

    async def _get_historical_offset(self, user_id: PydanticObjectId, period: str) -> int:
        """Calculate total units already paid for this period across all slips."""
        slips = await IncentiveSlip.find(
            IncentiveSlip.user_id == user_id,
            IncentiveSlip.period == period
        ).to_list()
        return sum(s.achieved for s in slips)

    async def calculate_incentive(self, calc_in: IncentiveCalculationRequest) -> Optional[IncentiveSlipRead]:
        user = await User.get(calc_in.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if not getattr(user, "incentive_enabled", True):
            raise HTTPException(status_code=400, detail="Incentive is disabled for this user")

        # 1. Anchor logic: Only consider clients created in THIS period
        period_start, next_month_start = self._get_period_bounds(calc_in.period)
        
        # 10-day maturation rule
        ten_days_ago = datetime.now(UTC) - timedelta(days=10)
        eligibility_end = ten_days_ago

        # 2. Total matured units for this period
        query = self._apply_role_scope_query(user).find(
            Client.created_at >= period_start,
            Client.created_at < next_month_start,
            Client.created_at < eligibility_end,
            Client.status == "ACTIVE"
        )
        total_matured_in_period = await query.count()

        # 3. How many were already paid for this period?
        offset = await self._get_historical_offset(user.id, calc_in.period)
        
        # 4. Impact check
        newly_matured = total_matured_in_period - offset
        
        if newly_matured <= 0:
            # Nothing new to pay
            return None

        # 5. Calculate stepped incentive for the NEW units using the OFFSET
        calc_result = await self._calculate_stepped_incentive(newly_matured, offset=offset)

        user_target = getattr(user, "target", 0) or 0
        # Percentage is based on total-period tally
        percentage = (total_matured_in_period / user_target * 100) if user_target > 0 else 0.0

        # 6. Create the NEW slip (representing the incremental payment)
        db_slip = IncentiveSlip(
            user_id=calc_in.user_id,
            period=calc_in.period,
            target=user_target,
            achieved=newly_matured,
            percentage=percentage,
            applied_slab=calc_result["applied_slab_label"],
            amount_per_unit=calc_result["incentive_per_unit"],
            slab_bonus_amount=calc_result["slab_bonus"],
            is_visible_to_employee=True,
            total_incentive=calc_result["total_incentive"],
            generated_at=datetime.now(UTC)
        )
        await db_slip.insert()

        res = IncentiveSlipRead.model_validate(db_slip)
        res.user_name = user.name or f"Employee #{user.id}"
        return res

    async def calculate_incentive_bulk(self, period: str) -> dict:
        """Sequential bulk calculation across users with incentive profiles."""
        users = await User.find(
            User.is_active == True,
            User.is_deleted == False,
            User.role != UserRole.ADMIN,
            User.role != UserRole.CLIENT
        ).to_list()

        created_slips = 0
        skipped_existing = 0
        skipped_disabled = 0
        failures = []

        for user in users:
            if not getattr(user, "incentive_enabled", True):
                skipped_disabled += 1
                continue

            exists = await IncentiveSlip.find_one(IncentiveSlip.user_id == user.id, IncentiveSlip.period == period)
            if exists:
                skipped_existing += 1
                continue

            try:
                await self.calculate_incentive(IncentiveCalculationRequest(user_id=user.id, period=period))
                created_slips += 1
            except Exception as e:
                failures.append({"user_id": str(user.id), "user_name": user.name, "error": str(e)})

        return {
            "period": period,
            "processed_users": len(users),
            "created_slips": created_slips,
            "skipped_existing": skipped_existing,
            "skipped_disabled": skipped_disabled,
            "failed_users": len(failures),
            "failures": failures,
        }

    async def get_user_incentive_slips(self, user_id: PydanticObjectId, visible_only: bool = False):
        q = IncentiveSlip.find(IncentiveSlip.user_id == user_id)
        if visible_only:
            q = q.find(IncentiveSlip.is_visible_to_employee == True)
        
        slips = await q.sort("-period", "-generated_at").to_list()
        user = await User.get(user_id)
        u_name = user.name if user else f"Employee #{user_id}"
        
        results = []
        for s in slips:
            r = IncentiveSlipRead.model_validate(s)
            r.user_name = u_name
            results.append(r)
        return results

    async def get_visible_user_incentive_slips(self, user_id: PydanticObjectId):
        return await self.get_user_incentive_slips(user_id, visible_only=True)

    async def calculate_progressive_incentive(self, user_id: PydanticObjectId, period: str):
        """Fetch existing incentive slips for a user and period."""
        return await IncentiveSlip.find(
            IncentiveSlip.user_id == user_id,
            IncentiveSlip.period == period
        ).to_list()

    async def get_all_incentive_slips(self):
        slips = await IncentiveSlip.find_all().sort("-period", "-generated_at").to_list()
        results = []
        for s in slips:
            user = await User.get(s.user_id)
            r = IncentiveSlipRead.model_validate(s)
            r.user_name = user.name if user else f"Employee #{s.user_id}"
            results.append(r)
        return results

    async def preview_incentive(self, user_id: PydanticObjectId, period: str, closed_units: Optional[int] = None) -> dict:
        user = await User.get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="Employee not found")
        
        target = getattr(user, "target", 0) or 0
        
        period_start, _ = self._get_period_bounds(period)
        
        last_slip = await IncentiveSlip.find(
            IncentiveSlip.user_id == user.id,
            IncentiveSlip.period < period
        ).sort("-generated_at").first_or_none()

        eligibility_start = (last_slip.generated_at - timedelta(days=10)) if last_slip and last_slip.generated_at else (period_start - timedelta(days=10))
        eligibility_end = datetime.now(UTC) - timedelta(days=10)

        # Base query for all clients in window
        base_q = self._apply_role_scope_query(user).find(
            Client.created_at >= eligibility_start,
            Client.created_at < eligibility_end
        )
        
        total_tasks = await base_q.count()
        confirmed_tasks = await base_q.find(Client.status == "ACTIVE").count()
        refunded_tasks = await base_q.find(Client.status == "REFUNDED").count()
        pending_tasks = total_tasks - confirmed_tasks - refunded_tasks

        # Override achieved if manual closed_units provided (e.g. for "what-if" scenarios)
        achieved = closed_units if closed_units is not None else confirmed_tasks
        
        calc_result = await self._calculate_stepped_incentive(achieved, offset=0)
        
        # Check if slip already exists
        exists = await IncentiveSlip.find_one(IncentiveSlip.user_id == user_id, IncentiveSlip.period == period)
        
        base_incentive = achieved * calc_result["incentive_per_unit"]
        percentage = (achieved / target * 100) if target > 0 else 0.0

        return {
            "user_id": str(user_id),
            "user_name": user.name or f"User #{user_id}",
            "period": period,
            "target": target,
            "confirmed_tasks": achieved,
            "pending_tasks": pending_tasks,
            "refunded_tasks": refunded_tasks,
            "total_tasks_in_period": total_tasks,
            "slab_range": calc_result["applied_slab_label"],
            "incentive_per_task": calc_result["incentive_per_unit"],
            "base_incentive": round(base_incentive, 2),
            "slab_bonus": calc_result["slab_bonus"],
            "total_incentive": calc_result["total_incentive"],
            "percentage": round(percentage, 2),
            "slip_exists": exists is not None,
            "audit_window_start": eligibility_start.strftime("%Y-%m-%d"),
            "audit_window_end": eligibility_end.strftime("%Y-%m-%d")
        }
