from typing import Dict, Any
from beanie import PydanticObjectId
from app.core.base_schema import MongoBaseSchema

class SystemSettingsRead(MongoBaseSchema):
    id: PydanticObjectId
    feature_flags: Dict[str, Any]
    access_policy: Dict[str, Any] = {}
    delete_policy: str = "SOFT"
    payslip_email: str = "hrmangukiya3494@gmail.com"
    payslip_phone: str = "8866005029"

class SystemSettingsUpdate(MongoBaseSchema):
    feature_flags: Dict[str, Any] | None = None
    access_policy: Dict[str, Any] | None = None
    delete_policy: str | None = None
    payslip_email: str | None = None
    payslip_phone: str | None = None
