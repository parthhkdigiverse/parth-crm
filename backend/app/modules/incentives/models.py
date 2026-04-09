# backend/app/modules/incentives/models.py
from typing import Optional, Any
from datetime import datetime, UTC
from pydantic import Field, field_validator
from beanie import Document, Indexed, PydanticObjectId

class IncentiveSlab(Document):
    min_units: int = 1
    max_units: int = 10
    incentive_per_unit: float = 0.0
    slab_bonus: float = 0.0

    class Settings:
        name = "srm_incentive_slabs"

class EmployeePerformance(Document):
    user_id: PydanticObjectId
    period: str  # YYYY-MM
    closed_units: int = 0

    class Settings:
        name = "srm_employee_performances"

class IncentiveSlip(Document):
    user_id: PydanticObjectId
    period: str  # YYYY-MM

    target: int = 0
    achieved: int = 0
    percentage: float = 0.0

    @field_validator("target", "achieved", mode="before")
    @classmethod
    def coerce_int(cls, v):
        if v is None:
            return 0
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    @field_validator("percentage", mode="before")
    @classmethod
    def coerce_percentage(cls, v):
        if v is None:
            return 0.0
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0
    applied_slab: Any = Field(default=None)
    amount_per_unit: float = 0.0
    total_incentive: float

    slab_bonus_amount: float = 0.0
    is_visible_to_employee: bool = False
    employee_remarks: Optional[str] = None
    manager_remarks: Optional[str] = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "srm_incentive_slips"
