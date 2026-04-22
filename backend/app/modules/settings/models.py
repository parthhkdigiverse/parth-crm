# backend/app/modules/settings/models.py
from typing import Dict, Any, Optional, Union, List
from beanie import Document, Indexed
from pydantic import Field

class SystemSettings(Document):
    feature_flags: Dict[str, Any] = Field(default_factory=dict)
    access_policy: Dict[str, Any] = Field(default_factory=dict)
    policy_version: int = 1
    delete_policy: Optional[str] = "SOFT"
    payslip_email: Optional[str] = "hrmangukiya3494@gmail.com"
    payslip_phone: Optional[str] = "8866005029"
    saturday_policy: Optional[str] = "FULL_WORKING"  # FULL_OFF, HALF_WORKING, FULL_WORKING, ALTERNATE, SECOND_AND_FOURTH_OFF

    class Settings:
        name = "srm_system_settings"

class AppSetting(Document):
    key: Indexed(str, unique=True)
    value: Union[str, List[Any], Dict[str, Any], int, float]

    class Settings:
        name = "srm_app_settings"
