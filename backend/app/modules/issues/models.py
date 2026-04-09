# backend/app/modules/issues/models.py
import enum
from typing import Optional
from datetime import datetime, UTC
from pydantic import Field
from beanie import Document, Indexed, PydanticObjectId

# Assuming GlobalTaskStatus is still in app.core.enums
from app.core.enums import GlobalTaskStatus

class IssueSeverity(str, enum.Enum):
    HIGH   = "HIGH"
    MEDIUM = "MEDIUM"
    LOW    = "LOW"

class Issue(Document):
    title: Indexed(str)
    description: Optional[str] = None
    status: GlobalTaskStatus = GlobalTaskStatus.OPEN
    severity: IssueSeverity = IssueSeverity.MEDIUM
    remarks: Optional[str] = None
    
    is_deleted: bool = False
    opened_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    
    # Relationships
    client_id: PydanticObjectId
    project_id: Optional[PydanticObjectId] = None
    reporter_id: PydanticObjectId
    assigned_to_id: Optional[PydanticObjectId] = None
    assigned_group: Optional[str] = None

    class Settings:
        name = "srm_issues"