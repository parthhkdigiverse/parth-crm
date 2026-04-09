# backend/app/modules/shops/models.py
import enum
from typing import Optional, List
from datetime import datetime, UTC
from pydantic import Field
from beanie import Document, Indexed, PydanticObjectId
from app.core.enums import MasterPipelineStage

class Shop(Document):
    name: Indexed(str)
    address: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    source: str = "Other"

    # Additional lead/project fields
    project_type: Optional[str] = None
    requirements: Optional[str] = None
    pipeline_stage: MasterPipelineStage = MasterPipelineStage.LEAD
    
    # Soft Delete / Archiving
    is_deleted: bool = False
    is_archived: bool = False
    archived_by_id: Optional[PydanticObjectId] = None

    # Relationships (Object IDs)
    owner_id: Optional[PydanticObjectId] = None
    area_id: Optional[PydanticObjectId] = None
    area_name: Optional[str] = None
    client_id: Optional[PydanticObjectId] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    assignment_status: str = "UNASSIGNED"
    assigned_user_ids: List[PydanticObjectId] = Field(default_factory=list)

    # UI/Display fields
    last_visitor_name: Optional[str] = None
    last_visit_status: Optional[str] = None

    # Lead Acceptance Tracking
    assigned_by_id: Optional[PydanticObjectId] = None
    accepted_at: Optional[datetime] = None
    created_by_id: Optional[PydanticObjectId] = None

    # PM Demo Pipeline
    project_manager_id: Optional[PydanticObjectId] = None
    demo_stage: int = 0
    demo_scheduled_at: Optional[datetime] = None
    demo_title: Optional[str] = None
    demo_type: Optional[str] = None
    demo_notes: Optional[str] = None
    demo_meet_link: Optional[str] = None
    scheduled_by_id: Optional[PydanticObjectId] = None
    
    # M2M Replacement (SQL's shop_assignments table)
    assigned_owner_ids: List[PydanticObjectId] = Field(default_factory=list)

    # Dynamic/Enriched attributes for Pydantic V2 and UI consistency
    project_manager_name: Optional[str] = None
    created_by_name: Optional[str] = None
    assigned_users: List[dict] = Field(default_factory=list)
    scheduled_by_name: Optional[str] = None
    archived_by_name: Optional[str] = None
    owner_name: Optional[str] = None
    pm_name: Optional[str] = None
    assigned_pm_name: Optional[str] = None
    client_organization: Optional[str] = None
    onboarding_pm_id: Optional[PydanticObjectId] = None
    onboarding_pm_name: Optional[str] = None

    class Settings:
        name = "srm_shops"

    # Back-compat alias
    @property
    def status(self):
        return self.pipeline_stage

    @status.setter
    def status(self, value):
        self.pipeline_stage = value
