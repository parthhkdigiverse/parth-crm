import re
from typing import Optional
from datetime import datetime
from pydantic import EmailStr, field_validator, BaseModel
from beanie import PydanticObjectId
from app.core.base_schema import MongoBaseSchema

class ClientBase(MongoBaseSchema):
    name: str
    phone: str | None = None
    email: EmailStr | None = None
    organization: str | None = None
    address: str | None = None
    project_type: str | None = None
    requirements: str | None = None

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if not v or v.strip() == "":
            return None
        digits_only = re.sub(r"\D", "", v)
        if len(digits_only) < 10:
            raise ValueError("Phone number must contain at least 10 digits")
        if not re.match(r"^[\d\+\-\s\(\)]+$", v):
            raise ValueError("Phone number contains invalid characters")
        return v

    @field_validator("email", mode="before")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if not v or v.strip() == "":
            return None
        return v

class ClientCreate(ClientBase):
    referral_code: str | None = None
    owner_id: PydanticObjectId | None = None

class ClientUpdate(ClientBase):
    name: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    organization: str | None = None
    address: str | None = None
    project_type: str | None = None
    requirements: str | None = None
    owner_id: PydanticObjectId | None = None
    pm_id: PydanticObjectId | None = None
    status: str | None = None
    is_active: bool | None = None


class ClientPMAssign(MongoBaseSchema):
    pm_id: PydanticObjectId

class ClientRead(MongoBaseSchema):
    id: PydanticObjectId
    name: str
    phone: str | None = None
    email: str | None = None
    organization: str | None = None
    pm_id: PydanticObjectId | None = None
    pm_name: str | None = None
    pm_assigned_by_name: str | None = None
    owner_id: PydanticObjectId | None = None
    address: str | None = None
    project_type: str | None = None
    requirements: str | None = None
    is_active: bool = True
    status: str = "ACTIVE"
    created_at: datetime | None = None


class PMWorkloadRead(BaseModel):
    pm_id: str
    pm_name: str | None = None
    pm_email: str | None = None
    role: str | None = None
    active_client_count: int


class ClientPMHistoryRead(MongoBaseSchema):
    id: PydanticObjectId
    client_id: PydanticObjectId
    pm_id: PydanticObjectId
    assigned_at: datetime
