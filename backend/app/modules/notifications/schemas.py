from typing import Optional
from datetime import datetime, timezone
from pydantic import field_serializer
from app.core.base_schema import MongoBaseSchema, PydanticObjectId

class NotificationRead(MongoBaseSchema):
    id: PydanticObjectId
    user_id: PydanticObjectId
    title: str
    message: str
    is_read: bool
    is_deleted: bool = False
    created_at: Optional[datetime] = None

    @field_serializer('created_at')
    def serialize_created_at(self, v: Optional[datetime]) -> Optional[str]:
        """
        Ensure created_at is always emitted as a UTC ISO-8601 string with a 'Z' suffix.
        Handles both naive datetimes (old rows before migration) and timezone-aware ones.
        """
        if v is None:
            return None
        if v.tzinfo is None:
            # Old naive row — was stored in UTC by the Python default; treat it as UTC
            v = v.replace(tzinfo=timezone.utc)
        else:
            v = v.astimezone(timezone.utc)
        return v.strftime('%Y-%m-%dT%H:%M:%SZ')
