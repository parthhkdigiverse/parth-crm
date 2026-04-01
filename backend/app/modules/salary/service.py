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

PAID_LEAVE_LIMIT = 1  # 1 free paid leave per month

class SalaryService:
    def __init__(self):
        # No db session needed in Beanie!
        pass

    async def _get_leave_data(self, user_id: PydanticObjectId, year: int, month_num: int):
        """Fetch approved leaves for a user in given year/month using Beanie find."""
        all_approved = await LeaveRecord.find(
            LeaveRecord.user_id == user_id,
            LeaveRecord.status == LeaveStatus.APPROVED,
            LeaveRecord.is_deleted == False
        ).to_list()
        
        # Manual date filtering for NoSQL context
        approved_leaves = [
            l for l in all_approved 
            if l.start_date.year == year and l.start_date.month == month_num
        ]

        def _count_days(leave) -> float:
            """Calendar days, halved for HALF day_type."""
            raw = (leave.end_date - leave.start_date).days + 1
            if getattr(leave, 'day_type', 'FULL') == 'HALF':
                return raw * 0.5
            return float(raw)

        unpaid_forced = sum(_count_days(l) for l in approved_leaves if getattr(l, 'leave_type', '') == 'UNPAID')
        other_leaves = sum(_count_days(l) for l in approved_leaves if getattr(l, 'leave_type', '') != 'UNPAID')
        
        paid_leaves = min(other_leaves, PAID_LEAVE_LIMIT)
        unpaid_leaves = max(0.0, other_leaves - PAID_LEAVE_LIMIT) + unpaid_forced

        return approved_leaves, (other_leaves + unpaid_forced), paid_leaves, unpaid_leaves

    async def _get_incentive_data(self, user_id: PydanticObjectId, month_str: str):
        """Fetch progressive incentive and slab bonus from IncentiveService."""
        from app.modules.incentives.service import IncentiveService
        
        service = IncentiveService()
        slips = await service.calculate_progressive_incentive(user_id, month_str)
        
        if not slips:
            return 0.0, 0.0

        incentive_only = 0.0
        slab_bonus = 0.0
        
        for slip in slips:
            bonus = slip.slab_bonus_amount or 0.0
            total = slip.total_incentive or 0.0
            incentive_only += (total - bonus)
            slab_bonus += bonus
            
        return round(incentive_only, 2), round(slab_bonus, 2)

    def _compute_salary(self, base: float, unpaid_leaves: float, incentive_amount: float,
                        slab_bonus: float, extra_deduction: float):
        """Standard Compute Engine for Salary Figures."""
        daily_wage = base / 30
        gross_salary = daily_wage * max(0, 30 - unpaid_leaves)
        leave_deduction = round(daily_wage * unpaid_leaves, 2)
        total_earnings = round(gross_salary + incentive_amount + slab_bonus, 2)
        final_salary = round(total_earnings - extra_deduction, 2)
        return {
            'daily_wage': daily_wage,
            'gross_salary': round(gross_salary, 2),
            'leave_deduction': leave_deduction,
            'total_earnings': total_earnings,
            'final_salary': final_salary,
        }

    # TODO: Implement MongoDB transactions for financial safety
    async def generate_salary_slip(self, salary_in: SalarySlipGenerate) -> dict:
        """Asynchronously generates a new DRAFT salary slip."""
        user = await User.get(salary_in.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Check for duplication
        existing = await SalarySlip.find_one(SalarySlip.user_id == salary_in.user_id, SalarySlip.month == salary_in.month)
        if existing:
            raise HTTPException(status_code=400, detail="Salary slip already exists")

        year, month_num = map(int, salary_in.month.split('-'))
        _, _, paid_leaves, unpaid_leaves = await self._get_leave_data(salary_in.user_id, year, month_num)
        inc_amt, slab_bonus = await self._get_incentive_data(salary_in.user_id, salary_in.month)
        
        base = salary_in.base_salary if salary_in.base_salary is not None else (user.base_salary or 0.0)
        calc = self._compute_salary(base, unpaid_leaves, inc_amt, slab_bonus, salary_in.extra_deduction)

        slip = SalarySlip(
            user_id=salary_in.user_id,
            month=salary_in.month,
            base_salary=base,
            paid_leaves=paid_leaves,
            unpaid_leaves=unpaid_leaves,
            deduction_amount=salary_in.extra_deduction,
            incentive_amount=inc_amt,
            slab_bonus=slab_bonus,
            total_earnings=calc['total_earnings'],
            final_salary=calc['final_salary'],
            status="DRAFT",
            generated_at=datetime.now(UTC).date()
        )
        await slip.insert()
        return slip.model_dump()

    async def confirm_salary_slip(self, slip_id: PydanticObjectId, confirmed_by_id: PydanticObjectId):
        """Confirms a draft slip, marking it for payment and making it visible."""
        slip = await SalarySlip.get(slip_id)
        if not slip: raise HTTPException(status_code=404, detail="Slip not found")
        
        slip.status = "CONFIRMED"
        slip.is_visible_to_employee = True
        slip.confirmed_by = confirmed_by_id
        slip.confirmed_at = datetime.now(UTC)
        await slip.save()
        return slip.model_dump()

    async def get_all_salary_slips(self) -> List[SalarySlip]:
        return await SalarySlip.find(SalarySlip.is_deleted == False).sort("-month").to_list()

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

        return await SalarySlip.find(filters).sort("-month").to_list()

    async def preview_salary(self, user_id: PydanticObjectId, month: str, extra_deduction: float = 0.0, base_salary: float = None):
        """Calculate figures for preview without saving."""
        user = await User.get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        year, month_num = map(int, month.split('-'))
        _, total_days, paid_leaves, unpaid_leaves = await self._get_leave_data(user_id, year, month_num)
        inc_amt, slab_bonus = await self._get_incentive_data(user_id, month)
        
        base = base_salary if base_salary is not None else (user.base_salary or 0.0)
        calc = self._compute_salary(base, unpaid_leaves, inc_amt, slab_bonus, extra_deduction)
        
        return {
            "user_id": str(user_id),
            "user_name": user.name or user.email,
            "month": month,
            "base_salary": base,
            "paid_leaves": paid_leaves,
            "unpaid_leaves": unpaid_leaves,
            "incentive_amount": inc_amt,
            "slab_bonus": slab_bonus,
            **calc
        }

    async def regenerate_salary_slip(self, salary_in: SalarySlipGenerate) -> dict:
        """Re-generates (updates) an existing draft or confirmed slip."""
        slip = await SalarySlip.find_one(SalarySlip.user_id == salary_in.user_id, SalarySlip.month == salary_in.month)
        if not slip:
            # If it doesn't exist, just generate it
            return await self.generate_salary_slip(salary_in)

        user = await User.get(salary_in.user_id)
        year, month_num = map(int, salary_in.month.split('-'))
        _, _, paid_leaves, unpaid_leaves = await self._get_leave_data(salary_in.user_id, year, month_num)
        inc_amt, slab_bonus = await self._get_incentive_data(salary_in.user_id, salary_in.month)
        
        base = salary_in.base_salary if salary_in.base_salary is not None else (user.base_salary or 0.0)
        calc = self._compute_salary(base, unpaid_leaves, inc_amt, slab_bonus, salary_in.extra_deduction)

        slip.base_salary = base
        slip.paid_leaves = paid_leaves
        slip.unpaid_leaves = unpaid_leaves
        slip.deduction_amount = salary_in.extra_deduction
        slip.incentive_amount = inc_amt
        slip.slab_bonus = slab_bonus
        slip.total_earnings = calc['total_earnings']
        slip.final_salary = calc['final_salary']
        
        await slip.save()
        return slip.model_dump()

    async def update_draft_slip(self, slip_id: PydanticObjectId, salary_in: SalarySlipGenerate) -> dict:
        """Manually update specific fields of a draft slip."""
        slip = await SalarySlip.get(slip_id)
        if not slip:
            raise HTTPException(status_code=404, detail="Slip not found")
        if slip.status != "DRAFT":
            raise HTTPException(status_code=400, detail="Only DRAFT slips can be manually updated here")

        calc = self._compute_salary(salary_in.base_salary, slip.unpaid_leaves, salary_in.incentive_amount, salary_in.slab_bonus, salary_in.extra_deduction)
        
        slip.base_salary = salary_in.base_salary
        slip.deduction_amount = salary_in.extra_deduction
        slip.incentive_amount = salary_in.incentive_amount
        slip.slab_bonus = salary_in.slab_bonus
        slip.total_earnings = calc['total_earnings']
        slip.final_salary = calc['final_salary']
        
        await slip.save()
        return slip.model_dump()

    async def _format_slip(self, slip: SalarySlip) -> dict:
        """Helper to format a slip for API response with enriched data if needed."""
        data = slip.model_dump()
        user = await User.get(slip.user_id)
        if user:
            data["user_name"] = user.name or user.email
            data["employee_name"] = user.name or user.email
        return data

    async def generate_invoice_html(self, slip_id: PydanticObjectId) -> str:
        """Generates a professional printable HTML salary slip (payslip)."""
        slip = await SalarySlip.get(slip_id)
        if not slip: raise HTTPException(status_code=404, detail="Salary slip not found")

        user = await User.get(slip.user_id)
        from app.modules.settings.models import SystemSettings
        settings = await SystemSettings.find_one()
        
        # Logo Embedding
        logo_data_uri = ""
        try:
             _root = os.getcwd()
             _logo_path = os.path.join(_root, "frontend", "images", "logo.png")
             if os.path.exists(_logo_path):
                 with open(_logo_path, "rb") as f:
                     logo_data_uri = f"data:image/png;base64,{base64.b64encode(f.read()).decode()}"
        except: pass

        month_display = datetime.strptime(slip.month, "%Y-%m").strftime("%B %Y")
        
        # Pay Calculation Breakdown
        gross_earnings = round(slip.base_salary + slip.incentive_amount + (slip.slab_bonus or 0.0), 2)
        total_deductions = round(gross_earnings - slip.final_salary, 2)
        
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: sans-serif; padding: 40px; color: #333; }}
                .header {{ display: flex; justify-content: space-between; border-bottom: 2px solid #2563eb; padding-bottom: 20px; }}
                .logo {{ height: 60px; }}
                .title {{ font-size: 24px; font-weight: bold; color: #2563eb; }}
                .meta-table {{ width: 100%; border-collapse: collapse; margin-top: 30px; }}
                .meta-table td {{ padding: 8px; border: 1px solid #ddd; }}
                .label {{ font-weight: bold; background: #f8fafc; }}
                .total-bar {{ background: #2563eb; color: #fff; padding: 15px; margin-top: 20px; font-size: 18px; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="header">
                <img class="logo" src="{logo_data_uri}">
                <div class="title">Payslip: {month_display}</div>
            </div>
            <table class="meta-table">
                <tr><td class="label">Employee</td><td>{user.name}</td><td class="label">Slip ID</td><td>{str(slip.id)}</td></tr>
                <tr><td class="label">Role</td><td>{user.role}</td><td class="label">Base Salary</td><td>₹{slip.base_salary:,.2f}</td></tr>
                <tr><td class="label">Paid Leaves</td><td>{slip.paid_leaves}</td><td class="label">Unpaid Leaves</td><td>{slip.unpaid_leaves}</td></tr>
            </table>
            <div class="total-bar">Net Salary Payable: ₹{slip.final_salary:,.2f}</div>
            
            <div style="margin-top: 30px; padding: 15px; border-top: 1px dashed #ddd; font-size: 12px; color: #666;">
                <div style="font-weight: bold; margin-bottom: 5px;">Company Contact for Queries:</div>
                <div>Email: {settings.payslip_email if settings else "hrmangukiya3494@gmail.com"}</div>
                <div>Phone: {settings.payslip_phone if settings else "8866005029"}</div>
            </div>

            <div style="margin-top: 20px; text-align: center; font-size: 10px; color: #999;">
                Computer generated document. No signature required.
            </div>
        </body>
        </html>
        """
        return html
