# backend/app/modules/salary/models.py
import enum
from typing import Optional
from datetime import datetime, date, UTC
from pydantic import Field
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

    class Settings:
        name = "srm_leave_records"

class SalarySlip(Document):
    user_id: PydanticObjectId
    month: str  # YYYY-MM
    generated_at: date = Field(default_factory=lambda: datetime.now(UTC).date())

    base_salary: float
    paid_leaves: int = 0
    unpaid_leaves: int = 0
    deduction_amount: float = 0.0
    incentive_amount: float = 0.0
    slab_bonus: float = 0.0
    total_earnings: float = 0.0
    final_salary: float

    # Workflow: DRAFT → CONFIRMED
    status: str = "CONFIRMED"
    confirmed_by: Optional[PydanticObjectId] = None
    confirmed_at: Optional[date] = None
    is_visible_to_employee: bool = False
    employee_remarks: Optional[str] = None
    manager_remarks: Optional[str] = None

    file_url: Optional[str] = None
    is_deleted: bool = False

    class Settings:
        name = "srm_salary_slips"

