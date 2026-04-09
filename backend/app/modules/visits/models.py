# backend/app/modules/visits/models.py
import enum
from typing import Optional
from datetime import datetime, UTC
from pydantic import Field, field_validator
from beanie import Document, Indexed, PydanticObjectId

class VisitStatus(str, enum.Enum):
    SATISFIED          = "SATISFIED"
    ACCEPT             = "ACCEPT"
    DECLINE            = "DECLINE"
    MISSED             = "MISSED"
    TAKE_TIME_TO_THINK = "TAKE_TIME_TO_THINK"
    OTHER              = "OTHER"
    COMPLETED          = "COMPLETED"
    CANCELLED          = "CANCELLED"
    SCHEDULED          = "SCHEDULED"
    DEMO_RESCHEDULED   = "DEMO_RESCHEDULED"
    MEETING_RESCHEDULED= "MEETING_RESCHEDULED"

class Visit(Document):
    shop_id: Optional[PydanticObjectId] = None
    user_id: PydanticObjectId
    
    status: VisitStatus = VisitStatus.SATISFIED
    remarks: Optional[str] = None
    decline_remarks: Optional[str] = None
    visit_date: Optional[datetime] = Field(default_factory=lambda: datetime.now(UTC))
    
    # Photo persistence
    photo_url: Optional[str] = None
    storefront_photo_url: Optional[str] = None
    selfie_photo_url: Optional[str] = None

    # Timer/Duration
    duration_seconds: Optional[int] = 0

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_deleted: bool = False

    # Dynamic/Enriched attributes for Pydantic V2 and UI consistency
    shop_name: Optional[str] = None
    area_name: Optional[str] = None
    user_name: Optional[str] = None
    project_manager_name: Optional[str] = None
    shop_status: Optional[str] = None
    shop_demo_stage: int = 0

    @field_validator("duration_seconds", mode="before")
    @classmethod
    def coerce_duration(cls, v):
        if v is None:
            return 0
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    @field_validator("shop_demo_stage", mode="before")
    @classmethod
    def coerce_demo_stage(cls, v):
        if v is None:
            return 0
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    class Settings:
        name = "srm_visits"
