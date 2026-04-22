# backend/app/modules/salary/service.py
from beanie import PydanticObjectId
from beanie.operators import In, Or, And
from fastapi import HTTPException
from datetime import datetime, UTC
from typing import List, Optional
import calendar
import os
import base64

from app.modules.salary.models import LeaveRecord, SalarySlip, LeaveStatus
from app.modules.settings.models import AppSetting
from app.modules.salary.schemas import SalarySlipGenerate
from app.modules.users.models import User


class SalaryService:
    def __init__(self):
        # No db session needed in Beanie!
        pass

    async def _get_working_days_for_month(self, year: int, month_num: int) -> float:
        from datetime import date, timedelta
        import calendar
        from app.modules.settings.models import SystemSettings
        
        settings = await SystemSettings.find_one()
        saturday_policy = settings.saturday_policy if settings and hasattr(settings, 'saturday_policy') else "FULL_WORKING"
        
        _, last_day = calendar.monthrange(year, month_num)
        month_start = date(year, month_num, 1)
        month_end = date(year, month_num, last_day)

        total_working_days_in_month = 0.0
        curr = month_start
        while curr <= month_end:
            wd = curr.weekday()
            if wd == 6:  # Sunday
                pass
            elif wd == 5:  # Saturday
                sat_nth = (curr.day - 1) // 7 + 1
                if saturday_policy == "FULL_OFF":
                    pass
                elif saturday_policy == "HALF_WORKING":
                    total_working_days_in_month += 0.5
                elif saturday_policy == "SECOND_AND_FOURTH_OFF":
                    if sat_nth not in [2, 4]:
                        total_working_days_in_month += 1.0
                elif saturday_policy == "ALTERNATE":
                    if sat_nth in [1, 3, 5]:
                        total_working_days_in_month += 1.0
                else: # FULL_WORKING
                    total_working_days_in_month += 1.0
            else:
                total_working_days_in_month += 1.0
            curr += timedelta(days=1)
        return float(total_working_days_in_month)

    async def _get_leave_data(self, user_id: PydanticObjectId, year: int, month_num: int):
        """Fetch approved leaves for a user in given year/month.
        Handles cross-month overlaps by clipping the leave to month boundaries.
        Skips Sundays and handles Saturday policy.
        """
        from datetime import date, timedelta
        import calendar
        from app.modules.settings.models import SystemSettings
        
        settings = await SystemSettings.find_one()
        saturday_policy = settings.saturday_policy if settings and hasattr(settings, 'saturday_policy') else "FULL_WORKING"
        
        _, last_day = calendar.monthrange(year, month_num)
        month_start = date(year, month_num, 1)
        month_end = date(year, month_num, last_day)
        
        total_working_days_in_month = await self._get_working_days_for_month(year, month_num)

        all_approved = await LeaveRecord.find(
            LeaveRecord.user_id == user_id,
            LeaveRecord.status == LeaveStatus.APPROVED,
            LeaveRecord.is_deleted != True
        ).to_list()

        month_leaves = []
        total_leave_days = 0.0

        for lv in all_approved:
            if lv.start_date <= month_end and lv.end_date >= month_start:
                effective_start = max(lv.start_date, month_start)
                effective_end = min(lv.end_date, month_end)
                
                leave_multiplier = 0.5 if getattr(lv, 'day_type', 'FULL') == 'HALF' else 1.0
                curr = effective_start
                overlap_days = 0.0
                while curr <= effective_end:
                    wd = curr.weekday()
                    if wd == 6: # Sunday
                        pass
                    elif wd == 5: # Saturday
                        day_num = curr.day
                        sat_nth = (day_num - 1) // 7 + 1
                        if saturday_policy == "FULL_OFF":
                            pass
                        elif saturday_policy == "HALF_WORKING":
                            overlap_days += 0.5 * leave_multiplier
                        elif saturday_policy == "SECOND_AND_FOURTH_OFF":
                            if sat_nth not in [2, 4]:
                                overlap_days += 1.0 * leave_multiplier
                        elif saturday_policy == "ALTERNATE":
                            if sat_nth in [1, 3, 5]:
                                overlap_days += 1.0 * leave_multiplier
                        else: # FULL_WORKING
                            overlap_days += 1.0 * leave_multiplier
                    else:
                        overlap_days += 1.0 * leave_multiplier
                    curr += timedelta(days=1)
                
                if overlap_days > 0:
                    total_leave_days += overlap_days
                    month_leaves.append(lv)

        return month_leaves, total_leave_days, total_working_days_in_month

    async def _get_incentive_data(self, user_id: PydanticObjectId, month_str: str, current_slip_id: PydanticObjectId = None):
        """Read all UNPAID incentive and slab bonuses for this user.
        Splits them into prev_month and curr_month.
        """
        from app.modules.incentives.models import IncentiveSlip as IncSlip
        from beanie import PydanticObjectId as BsonId
        from beanie.operators import Or
        from datetime import datetime

        uid = BsonId(str(user_id)) if not isinstance(user_id, BsonId) else user_id

        slips = await IncSlip.find(
            IncSlip.user_id == uid,
            Or(IncSlip.salary_slip_id == None, IncSlip.salary_slip_id == current_slip_id)
        ).to_list()

        y, m = map(int, month_str.split('-'))
        if m == 1:
            prev_y, prev_m = y - 1, 12
        else:
            prev_y, prev_m = y, m - 1
        prev_month_str = f"{prev_y}-{prev_m:02d}"

        prev_inc = 0.0
        prev_slab = 0.0
        curr_inc = 0.0
        curr_slab = 0.0
        
        total_inc = 0.0
        total_bonus = 0.0
        breakdown = {}

        for s in slips:
            amt = (s.total_incentive or 0.0) - (s.slab_bonus_amount or 0.0)
            bonus = (s.slab_bonus_amount or 0.0)
            
            if s.period == prev_month_str:
                prev_inc += amt
                prev_slab += bonus
            elif s.period == month_str:
                curr_inc += amt
                curr_slab += bonus
            else:
                prev_inc += amt
                prev_slab += bonus
                
            total_inc += amt
            total_bonus += bonus

            period = s.period
            breakdown[period] = breakdown.get(period, 0.0) + amt

        return {
            "prev_inc": round(prev_inc, 2),
            "prev_slab": round(prev_slab, 2),
            "curr_inc": round(curr_inc, 2),
            "curr_slab": round(curr_slab, 2),
            "total_inc": round(total_inc, 2),
            "total_bonus": round(total_bonus, 2),
            "breakdown": breakdown
        }

    def _compute_salary(self, base: float, unpaid_leaves: float, prev_inc: float, prev_slab: float, curr_inc: float, curr_slab: float, extra_deduction: float, total_working_days: float = 30):
        """Standard Compute Engine for Salary Figures using actual working days."""
        if total_working_days <= 0:
            total_working_days = 30
        daily_wage = base / total_working_days
        days_worked = max(0, total_working_days - unpaid_leaves)
        gross_salary = daily_wage * days_worked
        leave_deduction = round(daily_wage * unpaid_leaves, 2)
        total_incentive = prev_inc + prev_slab + curr_inc + curr_slab
        total_earnings = round(base + total_incentive, 2)
        final_salary = round(total_earnings - leave_deduction - extra_deduction, 2)
        return {
            'daily_wage': daily_wage,
            'gross_salary': round(gross_salary, 2),
            'leave_deduction': leave_deduction,
            'total_earnings': total_earnings,
            'final_salary': final_salary,
            'total_working_days': total_working_days,
            'days_worked': days_worked
        }

    # TODO: Implement MongoDB transactions for financial safety
    async def generate_salary_slip(self, salary_in: SalarySlipGenerate) -> dict:
        """Asynchronously generates a new DRAFT salary slip."""
        user = await User.get(salary_in.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Check for duplication — ignore soft-deleted slips so they can be regenerated
        existing = await SalarySlip.find_one(
            SalarySlip.user_id == salary_in.user_id,
            SalarySlip.month == salary_in.month,
            SalarySlip.is_deleted != True
        )
        
        # If the slip is confirmed, we prevent automatic overwrites. 
        # The admin must revert it to draft manually first to prevent accidental payment overwrites.
        if existing and existing.status == "CONFIRMED":
            raise HTTPException(status_code=400, detail="Salary slip already CONFIRMED. Revert to draft first to recalculate.")

        year, month_num = map(int, salary_in.month.split('-'))
        
        month_leaves, total_leave_days, total_working_days = await self._get_leave_data(salary_in.user_id, year, month_num)
        inc_data = await self._get_incentive_data(salary_in.user_id, salary_in.month)
        
        base = salary_in.base_salary if salary_in.base_salary is not None else (user.base_salary or 0.0)
        calc = self._compute_salary(base, total_leave_days, 
                                    inc_data["prev_inc"], inc_data["prev_slab"], 
                                    inc_data["curr_inc"], inc_data["curr_slab"], 
                                    salary_in.extra_deduction, total_working_days)

        if existing:
            slip = existing
            slip.base_salary = base
            slip.unpaid_leaves = total_leave_days
            slip.deduction_amount = salary_in.extra_deduction
            slip.prev_month_incentive = inc_data["prev_inc"]
            slip.prev_month_slab = inc_data["prev_slab"]
            slip.curr_month_incentive = inc_data["curr_inc"]
            slip.curr_month_slab = inc_data["curr_slab"]
            slip.incentive_amount = inc_data["total_inc"]
            slip.slab_bonus = inc_data["total_bonus"]
            slip.incentive_breakdown = inc_data["breakdown"]
            slip.total_earnings = calc['total_earnings']
            slip.final_salary = calc['final_salary']
            slip.status = "DRAFT"
            slip.is_visible_to_employee = False
            slip.generated_at = datetime.now(UTC).date()
            await slip.save()
        else:
            slip = SalarySlip(
                user_id=salary_in.user_id,
                month=salary_in.month,
                base_salary=base,
                paid_leaves=0.0,
                unpaid_leaves=total_leave_days,
                deduction_amount=salary_in.extra_deduction,
                prev_month_incentive=inc_data["prev_inc"],
                prev_month_slab=inc_data["prev_slab"],
                curr_month_incentive=inc_data["curr_inc"],
                curr_month_slab=inc_data["curr_slab"],
                incentive_amount=inc_data["total_inc"],
                slab_bonus=inc_data["total_bonus"],
                incentive_breakdown=inc_data["breakdown"],
                total_earnings=calc['total_earnings'],
                final_salary=calc['final_salary'],
                status="DRAFT",
                generated_at=datetime.now(UTC).date()
            )
            await slip.insert()
            
        return await self._format_slip(slip)

    async def confirm_salary_slip(self, slip_id: PydanticObjectId, confirmed_by_id: PydanticObjectId):
        """Confirms a draft slip, marking it for payment and making it visible."""
        slip = await SalarySlip.get(slip_id)
        if not slip: raise HTTPException(status_code=404, detail="Slip not found")
        # Assign slip number based on last 3 digits of employee code
        if not slip.slip_no:
            user = await User.get(slip.user_id)
            full_code = (user.employee_code if user and user.employee_code else str(slip.user_id)).strip()
            # Take last 3 digits (e.g. 017 from EMP017)
            emp_suffix = full_code[-3:]
            year, month_num = slip.month.split('-')
            slip.slip_no = f"PS-{year}-{month_num}-{emp_suffix}"

        slip.status = "CONFIRMED"
        slip.is_visible_to_employee = True
        slip.confirmed_by = confirmed_by_id
        slip.confirmed_at = datetime.now(UTC).date()
        await slip.save()

        # Link associated incentives to this salary slip atomically
        from app.modules.incentives.models import IncentiveSlip
        # We find all slips that were included (those with salary_slip_id == None for this user)
        # Note: We already fetch these in regenerate/generate. 
        # For simplicity and safety, we link all currently 'unpaid' slips for this user.
        await IncentiveSlip.find(
            IncentiveSlip.user_id == slip.user_id,
            IncentiveSlip.salary_slip_id == None
        ).set({"salary_slip_id": slip.id})

        return await self._format_slip(slip)

    async def get_all_salary_slips(self) -> List[dict]:
        slips = await SalarySlip.find(SalarySlip.is_deleted == False).sort("-month").to_list()
        return await self._filter_and_format_slips(slips)

    async def get_user_salary_slips(self, user_id: PydanticObjectId, month: str = None, **kwargs):
        filters: dict = {"user_id": user_id, "is_deleted": False}
        if month:
            filters["month"] = month
            
        show_drafts = kwargs.get("show_drafts", True)
        only_visible = kwargs.get("only_visible", False)

        if not show_drafts:
            filters["status"] = "CONFIRMED"
        if only_visible:
            filters["is_visible_to_employee"] = True

        slips = await SalarySlip.find(filters).sort("-month").to_list()
        return await self._filter_and_format_slips(slips)

    async def _filter_and_format_slips(self, slips: List[SalarySlip]) -> List[dict]:
        from collections import defaultdict
        groups = defaultdict(list)
        for s in slips:
            groups[(str(s.user_id), s.month)].append(s)

        filtered = []
        for key, group in groups.items():
            # Deduplicate: prefer CONFIRMED, otherwise newest DRAFT
            group.sort(key=lambda x: str(x.id), reverse=True)
            confirmed = [s for s in group if s.status == "CONFIRMED"]
            keeper = confirmed[0] if confirmed else group[0]
            
            user = await User.get(PydanticObjectId(str(keeper.user_id)))
            if not user:
                continue
                
            # Filter out non-employee and test records
            role_val = getattr(user.role, 'value', str(user.role)).upper()
            if role_val in ["ADMIN", "CLIENT"]:
                continue
            name_lower = str(user.name or "").lower()
            email_lower = str(user.email or "").lower()
            if "test" in name_lower or "test" in email_lower:
                continue

            filtered.append(await self._format_slip(keeper))

        # Re-sort descending by month since dict grouping loses original sorting
        filtered.sort(key=lambda x: x.get("month", ""), reverse=True)
        return filtered

    async def preview_salary(self, user_id: PydanticObjectId, month: str, extra_deduction: float = 0.0, base_salary: float = None):
        """Calculate figures for preview without saving."""
        user = await User.get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        year, month_num = map(int, month.split('-'))
        import calendar
        _, days_in_month = calendar.monthrange(year, month_num)
        
        # Pull any existing draft to cross-reference currently linked incentives
        existing_draft = await SalarySlip.find_one(
            SalarySlip.user_id == user_id,
            SalarySlip.month == month,
            SalarySlip.status == "DRAFT",
            SalarySlip.is_deleted != True
        )
        current_slip_id = existing_draft.id if existing_draft else None

        month_leaves, total_leave_days, total_working_days = await self._get_leave_data(user_id, year, month_num)
        inc_data = await self._get_incentive_data(user_id, month, current_slip_id=current_slip_id)
        
        base = base_salary if base_salary is not None else (user.base_salary or 0.0)
        calc = self._compute_salary(base, total_leave_days, 
                                    inc_data["prev_inc"], inc_data["prev_slab"], 
                                    inc_data["curr_inc"], inc_data["curr_slab"], 
                                    extra_deduction, total_working_days)

        res = await self._format_slip_base(user)
        res.update({
            "month": month,
            "base_salary": base,
            "total_leave_days": total_leave_days,
            "working_days": calc['total_working_days'],
            "days_worked": calc['days_worked'],
            "days_in_month": days_in_month,
            "leave_deduction": calc['leave_deduction'],
            "prev_month_incentive": inc_data["prev_inc"],
            "prev_month_slab": inc_data["prev_slab"],
            "curr_month_incentive": inc_data["curr_inc"],
            "curr_month_slab": inc_data["curr_slab"],
            "incentive_amount": inc_data["total_inc"],
            "slab_bonus": inc_data["total_bonus"],
            "incentive_breakdown": inc_data["breakdown"],
            "total_earnings": calc['total_earnings'],
            "final_salary": calc['final_salary'],
            "extra_deduction": extra_deduction,
            "approved_leaves": [l.model_dump() for l in month_leaves],
            "has_existing_slip": existing_draft is not None,
            "existing_slip_id": str(existing_draft.id) if existing_draft else None,
            "existing_slip_status": existing_draft.status if existing_draft else None,
            "total_working_days_in_month": calc['total_working_days']
        })
        return res

    async def regenerate_salary_slip(self, salary_in: SalarySlipGenerate) -> dict:
        """Re-generates an existing DRAFT slip. CONFIRMED slips must be reverted first."""
        slip = await SalarySlip.find_one(
            SalarySlip.user_id == salary_in.user_id,
            SalarySlip.month == salary_in.month,
            SalarySlip.is_deleted != True
        )
        if not slip:
            # No existing slip — just create a fresh one
            return await self.generate_salary_slip(salary_in)

        # Guard: cannot regenerate a confirmed slip directly
        if slip.status == "CONFIRMED":
            raise HTTPException(
                status_code=400,
                detail="Slip is already confirmed. Use 'Revert to Draft' before regenerating."
            )

        year, month_num = map(int, salary_in.month.split('-'))
        
        month_leaves, total_leave_days, total_working_days = await self._get_leave_data(salary_in.user_id, year, month_num)
        
        # Fetch unlinked incentives + anything already linked to this slip
        inc_data = await self._get_incentive_data(slip.user_id, slip.month, current_slip_id=slip.id)
        
        base = salary_in.base_salary if salary_in.base_salary is not None else (slip.base_salary or 0.0)
        calc = self._compute_salary(base, total_leave_days, 
                                    inc_data["prev_inc"], inc_data["prev_slab"], 
                                    inc_data["curr_inc"], inc_data["curr_slab"], 
                                    salary_in.extra_deduction, total_working_days)

        slip.base_salary = base
        slip.unpaid_leaves = total_leave_days
        slip.deduction_amount = salary_in.extra_deduction
        slip.prev_month_incentive = inc_data["prev_inc"]
        slip.prev_month_slab = inc_data["prev_slab"]
        slip.curr_month_incentive = inc_data["curr_inc"]
        slip.curr_month_slab = inc_data["curr_slab"]
        slip.incentive_amount = inc_data["total_inc"]
        slip.slab_bonus = inc_data["total_bonus"]
        slip.incentive_breakdown = inc_data["breakdown"]
        slip.total_earnings = calc['total_earnings']
        slip.final_salary = calc['final_salary']
        # Regeneration always resets to DRAFT for review
        slip.status = "DRAFT"
        slip.is_visible_to_employee = False
        slip.confirmed_by = None
        slip.confirmed_at = None
        await slip.save()
        return await self._format_slip(slip)

    async def update_draft_slip(self, slip_id: PydanticObjectId, salary_in: SalarySlipGenerate) -> dict:
        """Manually update specific fields of a draft slip."""
        slip = await SalarySlip.get(slip_id)
        if not slip:
            raise HTTPException(status_code=404, detail="Slip not found")
        if slip.status != "DRAFT":
            raise HTTPException(status_code=400, detail="Only DRAFT slips can be manually updated here")

        year, month_num = map(int, slip.month.split('-'))

        # Recalculate leaves and incentives completely so the preview figures match the updated draft!
        month_leaves, total_leave_days, total_working_days = await self._get_leave_data(slip.user_id, year, month_num)
        inc_data = await self._get_incentive_data(slip.user_id, slip.month, current_slip_id=slip.id)

        # Handle overrides - use existing if not provided
        base = salary_in.base_salary if salary_in.base_salary is not None else (slip.base_salary or 0.0)
        
        calc = self._compute_salary(base, total_leave_days, 
                                    inc_data["prev_inc"], inc_data["prev_slab"], 
                                    inc_data["curr_inc"], inc_data["curr_slab"], 
                                    salary_in.extra_deduction, total_working_days)
        
        slip.base_salary = base
        slip.unpaid_leaves = total_leave_days
        slip.deduction_amount = salary_in.extra_deduction
        slip.prev_month_incentive = inc_data["prev_inc"]
        slip.prev_month_slab = inc_data["prev_slab"]
        slip.curr_month_incentive = inc_data["curr_inc"]
        slip.curr_month_slab = inc_data["curr_slab"]
        slip.incentive_amount = inc_data["total_inc"]
        slip.slab_bonus = inc_data["total_bonus"]
        slip.incentive_breakdown = inc_data["breakdown"]
        slip.total_earnings = calc['total_earnings']
        slip.final_salary = calc['final_salary']
        
        await slip.save()
        return await self._format_slip(slip)

    async def _format_slip(self, slip: SalarySlip) -> dict:
        """Helper to format a slip for API response with enriched data if needed."""
        data = slip.model_dump()
        # MongoDB ID mapping for consistency
        data["id"] = str(slip.id) if slip.id else None
        data["user_id"] = str(slip.user_id) if slip.user_id else None
        
        # Ensure incentive_breakdown is a dict
        if data.get("incentive_breakdown") is None:
            data["incentive_breakdown"] = {}
            
        from bson import ObjectId as BsonObjectId
        user = await User.find_one({"_id": BsonObjectId(str(slip.user_id))})
        if user:
            data["user_name"] = user.name or user.email
            data["employee_name"] = user.name or user.email
            
        try:
            year, month_num = map(int, slip.month.split('-'))
            total_working_days = await self._get_working_days_for_month(year, month_num)
            data["total_working_days_in_month"] = total_working_days
            daily_wage = (slip.base_salary or 0) / (total_working_days if total_working_days > 0 else 30)
            data["leave_deduction"] = round(daily_wage * (slip.unpaid_leaves or 0), 2)
        except:
            data["total_working_days_in_month"] = 30
            data["leave_deduction"] = 0.0

        return data

    async def revert_to_draft(self, slip_id: PydanticObjectId):
        """Reverts a confirmed slip back to DRAFT state."""
        slip = await SalarySlip.get(slip_id)
        if not slip:
            raise HTTPException(status_code=404, detail="Slip not found")
        
        slip.status = "DRAFT"
        slip.confirmed_by = None
        slip.confirmed_at = None
        # Optionally hide it from employee again when reverted to draft
        slip.is_visible_to_employee = False
        await slip.save()

        # Unlink associated incentives so they can be paid again
        from app.modules.incentives.models import IncentiveSlip
        await IncentiveSlip.find(IncentiveSlip.salary_slip_id == slip.id).set({"salary_slip_id": None})

        return await self._format_slip(slip)

    async def delete_salary_slip(self, slip_id: PydanticObjectId):
        """Deletes a salary slip (following system policy) and unlinks incentives."""
        slip = await SalarySlip.find_one(SalarySlip.id == slip_id, SalarySlip.is_deleted != True)
        if not slip:
            raise HTTPException(status_code=404, detail="Slip not found")
            
        from app.modules.settings.models import SystemSettings
        settings = await SystemSettings.find_one()
        delete_policy = settings.delete_policy if settings else "SOFT"

        # 1. Unlink incentives
        from app.modules.incentives.models import IncentiveSlip
        await IncentiveSlip.find(IncentiveSlip.salary_slip_id == slip.id).set({"salary_slip_id": None})

        # 2. Delete slip
        if delete_policy == "HARD":
            await slip.delete()
        else:
            slip.is_deleted = True
            await slip.save()

    async def generate_invoice_html(self, slip_id: PydanticObjectId) -> str:
        """Generates a professional printable HTML salary slip (payslip)."""
        slip = await SalarySlip.get(slip_id)
        if not slip:
            raise HTTPException(status_code=404, detail="Salary slip not found")

        from bson import ObjectId as BsonObjectId
        user = await User.find_one({"_id": BsonObjectId(str(slip.user_id))})
        if not user:
            class _FallbackUser:
                id = slip.user_id
                name = f"Employee #{str(slip.user_id)[-6:]}"
                email = ""
                role = "N/A"
                department = None
                phone = None
                employee_code = None
                joining_date = None
            user = _FallbackUser()

        logo_data_uri = ""
        try:
            _root = os.getcwd()
            _logo_white_path = os.path.join(_root, "frontend", "images", "white logo.png")
            _logo_path = os.path.join(_root, "frontend", "images", "logo.png")
            _chosen = _logo_white_path if os.path.exists(_logo_white_path) else _logo_path
            if os.path.exists(_chosen):
                with open(_chosen, "rb") as _f:
                    _ext = "png" if _chosen.endswith(".png") else "jpeg"
                    logo_data_uri = f"data:image/{_ext};base64," + base64.b64encode(_f.read()).decode()
        except Exception:
            pass

        year, month_num = map(int, slip.month.split('-'))
        _, days_in_month = calendar.monthrange(year, month_num)

        _, _, total_working_days = await self._get_leave_data(slip.user_id, year, month_num)
        working_days = max(0, total_working_days - float(slip.unpaid_leaves))
        month_name = f"{calendar.month_name[month_num]} {year}"

        slab_bonus = slip.slab_bonus or 0.0
        incentive_amount = slip.incentive_amount or 0.0
        extra_deduction = slip.deduction_amount or 0.0
        
        base_salary = float(slip.base_salary or 0.0)
        unpaid_leaves = float(slip.unpaid_leaves or 0.0)
        paid_leaves = float(slip.paid_leaves or 0.0)
        
        daily_wage = base_salary / total_working_days if total_working_days > 0 else 0
        leave_deduction = round(daily_wage * unpaid_leaves, 2)
        
        gross_salary = base_salary - leave_deduction
        gross_earnings = round(base_salary + incentive_amount + slab_bonus, 2)
        total_deductions = leave_deduction + extra_deduction
        month_name = f"{calendar.month_name[month_num]} {year}"

        raw_date = slip.confirmed_at or slip.generated_at
        try:
            issue_date_str = raw_date.strftime("%d %B %Y")
        except Exception:
            issue_date_str = str(raw_date)

        emp_name = user.name or user.email
        designation = str(user.role).replace('_', ' ').title()

        def amount_in_words(amount: float) -> str:
            if amount < 0:
                return "Negative " + amount_in_words(abs(amount))
            
            ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven",
                    "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen",
                    "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
            tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty",
                    "Sixty", "Seventy", "Eighty", "Ninety"]

            def below_thousand(n):
                if n == 0: return ""
                elif n < 20: return ones[n] + " "
                elif n < 100: return tens[n // 10] + (" " + ones[n % 10] if n % 10 else "") + " "
                else: return ones[n // 100] + " Hundred " + below_thousand(n % 100)

            rupees = int(amount)
            paise = round((amount - rupees) * 100)
            if rupees == 0 and paise == 0: return "Zero Rupees Only"
            
            result = ""
            if rupees >= 100000:
                result += below_thousand(rupees // 100000) + "Lakh "
                rupees %= 100000
            if rupees >= 1000:
                result += below_thousand(rupees // 1000) + "Thousand "
                rupees %= 1000
            result += below_thousand(rupees)
            result = result.strip() + " Rupees"
            
            if paise > 0:
                result += f" and {below_thousand(paise).strip()} Paise"
            
            return result + " Only"

        net_in_words = amount_in_words(float(slip.final_salary or 0.0))
        status_str = slip.status if isinstance(slip.status, str) else slip.status.value

        if not slip.slip_no:
            full_code = (user.employee_code if user and hasattr(user, "employee_code") and user.employee_code else str(slip.user_id)).strip()
            emp_suffix = full_code[-3:]
            slip.slip_no = f"PS-{year}-{month_num:02d}-{emp_suffix}"
            await slip.save()

        slip_no = slip.slip_no

        from app.modules.settings.models import SystemSettings
        settings = await SystemSettings.find_one()
        _DEFAULT_EMAIL = "hrmangukiya3494@gmail.com"
        _DEFAULT_PHONE = "8866005029"
        company_email = settings.payslip_email if (settings and settings.payslip_email) else _DEFAULT_EMAIL
        company_phone = settings.payslip_phone if (settings and settings.payslip_phone) else _DEFAULT_PHONE

        incentive_rows_html = ""
        
        prev_inc = float(getattr(slip, "prev_month_incentive", 0.0) or 0.0)
        prev_slab = float(getattr(slip, "prev_month_slab", 0.0) or 0.0)
        curr_inc = float(getattr(slip, "curr_month_incentive", 0.0) or 0.0)
        curr_slab = float(getattr(slip, "curr_month_slab", 0.0) or 0.0)
        
        if month_num == 1:
            prev_year, prev_m_num = year - 1, 12
        else:
            prev_year, prev_m_num = year, month_num - 1
        
        curr_m_name = f"{calendar.month_name[month_num]} {year}"
        prev_m_name = f"{calendar.month_name[prev_m_num]} {prev_year}"
        
        if prev_inc > 0:
            incentive_rows_html += f"""
            <div class="pay-row">
                <div class="pay-desc">Incentive ({prev_m_name})</div>
                <div class="pay-amt earn">&#8377;&nbsp;{prev_inc:,.2f}</div>
            </div>"""
        if prev_slab > 0:
            incentive_rows_html += f"""
            <div class="pay-row">
                <div class="pay-desc">Slab Bonus ({prev_m_name})</div>
                <div class="pay-amt earn">&#8377;&nbsp;{prev_slab:,.2f}</div>
            </div>"""
        if curr_inc > 0:
            incentive_rows_html += f"""
            <div class="pay-row">
                <div class="pay-desc">Incentive ({curr_m_name})</div>
                <div class="pay-amt earn">&#8377;&nbsp;{curr_inc:,.2f}</div>
            </div>"""
        if curr_slab > 0:
            incentive_rows_html += f"""
            <div class="pay-row">
                <div class="pay-desc">Slab Bonus ({curr_m_name})</div>
                <div class="pay-amt earn">&#8377;&nbsp;{curr_slab:,.2f}</div>
            </div>"""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{slip_no} &mdash; {emp_name} &mdash; {month_name}</title>
    <style>
        @page {{ size: A4; margin: 10mm 12mm; }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', Arial, Helvetica, sans-serif; background: #dde3ec; color: #1a1a1a; font-size: 12px; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
        .a4-page {{ width: 210mm; min-height: 297mm; background: #ffffff; margin: 20px auto; padding: 12mm 14mm 10mm; box-shadow: 0 6px 32px rgba(0,0,0,0.28); }}
        .top-banner {{ background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%); margin: -12mm -14mm 0; padding: 14px 14mm; display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }}
        .banner-left {{ display: flex; align-items: center; gap: 14px; }}
        .logo-img {{ height: 60px; width: auto; object-fit: contain; flex-shrink: 0; }}
        .banner-right {{ text-align: right; }}
        .payslip-badge {{ font-size: 22px; font-weight: 900; color: #fff; letter-spacing: 2px; text-transform: uppercase; opacity: 0.92; }}
        .payslip-period {{ font-size: 11px; color: rgba(255,255,255,0.75); margin-top: 3px; text-align: right; }}
        .company-sub {{ font-size: 10px; color: rgba(255,255,255,0.75); margin-top: 5px; letter-spacing: 0.4px; }}
        .meta-strip {{ display: grid; grid-template-columns: repeat(4, 1fr); border: 1.5px solid #e2e8f0; border-radius: 8px; overflow: hidden; margin-bottom: 14px; }}
        .meta-cell {{ padding: 10px 14px; border-right: 1px solid #e2e8f0; background: #f8fafc; }}
        .meta-cell:last-child {{ border-right: none; }}
        .meta-lbl {{ font-size: 9.5px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.7px; font-weight: 700; margin-bottom: 4px; }}
        .meta-val {{ font-size: 13px; font-weight: 800; color: #1e293b; word-break: break-word; }}
        .s-confirmed {{ color: #059669; }}
        .s-draft {{ color: #D97706; }}
        .section-box {{ border: 1.5px solid #e2e8f0; border-radius: 8px; overflow: hidden; margin-bottom: 14px; }}
        .section-hdr {{ background: #1e3a5f; color: #fff; padding: 8px 14px; font-size: 10.5px; font-weight: 800; letter-spacing: 1.2px; text-transform: uppercase; }}
        .emp-grid {{ display: grid; grid-template-columns: 1fr 1fr; }}
        .emp-col:first-child {{ border-right: 1px solid #e2e8f0; }}
        .emp-row {{ display: flex; justify-content: space-between; align-items: flex-start; padding: 8px 14px; border-bottom: 1px solid #f1f5f9; font-size: 12px; }}
        .emp-row:last-child {{ border-bottom: none; }}
        .e-lbl {{ color: #64748b; font-weight: 500; white-space: nowrap; margin-right: 8px; }}
        .e-val {{ font-weight: 700; color: #1e293b; text-align: right; word-break: break-word; max-width: 58%; }}
        .att-strip {{ display: grid; grid-template-columns: repeat(4, 1fr); background: #f0f7ff; border: 1.5px solid #bfdbfe; border-radius: 8px; overflow: hidden; margin-bottom: 14px; }}
        .att-cell {{ padding: 10px 12px; text-align: center; border-right: 1px solid #bfdbfe; }}
        .att-cell:last-child {{ border-right: none; }}
        .att-num {{ font-size: 20px; font-weight: 900; color: #1e40af; line-height: 1; }}
        .att-num.green {{ color: #059669; }}
        .att-num.red {{ color: #dc2626; }}
        .att-lbl {{ font-size: 9.5px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px; font-weight: 600; }}
        .pay-table-wrap {{ display: grid; grid-template-columns: 1fr 1fr; }}
        .pay-col:first-child {{ border-right: 1px solid #e2e8f0; }}
        .pay-col-hdr {{ background: #f8fafc; padding: 8px 14px; font-size: 10px; color: #64748b; font-weight: 700; letter-spacing: 0.7px; text-transform: uppercase; border-bottom: 1.5px solid #e2e8f0; display: flex; justify-content: space-between; }}
        .pay-row {{ display: flex; justify-content: space-between; align-items: center; padding: 8px 14px; border-bottom: 1px solid #f1f5f9; font-size: 12px; }}
        .pay-row:last-child {{ border-bottom: none; }}
        .pay-desc {{ color: #374151; }}
        .pay-desc small {{ display: block; font-size: 10px; color: #94a3b8; margin-top: 1px; }}
        .pay-amt {{ font-weight: 700; color: #1e293b; white-space: nowrap; }}
        .pay-amt.earn {{ color: #059669; }}
        .pay-amt.ded {{ color: #dc2626; }}
        .totals-row {{ display: grid; grid-template-columns: 1fr 1fr; border-top: 2px solid #e2e8f0; background: #f8fafc; }}
        .tot-cell {{ padding: 9px 14px; display: flex; justify-content: space-between; align-items: center; font-size: 12px; font-weight: 700; }}
        .tot-cell:first-child {{ border-right: 1px solid #e2e8f0; }}
        .tot-lbl {{ color: #374151; }}
        .tot-val.earn {{ color: #059669; }}
        .tot-val.ded {{ color: #dc2626; }}
        .net-bar {{ background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%); color: #fff; border-radius: 8px; padding: 14px 18px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }}
        .net-words-lbl {{ font-size: 9.5px; text-transform: uppercase; letter-spacing: 0.8px; opacity: 0.75; margin-bottom: 4px; }}
        .net-words {{ font-size: 11.5px; font-style: italic; max-width: 310px; line-height: 1.4; }}
        .net-amt-lbl {{ font-size: 9.5px; text-transform: uppercase; letter-spacing: 0.8px; opacity: 0.75; margin-bottom: 2px; text-align: right; }}
        .net-amt {{ font-size: 28px; font-weight: 900; text-align: right; letter-spacing: -0.5px; }}
        .sig-section {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-bottom: 14px; }}
        .sig-line {{ border-top: 1px dashed #999; margin-top: 36px; padding-top: 5px; font-size: 10.5px; color: #64748b; font-weight: 600; text-align: center; }}
        .slip-footer {{ text-align: center; font-size: 9.5px; color: #94a3b8; border-top: 1px solid #e2e8f0; padding-top: 10px; line-height: 1.6; }}
        .print-bar {{ width: 210mm; margin: 14px auto; display: flex; gap: 10px; justify-content: center; }}
        .btn-print {{ padding: 10px 32px; background: #2563eb; color: #fff; border: none; font-size: 13px; font-weight: 700; cursor: pointer; font-family: inherit; border-radius: 7px; letter-spacing: 0.3px; }}
        .btn-close-w {{ padding: 10px 28px; background: #fff; color: #2563eb; border: 2px solid #2563eb; font-size: 13px; font-weight: 700; cursor: pointer; font-family: inherit; border-radius: 7px; }}
        @media print {{ body {{ background: #fff; }} .a4-page {{ margin: 0; padding: 0; box-shadow: none; width: 100%; min-height: auto; }} .top-banner {{ margin: 0; padding: 14px 14mm; }} .print-bar {{ display: none; }} }}
    </style>
</head>
<body>
<div class="a4-page">
    <div class="top-banner">
        <div class="banner-left">
            {'<img class="logo-img" src="' + logo_data_uri + '" alt="Logo">' if logo_data_uri else '<div style="width:52px;height:52px;background:rgba(255,255,255,0.18);border:2px solid rgba(255,255,255,0.35);border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:900;color:#fff;">&#9670;</div>'}
        </div>
        <div class="banner-right">
            <div class="payslip-badge">Salary Slip</div>
            <div class="payslip-period">{month_name}</div>
            <div class="company-sub">{company_email} &nbsp;&middot;&nbsp; {company_phone}</div>
        </div>
    </div>
    <div class="meta-strip">
        <div class="meta-cell"><div class="meta-lbl">Slip No.</div><div class="meta-val">{slip_no}</div></div>
        <div class="meta-cell"><div class="meta-lbl">Issue Date</div><div class="meta-val">{issue_date_str}</div></div>
        <div class="meta-cell"><div class="meta-lbl">Status</div><div class="meta-val {'s-confirmed' if status_str == 'CONFIRMED' else 's-draft'}">{'&#10003; PAID' if status_str == 'CONFIRMED' else '&#9679; DRAFT'}</div></div>
        <div class="meta-cell"><div class="meta-lbl">Net Payable</div><div class="meta-val" style="color:#2563eb;">&#8377;&nbsp;{float(slip.final_salary or 0.0):,.2f}</div></div>
    </div>
    <div class="section-box">
        <div class="section-hdr">Employee Details</div>
        <div class="emp-grid">
            <div class="emp-col">
                <div class="emp-row"><span class="e-lbl">Name</span><span class="e-val">{emp_name}</span></div>
                <div class="emp-row"><span class="e-lbl">Designation</span><span class="e-val">{designation}</span></div>
                <div class="emp-row"><span class="e-lbl">Email</span><span class="e-val">{user.email}</span></div>
            </div>
            <div class="emp-col">
                <div class="emp-row"><span class="e-lbl">Employee ID</span><span class="e-val">EMP-{str(user.id)[-4:].upper()}</span></div>
                <div class="emp-row"><span class="e-lbl">Department</span><span class="e-val">{user.department or 'N/A'}</span></div>
                <div class="emp-row"><span class="e-lbl">Phone</span><span class="e-val">{user.phone or 'N/A'}</span></div>
            </div>
        </div>
    </div>
    <div class="att-strip">
        <div class="att-cell"><div class="att-num">{total_working_days}</div><div class="att-lbl">Total Work Days</div></div>
        <div class="att-cell"><div class="att-num">{working_days}</div><div class="att-lbl">Days Worked</div></div>
        <div class="att-cell"><div class="att-num green">{paid_leaves}</div><div class="att-lbl">Paid Leaves</div></div>
        <div class="att-cell"><div class="att-num red">{unpaid_leaves}</div><div class="att-lbl">Unpaid Leaves</div></div>
    </div>
    <div class="section-box">
        <div class="section-hdr">Earnings &amp; Deductions</div>
        <div class="pay-table-wrap">
            <div class="pay-col">
                <div class="pay-col-hdr"><span>Earnings</span><span>Amount (&#8377;)</span></div>
                <div class="pay-row"><div class="pay-desc">Basic Salary</div><div class="pay-amt earn">&#8377;&nbsp;{base_salary:,.2f}</div></div>
                {incentive_rows_html}
            </div>
            <div class="pay-col">
                <div class="pay-col-hdr"><span>Deductions</span><span>Amount (&#8377;)</span></div>
                <div class="pay-row"><div class="pay-desc">Leave Deduction <small>{unpaid_leaves} unpaid day(s)</small></div><div class="pay-amt ded">&#8377;&nbsp;{leave_deduction:,.2f}</div></div>
                <div class="pay-row"><div class="pay-desc">Other Deductions</div><div class="pay-amt ded">&#8377;&nbsp;{extra_deduction:,.2f}</div></div>
            </div>
        </div>
        <div class="totals-row">
            <div class="tot-cell"><span class="tot-lbl">Total Earnings</span><span class="tot-val earn">&#8377;&nbsp;{gross_earnings:,.2f}</span></div>
            <div class="tot-cell"><span class="tot-lbl">Total Deductions</span><span class="tot-val ded">&#8377;&nbsp;{total_deductions:,.2f}</span></div>
        </div>
    </div>
    <div class="net-bar">
        <div><div class="net-words-lbl">Net Salary in Words</div><div class="net-words">{net_in_words}</div></div>
        <div><div class="net-amt-lbl">Net Amount Payable</div><div class="net-amt">&#8377;&nbsp;{float(slip.final_salary or 0.0):,.2f}</div></div>
    </div>
    <div class="sig-section">
        <div class="sig-line" style="margin-top: 40px;">Employee Signature</div>
        <div class="sig-line" style="margin-top: 40px;">HR / Accounts</div>
        <div class="sig-line" style="margin-top: 40px;">Authorized Signatory</div>
    </div>
    <div class="slip-footer">Computer generated document. No signature required.</div>
</div>
<div class="print-bar">
    <button class="btn-close-w" onclick="window.top.location.href='/frontend/template/salary.html'">&#10005;&nbsp; Close</button>
    <button class="btn-print" onclick="window.print()">&#128438;&nbsp; Print / Save as PDF</button>
</div>
</body>
</html>"""
        return html

    async def generate_bulk_salary(self, month: str, extra_deduction_default: float = 0.0) -> dict:
        """Sequential bulk generation for all active employees (with optimized initial checks)."""
        from app.modules.users.models import User, UserRole
        from app.modules.salary.schemas import SalarySlipGenerate
        
        users = await User.find(
            User.is_active == True,
            User.is_deleted == False,
            User.role != UserRole.ADMIN,
            User.role != UserRole.CLIENT
        ).to_list()

        # --- OPTIMIZATION: Bulk Check Existing Slips ---
        user_ids = [u.id for u in users]
        existing_slips = await SalarySlip.find(
            In(SalarySlip.user_id, user_ids),
            SalarySlip.month == month,
            SalarySlip.is_deleted == False
        ).to_list()
        existing_user_ids = {s.user_id for s in existing_slips}

        generated = 0
        skipped = 0
        failed = 0
        failures = []

        for user in users:
            if user.id in existing_user_ids:
                skipped += 1
                continue

            try:
                await self.generate_salary_slip(SalarySlipGenerate(
                    user_id=user.id,
                    month=month,
                    extra_deduction=extra_deduction_default
                ))
                generated += 1
            except Exception as e:
                failed += 1
                failures.append({"user_id": str(user.id), "user_name": user.name or user.email, "error": str(e)})

        return {
            "month": month,
            "processed_count": len(users),
            "generated_count": generated,
            "skipped_count": skipped,
            "failed_count": failed,
            "failures": failures
        }

    async def _format_slip_base(self, user: User) -> dict:
        """Helper to return base employee data for salary response/preview."""
        return {
            "user_id": str(user.id),
            "employee_id": f"EMP-{str(user.id)[-4:].upper()}",
            "user_name": user.name or user.email,
            "designation": str(user.role).replace('_', ' ').title(),
            "department": user.department or "N/A",
            "email": user.email,
            "phone": user.phone or "N/A"
        }


