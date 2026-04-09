# backend/app/modules/auth/models.py
from datetime import datetime, UTC
from typing import Optional
from pydantic import Field
from beanie import Document, PydanticObjectId

class PasswordResetRequest(Document):
    user_id: PydanticObjectId
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: str = "PENDING"  # PENDING, RESOLVED
    resolved_by: Optional[PydanticObjectId] = None
    resolved_at: Optional[datetime] = None

    class Settings:
        name = "srm_password_reset_requests"
