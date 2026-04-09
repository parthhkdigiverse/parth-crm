# backend/app/modules/payments/models.py
import enum
from typing import Optional
from datetime import datetime, UTC
from pydantic import Field
from beanie import Document, Indexed, PydanticObjectId

class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"

class Payment(Document):
    client_id: PydanticObjectId
    amount: float
    qr_code_data: Optional[str] = None # Could store URL or text
    status: PaymentStatus = PaymentStatus.PENDING
    generated_by_id: PydanticObjectId
    verified_by_id: Optional[PydanticObjectId] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_deleted: bool = False
    verified_at: Optional[datetime] = None

    class Settings:
        name = "srm_payments"
