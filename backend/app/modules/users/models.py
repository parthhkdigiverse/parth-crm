import enum
from typing import Optional, Dict, Any
from datetime import date
from pydantic import Field, field_validator  # Aa line dhyan thi chek karjo
from beanie import Document, Indexed

class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    SALES = "SALES"
    TELESALES = "TELESALES"
    PROJECT_MANAGER = "PROJECT_MANAGER"
    PROJECT_MANAGER_AND_SALES = "PROJECT_MANAGER_AND_SALES"
    CLIENT = "CLIENT"

class User(Document):
    email: Indexed(str, unique=True)
    hashed_password: str
    name: Optional[str] = None
    phone: Optional[str] = None
    role: UserRole = UserRole.TELESALES
    referral_code: Optional[str] = None
    
    is_active: bool = True
    is_deleted: bool = False
    preferences: Dict[str, Any] = Field(default_factory=dict)

    # --- Employee / HR Profile ---
    employee_code: Optional[str] = None
    joining_date: Optional[date] = None
    base_salary: float | None = None
    target: int | None = None
    incentive_enabled: bool = True
    department: Optional[str] = None

    # --- Validators (Aa nava code ma chhe, etle aa rakvu jaruri chhe) ---
    @field_validator("base_salary", mode="before")
    @classmethod
    def coerce_salary(cls, v):
        if v is None: return None
        try: return float(v)
        except (TypeError, ValueError): return 0.0

    @field_validator("target", mode="before")
    @classmethod
    def coerce_target(cls, v):
        if v is None: return None
        try: return int(v)
        except (TypeError, ValueError): return 0

    class Settings:
        name = "srm_users"