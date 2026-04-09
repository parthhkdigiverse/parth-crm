import typing
import datetime
from pydantic import BaseModel
from beanie import PydanticObjectId
from app.core.base_schema import MongoBaseSchema

from app.core.enums import GlobalTaskStatus
from app.modules.meetings.models import MeetingType


class MeetingSummaryBase(BaseModel):
    title: str
    content: str
    date: typing.Optional[datetime.datetime] = None
    client_id: typing.Optional[PydanticObjectId] = None
    meeting_type: typing.Optional[str] = "In-Person"


class MeetingSummaryCreate(BaseModel):
    title: str
    content: str
    date: typing.Optional[datetime.datetime] = None
    meeting_type: typing.Optional[str] = "In-Person"
    status: typing.Optional[GlobalTaskStatus] = GlobalTaskStatus.OPEN
    host_id: typing.Optional[PydanticObjectId] = None
    attendee_ids: typing.Optional[list[PydanticObjectId]] = []
    client_id: typing.Optional[PydanticObjectId] = None
    target_type: typing.Optional[str] = "CLIENT" # CLIENT, ALL_STAFF, ROLE_BASED
    target_role: typing.Optional[str] = None
    priority: typing.Any = None


class MeetingSummaryUpdateBase(BaseModel):
    title: typing.Optional[str] = None
    content: typing.Optional[str] = None
    date: typing.Optional[datetime.datetime] = None
    status: typing.Optional[GlobalTaskStatus] = None
    meeting_type: typing.Optional[str] = None
    meet_link: typing.Optional[str] = None


class MeetingSummaryUpdate(MeetingSummaryUpdateBase):
    pass


class MeetingCancel(BaseModel):
    reason: typing.Optional[str] = None


class MeetingReschedule(BaseModel):
    new_date: datetime.datetime


class MeetingSummaryRead(MeetingSummaryBase):
    id: PydanticObjectId
    status: GlobalTaskStatus
    client_id: typing.Optional[PydanticObjectId] = None
    meet_link: typing.Optional[str] = None
    cancellation_reason: typing.Optional[str] = None
    todo_id: typing.Optional[PydanticObjectId] = None
    host_id: typing.Optional[PydanticObjectId] = None
    attendee_ids: typing.Optional[list[PydanticObjectId]] = []
    priority: typing.Any = None
