# backend/app/modules/meetings/models.py
import enum
from typing import Optional, List, Dict, Any
import datetime as dt
from datetime import UTC
from pydantic import Field
from beanie import Document, Indexed, PydanticObjectId

from app.core.enums import GlobalTaskStatus
# Import TodoPriority assuming it exists in your code
# from app.modules.todos.models import TodoPriority

class MeetingType(str, enum.Enum):
    IN_PERSON_FRIENDLY   = "In-Person"
    IN_PERSON_LEGACY     = "IN_PERSON"
    GOOGLE_MEET_FRIENDLY = "Google Meet"
    VIRTUAL_FRIENDLY     = "Virtual"
    
    # Legacy/Normalized variants
    GOOGLE_MEET = "GOOGLE_MEET"
    VIRTUAL     = "VIRTUAL"

class MeetingSummary(Document):
    title: Indexed(str)
    content: str
    date: dt.datetime = Field(default_factory=lambda: dt.datetime.now(UTC))

    status: GlobalTaskStatus = GlobalTaskStatus.OPEN
    meeting_type: Optional[str] = "In-Person"
    meet_link: Optional[str] = None

    # Google Calendar / AI pipeline
    calendar_event_id: Optional[str] = None
    transcript: Optional[str] = None
    ai_summary: Optional[Any] = None

    cancellation_reason: Optional[str] = None
    
    # Relationships
    client_id: Optional[PydanticObjectId] = None
    project_id: Optional[PydanticObjectId] = None
    host_id: Optional[PydanticObjectId] = None
    todo_id: Optional[PydanticObjectId] = None
    
    # M2M replacement: List of User Object IDs
    attendee_ids: List[PydanticObjectId] = Field(default_factory=list)

    is_deleted: bool = False
    reminder_sent: bool = False
    
    # Priority for Timetable pinning (using string fallback if enum is tricky to import initially)
    priority: Any = None

    class Settings:
        name = "srm_meeting_summaries"