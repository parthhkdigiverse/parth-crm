# backend/app/modules/salary/models.py
import enum
from typing import Optional
from datetime import datetime, date, UTC
from pydantic import Field, field_validator
from beanie import Document, Indexed, PydanticObjectId

class LeaveType(str, enum.Enum):
    ANNUAL = "ANNUAL"
    SICK = "SICK"
    CASUAL = "CASUAL"
    UNPAID = "UNPAID"
    OTHER = "OTHER"

class DayType(str, enum.Enum):
    FULL = "FULL"
    HALF = "HALF"

class LeaveStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class SalaryStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"

class LeaveRecord(Document):
    user_id: PydanticObjectId
    start_date: date
    end_date: date
    leave_type: str = "CASUAL"
    day_type: str = "FULL"  # FULL or HALF
    reason: Optional[str] = None
    status: LeaveStatus = LeaveStatus.PENDING
    approved_by: Optional[PydanticObjectId] = None
    remarks: Optional[str] = None  # Admin remarks on rejection/approval
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_deleted: bool = False

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def _coerce_datetime_to_date(cls, v):
        if hasattr(v, "date"):
            return v.date()
        return v

    class Settings:
        name = "srm_leave_records"

class SalarySlip(Document):
    user_id: PydanticObjectId
    month: str  # YYYY-MM
    generated_at: date = Field(default_factory=lambda: datetime.now(UTC).date())

    base_salary: float
    paid_leaves: float = 0.0
    unpaid_leaves: float = 0.0
    deduction_amount: float = 0.0
    
    prev_month_incentive: float = 0.0
    prev_month_slab: float = 0.0
    curr_month_incentive: float = 0.0
    curr_month_slab: float = 0.0
    
    incentive_amount: float = 0.0 # total
    slab_bonus: float = 0.0 # total
    total_earnings: float = 0.0
    final_salary: float
    incentive_breakdown: Optional[dict] = None  # e.g. {"2026-04": 2000.0, "2026-05": 5000.0}

    # Workflow: DRAFT → CONFIRMED
    status: str = "CONFIRMED"
    confirmed_by: Optional[PydanticObjectId] = None
    confirmed_at: Optional[date] = None
    is_visible_to_employee: bool = False
    employee_remarks: Optional[str] = None
    manager_remarks: Optional[str] = None

    file_url: Optional[str] = None
    slip_no: Optional[str] = None  # e.g. PS-2026-04-001, set at confirmation
    is_deleted: bool = False

    @field_validator("confirmed_at", "generated_at", mode="before")
    @classmethod
    def _coerce_datetime_to_date(cls, v):
        if isinstance(v, datetime):
            return v.date()
        return v

    class Settings:
        name = "srm_salary_slips"

