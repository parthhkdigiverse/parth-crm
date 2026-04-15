import typing
import datetime
from beanie import PydanticObjectId
from app.core.base_schema import MongoBaseSchema

class AttendanceBase(MongoBaseSchema):
    user_id: PydanticObjectId
    date: datetime.date
    punch_in: datetime.datetime | None = None
    punch_out: datetime.datetime | None = None
    total_hours: float = 0.0

class AttendanceCreate(AttendanceBase):
    pass

class AttendanceResponse(AttendanceBase):
    id: PydanticObjectId

class AttendanceLog(MongoBaseSchema):
    id: PydanticObjectId
    punch_in: datetime.datetime | None = None
    punch_out: datetime.datetime | None = None
    total_hours: float = 0.0

class PunchStatus(MongoBaseSchema):
    is_punched_in: bool
    last_punch: datetime.datetime | None = None
    last_punch_ts: float | None = None  # Epoch milliseconds
    first_punch_in: datetime.datetime | None = None
    first_punch_in_ts: float | None = None  # Epoch milliseconds
    today_hours: float = 0.0
    today_hours_secs: float = 0.0
    completed_hours_secs: float = 0.0
    week_hours: float = 0.0
    month_hours: float = 0.0


class AttendanceDaySummary(MongoBaseSchema):
    date: datetime.date
    user_id: PydanticObjectId | None = None
    user_name: str | None = None
    first_punch_in: datetime.datetime | None = None
    last_punch_out: datetime.datetime | None = None
    total_hours: float = 0.0
    day_status: str = "PRESENT"  # PRESENT | HALF | ABSENT | OFF
    is_punched_in: bool = False
    leave_status: str | None = None


class AttendanceSummaryResponse(MongoBaseSchema):
    start_date: datetime.date
    end_date: datetime.date
    total_hours: float = 0.0
    records: typing.List[AttendanceDaySummary]


class AttendanceSettings(MongoBaseSchema):
    absent_hours_threshold: float = 0.0
    half_day_hours_threshold: float = 4.0
    weekly_off_saturday: str = "FULL"  # NONE | HALF | FULL
    weekly_off_sunday: str = "FULL"  # NONE | HALF | FULL
    official_holidays: typing.List[datetime.date] = []
