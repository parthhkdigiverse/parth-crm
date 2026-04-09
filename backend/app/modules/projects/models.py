# backend/app/modules/projects/models.py
from typing import Optional
from datetime import datetime, UTC
from pydantic import Field
from beanie import Document, Indexed, PydanticObjectId
from app.core.enums import GlobalTaskStatus

class Project(Document):
    name: Indexed(str)
    description: Optional[str] = None

    client_id: PydanticObjectId
    pm_id: PydanticObjectId

    status: GlobalTaskStatus = GlobalTaskStatus.OPEN

    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    budget: float = 0.0
    
    total_issues: int = 0
    resolved_issues: int = 0 
    progress_percentage: float = 0.0
    
    # UI Metadata fields mapped dynamically in the service layer
    client_name: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    project_type: Optional[str] = None
    pm_name: Optional[str] = None

    is_deleted: bool = False

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "srm_projects"
