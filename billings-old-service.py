# backend/app/modules/billing/service.py
from typing import Optional, List, Dict, Any
from beanie import PydanticObjectId
from beanie.operators import In, Or
from fastapi import HTTPException, Request
from app.modules.billing.models import Bill
from app.modules.billing.schemas import BillCreate, BillingWorkflowResolveRequest
from app.modules.clients.models import Client
from app.modules.settings.models import AppSetting
from app.modules.users.models import User, UserRole
from app.modules.notifications.models import Notification
from app.core.config import settings
from app.utils.notify_helpers import create_notification, notify_admins
import datetime
from datetime import UTC
import uuid
import hmac as _hmac
import hashlib
from urllib.parse import quote
import json
import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

class BillingService:
    def __init__(self):
        # No db session needed in Beanie!
        pass

    # ─────────────────────────────── helpers ────────────────────────────────

    async def _get_setting(self, key: str, default: str = "") -> str:
        row = await AppSetting.find_one({"key": key})
        return row.value if row and row.value is not None else default

    async def _set_setting(self, key: str, value: str) -> None:
        row = await AppSetting.find_one({"key": key})
        if row:
            row.value = value
            await row.save()
        else:
            new_setting = AppSetting(key=key, value=value)
            await new_setting.insert()

    async def _next_invoice_number(self, gst_type: str) -> tuple[str, str, int]:
        year = datetime.datetime.now(UTC).year
        if gst_type == "WITHOUT_GST":
            seq_key = "invoice_seq_without_gst"
            series = "PINV"
            prefix = "PInv"
        else:
            seq_key = "invoice_seq_with_gst"
            series = "INV"
            prefix = "Inv"

        start_str = await self._get_setting(seq_key, "1")
        start = int(start_str or "1")
        current = max(start, 1)

        while True:
            invoice_number = f"{prefix}/{year}/{current:03d}"
            exists = await Bill.find_one(Bill.invoice_number == invoice_number)
            if not exists:
                break
            current += 1

        # Persist the next sequence pointer
        await self._set_setting(seq_key, str(current + 1))
        return invoice_number, series, current

    def _current_role_name(self, current_user: User) -> str:
        return current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)

    async def _has_invoice_permission(self, current_user: User, setting_key: str, default_roles: str) -> bool:
        raw_val = await self._get_setting(setting_key, default_roles)
        raw = (raw_val or default_roles).strip()
        roles = {r.strip().upper() for r in raw.split(",") if r.strip()}
        if not roles:
            roles = {r.strip().upper() for r in default_roles.split(",") if r.strip()}
        return self._current_role_name(current_user) in roles

    async def _can_verify(self, current_user: User) -> bool:
        return await self._has_invoice_permission(current_user, "invoice_verifier_roles", "ADMIN")

    async def _can_send(self, current_user: User) -> bool:
        _default = "ADMIN,SALES,TELESALES,PROJECT_MANAGER_AND_SALES"
        return await self._has_invoice_permission(current_user, "invoice_sender_roles", _default)

    async def _allowed_verifier_roles(self) -> set[str]:
        raw_val = await self._get_setting("invoice_verifier_roles", "ADMIN")
        raw = (raw_val or "ADMIN").strip()
        roles = {r.strip().upper() for r in raw.split(",") if r.strip()}
        return roles or {"ADMIN"}

    async def _allowed_sender_roles(self) -> set[str]:
        _default = "ADMIN,SALES,TELESALES,PROJECT_MANAGER_AND_SALES"
        raw_val = await self._get_setting("invoice_sender_roles", _default)
        raw = (raw_val or _default).strip()
        roles = {r.strip().upper() for r in raw.split(",") if r.strip()}
        return roles or {r.strip().upper() for r in _default.split(",")}

    async def _allowed_invoice_creator_roles(self) -> set[str]:
        _default = "ADMIN,SALES,TELESALES,PROJECT_MANAGER_AND_SALES"
        raw_val = await self._get_setting("invoice_creator_roles", _default)
        raw = (raw_val or _default).strip()
        roles = {r.strip().upper() for r in raw.split(",") if r.strip()}
        return roles or {"ADMIN", "SALES", "TELESALES", "PROJECT_MANAGER_AND_SALES"}

    async def _can_create_invoice(self, current_user: User) -> bool:
        role_name = self._current_role_name(current_user)
        creator_roles = await self._allowed_invoice_creator_roles()
        return role_name in creator_roles

    @staticmethod
    def _can_archive_invoice(current_user: User, bill: Bill) -> bool:
        if current_user.role == UserRole.ADMIN:
            return True
        return bill.created_by_id == current_user.id

    def _validate_payment_mode(self, payment_type: str, gst_type: str) -> None:
        if payment_type == "BUSINESS_ACCOUNT" and gst_type != "WITH_GST":
            raise HTTPException(status_code=400, detail="Business account payments must be WITH_GST")
        if payment_type not in {"BUSINESS_ACCOUNT", "PERSONAL_ACCOUNT", "CASH"}:
            raise HTTPException(status_code=400, detail="Invalid payment type")
        if gst_type not in {"WITH_GST", "WITHOUT_GST"}:
            raise HTTPException(status_code=400, detail="Invalid GST type")

    async def get_invoice_defaults(self) -> dict:
        keys = [
            "invoice_default_amount", "personal_without_gst_default_amount", "invoice_terms_conditions",
            "business_payment_upi_id", "business_payment_account_name", "business_payment_qr_image_url",
            "business_payment_bank_name", "business_payment_account_number", "business_payment_ifsc", "business_payment_branch",
            "personal_payment_upi_id", "personal_payment_account_name", "personal_payment_qr_image_url",
            "personal_payment_bank_name", "personal_payment_account_number", "personal_payment_ifsc", "personal_payment_branch",
            "payment_upi_id", "payment_account_name", "payment_qr_image_url", "payment_bank_name", "payment_account_number", "payment_ifsc", "payment_branch",
            "company_name", "company_address", "company_header_image_details", "company_phone", "company_email", "company_gstin", "company_pan", "company_cin", "company_cst_code",
            "invoice_header_bg", "invoice_seq_with_gst", "invoice_seq_without_gst", "invoice_verifier_roles", "invoice_sender_roles", "invoice_creator_roles", "whatsapp_invoice_caption",
        ]
        rows = await AppSetting.find({"key": {"$in": keys}}).to_list()
        mapping = {r.key: r.value for r in rows}

        def _to_float(v: str | None, fb: float) -> float:
            try: return float(v) if v not in (None, "") else fb
            except: return fb

        def _to_int(v: str | None, fb: int) -> int:
            try: return int(v) if v not in (None, "") else fb
            except: return fb

        return {
            "invoice_default_amount": _to_float(mapping.get("invoice_default_amount"), 12000),
            "personal_without_gst_default_amount": _to_float(mapping.get("personal_without_gst_default_amount"), 12000),
            "invoice_terms_conditions": mapping.get("invoice_terms_conditions") or "• Subject to Surat Jurisdiction",
            "payment_upi_id": mapping.get("payment_upi_id") or "",
            "payment_account_name": mapping.get("payment_account_name") or "Harikrushn DigiVerse LLP",
            "payment_qr_image_url": mapping.get("payment_qr_image_url") or "",
            "company_name": mapping.get("company_name") or "Harikrushn DigiVerse LLP",
            "company_address": mapping.get("company_address") or "Surat, Gujarat, India",
            "company_phone": mapping.get("company_phone") or "+91 8866005029",
            "company_email": mapping.get("company_email") or "hetrmangukiya@gmail.com"
        }

    async def get_workflow_options(self, current_user: User) -> dict:
        settings_defaults = await self.get_invoice_defaults()
        return {
            "payment_types": ["BUSINESS_ACCOUNT", "PERSONAL_ACCOUNT", "CASH"],
            "gst_types": ["WITH_GST", "WITHOUT_GST"],
            "permissions": {
                "can_create_invoice": await self._can_create_invoice(current_user),
                "can_verify": await self._can_verify(current_user),
                "can_send": await self._can_send(current_user),
            },
        }

    async def resolve_workflow(self, req: BillingWorkflowResolveRequest) -> dict:
        self._validate_payment_mode(req.payment_type, req.gst_type)
        settings_defaults = await self.get_invoice_defaults()

        base_amount = req.amount
        if base_amount is None:
            if req.payment_type == "PERSONAL_ACCOUNT" and req.gst_type == "WITHOUT_GST":
                base_amount = float(settings_defaults.get("personal_without_gst_default_amount") or 12000)
            else:
                base_amount = float(settings_defaults.get("invoice_default_amount") or 12000)

        if base_amount <= 0: raise HTTPException(status_code=400, detail="Amount > 0 required")

        gst_amount = round(base_amount * 0.18, 2) if req.gst_type == "WITH_GST" else 0.0
        total_amount = round(base_amount + gst_amount, 2)

        return {
            "payment_type": req.payment_type,
            "gst_type": req.gst_type,
            "amount": total_amount,
            "base_amount": base_amount,
            "gst_amount": gst_amount,
            "total_amount": total_amount
        }

    async def create_invoice(self, bill_in: BillCreate, current_user: User) -> Bill:
        # TODO: Implement MongoDB transactions for financial safety
        if not await self._can_create_invoice(current_user):
            raise HTTPException(status_code=403, detail="Permission Denied")

        resolved = await self.resolve_workflow(
            BillingWorkflowResolveRequest(payment_type=bill_in.payment_type, gst_type=bill_in.gst_type, amount=bill_in.amount)
        )
        invoice_number, invoice_series, invoice_sequence = await self._next_invoice_number(bill_in.gst_type)

        existing_client = await Client.find_one(Client.phone == bill_in.invoice_client_phone) if bill_in.invoice_client_phone else None

        db_bill = Bill(
            shop_id=bill_in.shop_id,
            client_id=existing_client.id if existing_client else None,
            invoice_client_name=bill_in.invoice_client_name,
            invoice_client_phone=bill_in.invoice_client_phone,
            invoice_client_email=bill_in.invoice_client_email,
            invoice_client_address=bill_in.invoice_client_address,
            invoice_client_org=bill_in.invoice_client_org,
            amount=resolved["total_amount"],
            payment_type=bill_in.payment_type,
            gst_type=bill_in.gst_type,
            invoice_series=invoice_series,
            invoice_sequence=invoice_sequence,
            requires_qr=bill_in.payment_type != "CASH",
            service_description=bill_in.service_description,
            billing_month=bill_in.billing_month,
            invoice_number=invoice_number,
            invoice_status="PENDING_VERIFICATION",
            status="PENDING",
            created_by_id=current_user.id,
        )
        await db_bill.insert()
        return db_bill

    async def get_bill(self, bill_id: PydanticObjectId, current_user: User = None) -> Bill | None:
        bill = await Bill.get(bill_id)
        if not bill or bill.is_deleted: return None
        return bill

    async def get_all_bills(self, current_user: User, skip: int = 0, limit: int = 200, search: str = None, **kwargs):
        """Refined bill retrieval with dynamic aggregation of frontend filters."""
        filters: Dict[str, Any] = {"is_deleted": False}
        
        # RBAC: Non-admins only see their own or non-archived bills
        if current_user.role != UserRole.ADMIN:
            filters["$or"] = [
                {"created_by_id": current_user.id},
                {"is_archived": False}
            ]
            
        if search:
            import re
            pattern = re.compile(f".*{re.escape(search.strip())}.*", re.IGNORECASE)
            search_clause = {
                "$or": [
                    {"invoice_number": pattern},
                    {"invoice_client_name": pattern},
                    {"invoice_client_phone": pattern}
                ]
            }
            if "$or" in filters:
                filters = {"$and": [filters, search_clause]}
            else:
                filters.update(search_clause)

        # Dynamic Filters from Kwargs
        status_filter = kwargs.get("status_filter")
        if status_filter and status_filter.upper() != "ALL":
            filters["invoice_status"] = status_filter.upper()
             
        payment_type = kwargs.get("payment_type")
        if payment_type and payment_type.upper() != "ALL":
            filters["payment_type"] = payment_type.upper()
             
        gst_type = kwargs.get("gst_type")
        if gst_type and gst_type.upper() != "ALL":
            filters["gst_type"] = gst_type.upper()
             
        if "archived" in kwargs:
            val = kwargs["archived"]
            filters["is_archived"] = str(val).lower() == "true"

        bills = await Bill.find(filters).sort("-created_at").skip(skip).limit(limit).to_list()
        res = []
        for b in bills:
            d = b.model_dump()
            d["id"] = b.id
            if b.created_by_id:
                u = await User.get(b.created_by_id)
                d["creator_name"] = u.name if u else "Admin"
            res.append(d)
        return res

    async def verify_invoice(self, bill_id: PydanticObjectId, current_user: User) -> Bill:
        if not await self._can_verify(current_user): raise HTTPException(status_code=403, detail="Permission Denied")
        bill = await self.get_bill(bill_id)
        if not bill: raise HTTPException(status_code=404, detail="Not Found")
        bill.invoice_status = "VERIFIED"
        bill.verified_by_id = current_user.id
        bill.verified_at = datetime.datetime.now(UTC)
        await bill.save()
        return bill

    async def archive_invoice(self, bill_id: PydanticObjectId, current_user: User) -> Bill:
        bill = await self.get_bill(bill_id)
        if not bill: raise HTTPException(status_code=44, detail="Not Found")
        bill.is_archived = True
        await bill.save()
        return bill

    async def send_whatsapp_invoice(self, bill_id: PydanticObjectId, current_user: User) -> dict:
        bill = await self.get_bill(bill_id)
        if not bill: raise HTTPException(status_code=404, detail="Not Found")
        
        if not bill.client_id:
            client = await Client.find_one(Client.phone == bill.invoice_client_phone)
            if not client:
                client = Client(name=bill.invoice_client_name, phone=bill.invoice_client_phone, email=bill.invoice_client_email or f"pm_{uuid.uuid4().hex[:4]}@crm.com", is_active=True)
                await client.insert()
            bill.client_id = client.id

        # Simplified for Batch 1 rewrite - placeholder for real WA logic
        bill.invoice_status = "SENT"
        bill.whatsapp_sent = True
        await bill.save()
        
        # Advance shop stage
        if bill.shop_id:
            from app.modules.shops.models import Shop
            shop = await Shop.get(bill.shop_id)
            if shop:
                from app.core.enums import MasterPipelineStage
                shop.pipeline_stage = MasterPipelineStage.MAINTENANCE
                shop.client_id = bill.client_id
                await shop.save()

        return {"bill": bill, "status": "sent"}

    async def refund_invoice(self, bill_id: PydanticObjectId, current_user: User) -> Bill:
        # TODO: Implement MongoDB transactions for financial safety
        bill = await self.get_bill(bill_id)
        if not bill: raise HTTPException(status_code=404, detail="Not Found")
        bill.invoice_status = "REFUNDED"
        if bill.client_id:
            c = await Client.get(bill.client_id)
            if c:
                c.is_active = False
                await c.save()
        await bill.save()
        return bill

    async def get_invoice_actions(self, invoice_id: PydanticObjectId, current_user: User, **kwargs) -> dict:
        bill = await self.get_bill(invoice_id)
        if not bill:
            raise HTTPException(status_code=404, detail="Invoice not found")
            
        allowed_verifier_roles = await self._allowed_verifier_roles()
        
        can_verify = await self._can_verify(current_user)
        can_send_whatsapp = await self._can_send(current_user)
        can_archive = self._can_archive_invoice(current_user, bill)
        
        if bill.invoice_status in ["VERIFIED", "SENT", "PAID", "CANCELLED", "REFUNDED"]:
            can_verify = False
            
        return {
            "can_verify": can_verify,
            "can_send_whatsapp": can_send_whatsapp,
            "can_archive": can_archive and not bill.is_archived,
            "can_unarchive": can_archive and bill.is_archived,
            "can_delete_archived": current_user.role == UserRole.ADMIN,
            "allowed_verifier_roles": list(allowed_verifier_roles),
        }

    async def save_invoice_settings(self, payload: dict) -> dict:
        for key, value in payload.items():
            if isinstance(value, str):
                await self._set_setting(key, value)
            else:
                await self._set_setting(key, str(value))
        return {"status": "success", "message": "Settings updated"}

    async def check_whatsapp_health(self, current_user: User) -> dict:
        # Placeholder for WA health check
        return {"status": "UP", "message": "WhatsApp service is reachable"}

    async def unarchive_invoice(self, bill_id: PydanticObjectId, current_user: User) -> Bill:
        bill = await self.get_bill(bill_id)
        if not bill: raise HTTPException(status_code=404, detail="Not Found")
        bill.is_archived = False
        await bill.save()
        return bill

    async def archive_invoices_bulk(self, ids: List[PydanticObjectId], current_user: User) -> dict:
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Permission Denied")
        # Native Beanie bulk update
        await Bill.find(In(Bill.id, ids)).update({"$set": {"is_archived": True}})
        return {"status": "success", "archived_count": len(ids)}

    async def delete_archived_invoice(self, bill_id: PydanticObjectId, current_user: User) -> dict:
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Permission Denied")
        bill = await self.get_bill(bill_id)
        if not bill: raise HTTPException(status_code=404, detail="Not Found")
        bill.is_deleted = True
        await bill.save()
        return {"status": "success"}

    async def delete_archived_invoices_bulk(self, ids: List[PydanticObjectId], current_user: User) -> dict:
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Permission Denied")
        # Native Beanie bulk update
        await Bill.find(In(Bill.id, ids)).update({"$set": {"is_deleted": True}})
        return {"status": "success", "deleted_count": len(ids)}

    async def force_sent(self, bill_id: PydanticObjectId, current_user: User) -> Bill:
        bill = await self.get_bill(bill_id)
        if not bill: raise HTTPException(status_code=404, detail="Not Found")
        bill.invoice_status = "SENT"
        bill.whatsapp_sent = True
        await bill.save()
        return bill
