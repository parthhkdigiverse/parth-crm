import typing
import datetime
from pydantic import field_validator, Field
from app.core.base_schema import MongoBaseSchema, PydanticObjectId
from app.modules.salary.models import LeaveStatus, LeaveType, DayType

class LeaveApplicationCreate(MongoBaseSchema):
    start_date: datetime.date
    end_date: datetime.date
    leave_type: str = "CASUAL"
    day_type: str = "FULL"  # FULL or HALF
    reason: str  # required

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Leave reason is required")
        return v.strip()

    @field_validator("leave_type")
    @classmethod
    def validate_leave_type(cls, v: str) -> str:
        valid = [lt.value for lt in LeaveType]
        if v not in valid:
            raise ValueError(f"leave_type must be one of {valid}")
        return v

    @field_validator("day_type")
    @classmethod
    def validate_day_type(cls, v: str) -> str:
        valid = [dt.value for dt in DayType]
        if v not in valid:
            raise ValueError(f"day_type must be one of {valid}")
        return v


class LeaveApproval(MongoBaseSchema):
    status: LeaveStatus  # APPROVED or REJECTED
    remarks: str | None = None  # Admin remarks (reason for rejection etc.)


class LeaveRecordRead(MongoBaseSchema):
    id: PydanticObjectId
    user_id: PydanticObjectId
    start_date: datetime.date
    end_date: datetime.date
    leave_type: str = "CASUAL"
    day_type: str = "FULL"
    reason: str | None = None
    status: LeaveStatus
    remarks: str | None = None
    user_name: str | None = None
    approver_name: str | None = None
    approved_by: PydanticObjectId | None = None
    created_at: typing.Any
    updated_at: typing.Any


# Salary Schemas
class SalarySlipGenerate(MongoBaseSchema):
    user_id: PydanticObjectId
    month: str  # YYYY-MM
    extra_deduction: float = 0.0  # Admin-applied manual deduction
    base_salary: float | None = None  # Override employee profile base salary for this slip
    incentive_amount: float | None = None
    slab_bonus: float | None = None


class SalaryPreviewResponse(MongoBaseSchema):
    user_id: PydanticObjectId
    user_name: str
    month: str
    base_salary: float
    working_days: int
    total_leave_days: int
    paid_leaves: float
    unpaid_leaves: float
    leave_deduction: float
    incentive_amount: float
    slab_bonus: float
    extra_deduction: float
    total_earnings: float
    final_salary: float
    approved_leaves: typing.List[typing.Any]
    has_existing_slip: bool = False
    existing_slip_id: str | None = None
    existing_slip_status: str | None = None


class SalarySlipRead(MongoBaseSchema):
    id: PydanticObjectId
    user_id: PydanticObjectId
    month: str
    base_salary: float
    paid_leaves: float
    unpaid_leaves: float
    deduction_amount: float
    incentive_amount: float
    slab_bonus: float = 0.0
    total_earnings: float
    final_salary: float
    status: str = "CONFIRMED"
    confirmed_by: PydanticObjectId | None = None
    is_visible_to_employee: bool = True
    employee_remarks: str | None = None
    manager_remarks: str | None = None
    user_name: str | None = None
    confirmer_name: str | None = None
    generated_at: datetime.date
    slip_no: str | None = None


class SalaryBulkGenerateRequest(MongoBaseSchema):
    month: str  # YYYY-MM
    extra_deduction_default: float = 0.0

class SalaryBulkGenerateResponse(MongoBaseSchema):
    month: str
    processed_count: int
    generated_count: int
    skipped_count: int
    failed_count: int
    failures: list[dict] = []
