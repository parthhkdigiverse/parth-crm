# backend/app/modules/reports/models.py
from datetime import datetime
from typing import Optional
from beanie import Document, PydanticObjectId
from pydantic import Field

class PerformanceNote(Document):
    employee_id: PydanticObjectId
    admin_id: PydanticObjectId
    admin_name: str
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "srm_performance_notes"
