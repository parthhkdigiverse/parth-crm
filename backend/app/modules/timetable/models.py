# backend/app/modules/timetable/models.py
from typing import Optional
import datetime as dt
from beanie import Document, Indexed, PydanticObjectId
from app.modules.todos.models import TodoPriority

class TimetableEvent(Document):
    user_id: PydanticObjectId
    
    title: str
    assignee_name: Optional[str] = None
    date: dt.date
    start_time: dt.time
    end_time: dt.time
    location: Optional[str] = None
    
    priority: TodoPriority = TodoPriority.MEDIUM

    is_deleted: bool = False

    class Settings:
        name = "srm_timetable_events"
        bson_encoders = {
            dt.time: str,
            dt.date: lambda d: dt.datetime.combine(d, dt.time.min, tzinfo=dt.timezone.utc)
        }
