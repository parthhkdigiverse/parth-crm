import typing
from typing import Optional, Dict, Any
import datetime
from pydantic import field_validator
from app.core.base_schema import MongoBaseSchema, PydanticObjectId

class BillCreate(MongoBaseSchema):
    # Client details (name + phone required)
    invoice_client_name: str
    invoice_client_phone: str
    invoice_client_email: str | None = None
    invoice_client_address: str | None = None
    invoice_client_org: str | None = None

    # Optional shop/lead linkage
    shop_id: PydanticObjectId | None = None

    # Financial
    amount: float | None = None
    payment_type: typing.Literal["BUSINESS_ACCOUNT", "PERSONAL_ACCOUNT", "CASH"]
    gst_type: typing.Literal["WITH_GST", "WITHOUT_GST"]
    service_description: str | None = "Harikrushn DigiVerse LLP Software – Annual Subscription"
    # CHANGE: Optional with auto-fill fallback in service.create_invoice() —
    # was `billing_month: str` which caused silent 422 on any non-wizard path
    billing_month: str | None = None  # e.g. "Feb 2026"
    transaction_id: str | None = None
    payment_gateway_status: str | None = None

    @field_validator('invoice_client_name')
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('Client name is required')
        return v.strip()

    @field_validator('invoice_client_phone')
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('Client phone is required')
        v = v.strip()
        # Basic validation for 10 digits
        digits = ''.join(filter(str.isdigit, v))
        if len(digits) == 10:
            return v
        elif len(digits) == 12 and digits.startswith("91"):
            return v
        else:
            raise ValueError('Client phone must be a valid 10-digit number (or 12-digit with 91 prefix) for WhatsApp')


class BillRead(MongoBaseSchema):
    id: PydanticObjectId
    shop_id: PydanticObjectId | None = None
    client_id: PydanticObjectId | None = None

    invoice_client_name: str | None = None
    invoice_client_phone: str | None = None
    invoice_client_email: str | None = None
    invoice_client_address: str | None = None
    invoice_client_org: str | None = None

    amount: float
    payment_type: str
    gst_type: str
    invoice_series: str
    invoice_sequence: int
    requires_qr: bool
    invoice_status: str
    status: str
    invoice_number: str | None = None
    whatsapp_sent: bool
    is_archived: bool = False

    service_description: Optional[str] = None
    billing_month: Optional[str] = None
    transaction_id: Optional[str] = None
    payment_gateway_status: Optional[str] = None

    shop_name: str | None = None
    client_name: str | None = None
    creator_name: Optional[str] = None

    created_by_id: PydanticObjectId | None = None
    verified_by_id: PydanticObjectId | None = None
    verified_at: datetime.datetime | None = None
    created_at: datetime.datetime

    # CRITICAL FIX: Without this field, Pydantic silently strips the `actions` dict
    # from every list response, making ALL action buttons (verify/archive/unarchive/delete)
    # invisible on the frontend. One missing line = all buttons gone.
    actions: Optional[Dict[str, Any]] = None

class BillingWorkflowResolveRequest(MongoBaseSchema):
    payment_type: typing.Literal["BUSINESS_ACCOUNT", "PERSONAL_ACCOUNT", "CASH"]
    gst_type: typing.Literal["WITH_GST", "WITHOUT_GST"]
    amount: float | None = None


class BillingWorkflowResolveResponse(MongoBaseSchema):
    payment_type: str
    gst_type: str
    requires_qr: bool
    amount: float
    base_amount: float
    gst_amount: float
    total_amount: float
    amount_source: str
    qr_available: bool
    qr_image_url: str | None = None
    payment_upi_id: str | None = None
    payment_account_name: str | None = None


class BillingInvoiceActionResponse(MongoBaseSchema):
    can_verify: bool
    can_send_whatsapp: bool
    can_archive: bool = False
    can_unarchive: bool = False
    can_delete_archived: bool = False
    can_refund: bool = False          # role-gated refund (was dropped in migration)
    allowed_verifier_roles: list[str]
