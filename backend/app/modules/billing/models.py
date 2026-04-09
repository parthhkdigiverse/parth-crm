# backend/app/modules/billing/models.py
from typing import Optional
from datetime import datetime, UTC
from pydantic import Field
from beanie import Document, Indexed, PydanticObjectId

class Bill(Document):
    # Optional linkage (pre-existing lead/client)
    shop_id: Optional[PydanticObjectId] = None
    client_id: Optional[PydanticObjectId] = None

    # Client detail snapshot
    invoice_client_name: str
    invoice_client_phone: str
    invoice_client_email: Optional[str] = None
    invoice_client_address: Optional[str] = None
    invoice_client_org: Optional[str] = None

    # Financial
    amount: float = 12000.0
    payment_type: str = "PERSONAL_ACCOUNT"
    gst_type: str = "WITH_GST"
    invoice_series: str = "INV"
    invoice_sequence: int = 1
    requires_qr: bool = True
    
    # Soft Delete / Lifecycle
    is_deleted: bool = False
    is_archived: bool = False
    archived_by_id: Optional[PydanticObjectId] = None

    # Statuses
    invoice_status: str = "DRAFT"
    status: str = "PENDING"
    invoice_number: Optional[Indexed(str)] = None
    transaction_id: Optional[str] = None
    payment_gateway_status: Optional[str] = None
    whatsapp_sent: bool = False

    # Audit
    created_by_id: Optional[PydanticObjectId] = None
    verified_by_id: Optional[PydanticObjectId] = None
    verified_at: Optional[datetime] = None

    # Description
    service_description: Optional[str] = None
    billing_month: Optional[str] = None

    # Dynamically attached fields for frontend UI
    creator_name: Optional[str] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "srm_bills"
