# backend/app/modules/notifications/models.py
from typing import Optional
from datetime import datetime, UTC
from pydantic import Field
from beanie import Document, Indexed, PydanticObjectId

class Notification(Document):
    user_id: PydanticObjectId
    
    title: str
    message: str
    
    is_read: bool = False
    is_deleted: bool = False
    
    created_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "srm_notifications"
