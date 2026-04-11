import typing
import datetime
from pydantic import BaseModel, model_validator, Field
from beanie import PydanticObjectId

from app.core.enums import GlobalTaskStatus
from app.modules.meetings.models import MeetingType


class MeetingSummaryBase(BaseModel):
    title: str
    content: typing.Optional[str] = None
    date: typing.Optional[datetime.datetime] = None
    client_id: typing.Optional[PydanticObjectId] = None
    project_id: typing.Optional[PydanticObjectId] = None
    meeting_type: typing.Optional[str] = "In-Person"

    model_config = {"from_attributes": True, "populate_by_name": True}


class MeetingSummaryCreate(BaseModel):
    title: str
    # content is optional from frontend; default to empty string so DB is happy
    content: typing.Optional[str] = Field(default="")
    date: typing.Optional[datetime.datetime] = None
    meeting_type: typing.Optional[str] = "In-Person"
    status: typing.Optional[GlobalTaskStatus] = GlobalTaskStatus.OPEN
    host_id: typing.Optional[PydanticObjectId] = None
    attendee_ids: typing.Optional[typing.List[PydanticObjectId]] = Field(default_factory=list)
    client_id: typing.Optional[PydanticObjectId] = None
    project_id: typing.Optional[PydanticObjectId] = None
    target_type: typing.Optional[str] = "CLIENT"   # CLIENT | PROJECT | INTERNAL | ALL_STAFF | ROLE_BASED
    target_role: typing.Optional[str] = None
    priority: typing.Optional[str] = "MEDIUM"

    @model_validator(mode="before")
    @classmethod
    def coerce_empty_content(cls, values):
        """Ensure content is never None/empty string in DB."""
        if isinstance(values, dict):
            if not values.get("content"):
                values["content"] = " "
        return values

    model_config = {"from_attributes": True, "populate_by_name": True}


class MeetingSummaryUpdateBase(BaseModel):
    title: typing.Optional[str] = None
    content: typing.Optional[str] = None
    date: typing.Optional[datetime.datetime] = None
    status: typing.Optional[GlobalTaskStatus] = None
    meeting_type: typing.Optional[str] = None
    meet_link: typing.Optional[str] = None
    priority: typing.Optional[str] = None

    model_config = {"from_attributes": True, "populate_by_name": True}


class MeetingSummaryUpdate(MeetingSummaryUpdateBase):
    pass


class MeetingCancel(BaseModel):
    reason: typing.Optional[str] = None


class MeetingReschedule(BaseModel):
    new_date: datetime.datetime


class MeetingSummaryRead(BaseModel):
    id: PydanticObjectId
    title: str
    content: typing.Optional[str] = None
    date: typing.Optional[datetime.datetime] = None
    client_id: typing.Optional[PydanticObjectId] = None
    project_id: typing.Optional[PydanticObjectId] = None
    meeting_type: typing.Optional[str] = None
    status: GlobalTaskStatus = GlobalTaskStatus.OPEN
    meet_link: typing.Optional[str] = None
    cancellation_reason: typing.Optional[str] = None
    todo_id: typing.Optional[PydanticObjectId] = None
    host_id: typing.Optional[PydanticObjectId] = None
    attendee_ids: typing.Optional[typing.List[PydanticObjectId]] = Field(default_factory=list)
    priority: typing.Optional[str] = None
    calendar_event_id: typing.Optional[str] = None

    model_config = {"from_attributes": True, "populate_by_name": True}
