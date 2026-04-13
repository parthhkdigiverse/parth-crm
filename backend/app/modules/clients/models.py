# backend/app/modules/clients/models.py
from typing import Optional, List
from datetime import datetime, UTC
from pydantic import BaseModel, Field
from beanie import Document, Indexed, PydanticObjectId
from pymongo import IndexModel

class ClientPMHistory(BaseModel):
    """Embedded sub-document for tracking PM assignment history"""
    pm_id: PydanticObjectId
    assigned_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class Client(Document):
    name: Indexed(str)
    email: Optional[str] = None
    phone: Optional[str] = None
    organization: Optional[str] = None
    address: Optional[str] = None
    project_type: Optional[str] = None
    requirements: Optional[str] = None
    referral_code: Optional[str] = None
    
    # Relationships (Stored as Object IDs)
    referred_by_id: Optional[PydanticObjectId] = None
    owner_id: Optional[PydanticObjectId] = None
    pm_id: Optional[PydanticObjectId] = None
    pm_assigned_by_id: Optional[PydanticObjectId] = None
    pm_name: Optional[str] = None
    
    # Embedded History
    pm_history: List[ClientPMHistory] = Field(default_factory=list)
    archived_by_ids: List[PydanticObjectId] = Field(default_factory=list)

    is_active: bool = True
    status: Indexed(str) = "ACTIVE"  # ACTIVE, REFUNDED, ARCHIVED
    is_deleted: bool = False
    created_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "srm_clients"
        indexes = [
            IndexModel(
                [("phone", 1)], 
                unique=True, 
                partialFilterExpression={"phone": {"$type": "string"}}
            ),
        ]

