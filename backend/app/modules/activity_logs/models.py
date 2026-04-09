# backend/app/modules/activity_logs/models.py
import enum
from typing import Optional, Any, Dict
from datetime import datetime, UTC
from pydantic import Field
from beanie import Document, PydanticObjectId

class ActionType(str, enum.Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    ASSIGN = "ASSIGN"
    UNASSIGN = "UNASSIGN"
    STATUS_CHANGE = "STATUS_CHANGE"
    RESCHEDULE = "RESCHEDULE"
    CANCEL = "CANCEL"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"

class EntityType(str, enum.Enum):
    CLIENT = "CLIENT"
    PROJECT = "PROJECT"
    ISSUE = "ISSUE"
    MEETING = "MEETING"
    LEAD = "LEAD"
    VISIT = "VISIT"
    REASSIGN = "REASSIGN"
    FEEDBACK = "FEEDBACK"
    USER = "USER"

class ActivityLog(Document):
    user_id: Any = None # Relaxed for legacy 0 IDs
    user_name: Optional[str] = None
    user_role: Any = "USER"
    action: Any = "UNKNOWN"
    entity_type: Any = "UNKNOWN"
    entity_id: Any = None
    old_data: Any = None
    new_data: Any = None
    ip_address: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "srm_activity_logs"
