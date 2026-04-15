import typing
import datetime
from beanie import PydanticObjectId
from app.core.base_schema import MongoBaseSchema

class TimelineEvent(MongoBaseSchema):
    id: PydanticObjectId | str | int
    title: str
    date: str | None = None # YYYY-MM-DD or full ISO
    user: str | None = None # Assignee/User name
    sh: int | None = None
    sm: int | None = None
    eh: int | None = None
    em: int | None = None
    loc: str | None = None
    
    # Original fields for reference
    event_type: str # VISIT, MEETING, TODO, TIMETABLE, DEMO
    status: str | None = None
    priority: str | None = None
    reference_id: PydanticObjectId | str | None = None
    description: str | None = None
    meet_url: str | None = None

    # New fields for generic calendar events
    start: str | None = None
    end: str | None = None
    backgroundColor: str | None = None
    borderColor: str | None = None
    textColor: str | None = None
    allDay: bool | None = None

class TimetableResponse(MongoBaseSchema):
    events: typing.List[TimelineEvent]

class TimetableEventBase(MongoBaseSchema):
    title: str
    assignee_name: str | None = None
    date: datetime.date
    start_time: str | None = None
    end_time: str | None = None
    location: str | None = None
    priority: str | None = "MEDIUM"
    status: str | None = "PENDING"

class TimetableEventCreate(TimetableEventBase):
    pass

class TimetableEventUpdate(MongoBaseSchema):
    title: str | None = None
    assignee_name: str | None = None
    date: datetime.date | None = None
    start_time: str | None = None
    end_time: str | None = None
    location: str | None = None
    priority: str | None = None
    status: str | None = None

class TimetableEventRead(TimetableEventBase):
    id: PydanticObjectId
    user_id: PydanticObjectId
