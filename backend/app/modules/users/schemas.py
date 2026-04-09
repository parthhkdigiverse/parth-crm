# backend/app/modules/users/schemas.py
import typing
import datetime
from pydantic import EmailStr, field_validator, model_validator
from beanie import PydanticObjectId
from app.core.base_schema import MongoBaseSchema
from app.modules.users.models import UserRole

class UserBase(MongoBaseSchema):
    email: EmailStr | None = None
    name: str | None = None
    phone: str | None = None
    role: UserRole | None = UserRole.TELESALES
    is_active: bool | None = True
    incentive_enabled: bool | None = True

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, v: typing.Any) -> typing.Any:
        if isinstance(v, str):
            return v.upper()
        return v

class UserCreate(UserBase):
    email: EmailStr
    name: str
    password: str
    employee_code: str | None = None
    joining_date: datetime.date | None = None
    base_salary: float | None = None
    target: int | None = None
    department: str | None = None

    @field_validator("email")
    @classmethod
    def check_email_deliverability(cls, v: str) -> str:
        from email_validator import validate_email, EmailNotValidError
        try:
            validate_email(v, check_deliverability=True)
            return v
        except EmailNotValidError as e:
            raise ValueError(f"Invalid or non-existent email domain: {str(e)}")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v

class UserUpdate(UserBase):
    password: str | None = None

class UserProfileUpdate(MongoBaseSchema):
    name: str | None = None
    phone: str | None = None
    password: str | None = None
    preferences: dict | None = None
    employee_code: str | None = None
    joining_date: datetime.date | None = None
    base_salary: float | None = None
    target: int | None = None
    incentive_enabled: bool | None = None
    department: str | None = None

    @field_validator("password")
    @classmethod
    def validate_password_profile(cls, v: typing.Optional[str]) -> typing.Optional[str]:
        if v is None:
            return v
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v

class EmployeeUpdate(UserProfileUpdate):
    role: UserRole | None = None
    is_active: bool | None = None

class UserRead(UserBase):
    id: PydanticObjectId
    employee_code: str | None = None
    joining_date: datetime.date | None = None
    base_salary: float | None = None
    target: int | None = None
    department: str | None = None
    referral_code: str | None = None
    preferences: dict | None = None
    
    @model_validator(mode="after")
    def populate_fallback_name(self) -> "UserRead":
        if not self.name:
            self.name = self.email.split("@")[0] if self.email else "Employee"
        return self
