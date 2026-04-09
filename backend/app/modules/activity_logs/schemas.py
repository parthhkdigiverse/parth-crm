# backend/app/modules/activity_logs/schemas.py
from typing import Any
from datetime import datetime
from beanie import PydanticObjectId
from app.core.base_schema import MongoBaseSchema

class ActivityLogBase(MongoBaseSchema):
    user_id: Any | None = None # Relaxed for legacy 0 IDs
    user_role: str
    action: Any
    entity_type: Any
    entity_id: Any
    old_data: Any | None = None
    new_data: Any | None = None
    ip_address: str | None = None

class ActivityLogCreate(ActivityLogBase):
    pass

class ActivityLogResponse(ActivityLogBase):
    id: PydanticObjectId
    created_at: datetime
    user_name: str | None = None
