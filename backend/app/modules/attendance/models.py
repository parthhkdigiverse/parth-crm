# backend/app/modules/attendance/models.py
import datetime as dt
from typing import Optional
from pydantic import Field, field_validator
from beanie import Document, Indexed, PydanticObjectId

def get_ist_today():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).date()

class Attendance(Document):
    user_id: PydanticObjectId
    date: dt.date = Field(default_factory=get_ist_today)
    punch_in: Optional[dt.datetime] = None
    punch_out: Optional[dt.datetime] = None
    total_hours: float = 0.0

    @field_validator("total_hours", mode="before")
    @classmethod
    def coerce_total_hours(cls, v):
        if v is None:
            return 0.0
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0
    is_deleted: bool = False

    class Settings:
        name = "srm_attendance"
