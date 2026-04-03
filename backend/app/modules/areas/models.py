# backend/app/modules/areas/models.py
from typing import Optional, List
from datetime import datetime, UTC
from pydantic import Field
from beanie import Document, Indexed, PydanticObjectId

class Area(Document):
    name: Indexed(str)
    description: Optional[str] = None
    pincode: Optional[str] = None
    city: Optional[str] = None
    assigned_user_id: Optional[PydanticObjectId] = None
    
    # Coordinates
    lat: Optional[float] = None
    lng: Optional[float] = None
    
    # Soft Delete / Archiving
    is_deleted: bool = False
    is_archived: bool = False 
    archived_by_id: Optional[PydanticObjectId] = None
    archived_by_name: Optional[str] = None
    created_by_name: Optional[str] = None
    
    assignment_status: str = "UNASSIGNED"
    
    # Lead Acceptance Tracking
    assigned_by_id: Optional[PydanticObjectId] = None
    accepted_at: Optional[datetime] = None
    created_by_id: Optional[PydanticObjectId] = None
    
    # Advanced Targeting
    radius_meters: int = 500
    shop_limit: int = 20
    priority_level: str = "MEDIUM"
    auto_discovery_enabled: bool = False
    target_categories: Optional[List[str]] = None
    
    shops_count: int = 0
    # M2M Replacement (SQL's area_assignments table)
    assigned_user_ids: List[PydanticObjectId] = Field(default_factory=list)
    assigned_users: List[dict] = Field(default_factory=list) # For UI enrichment

    class Settings:
        name = "areas"
