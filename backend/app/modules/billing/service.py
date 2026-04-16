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
from app.modules.activity_logs.service import ActivityLogger
from app.modules.activity_logs.models import ActionType, EntityType
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
import re

import httpx
import base64
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

class BillingService:
    def __init__(self):
        # No db session needed in Beanie!
        pass

    # ─────────────────────────────── helpers ────────────────────────────────

    async def _get_setting(self, key: str, default: str = "") -> str:
        row = await AppSetting.find_one(AppSetting.key == key)
        return row.value if row and row.value is not None else default

    async def _set_setting(self, key: str, value: str) -> None:
        row = await AppSetting.find_one(AppSetting.key == key)
        if row:
            row.value = value
            await row.save()
        else:
            new_setting = AppSetting(key=key, value=value)
            await new_setting.insert()

    async def _get_website_max_seq(self, prefix: str, year: int) -> int:
        """
        Finds the highest sequence number (NNN) from website_payment ONLY.
        Only counts 'SUCCESS' statuses as per user's requirement.
        """
        max_seq = 0
        regex = f"^{prefix}/{year}/"
        website_coll = Bill.get_pymongo_collection().database["website_payment"]
        possible_fields = ["invoice", "invoice_no", "invoice_number"]
        or_filters = [{f: {"$regex": regex}} for f in possible_fields]
        
        last_site_payment = await website_coll.find_one(
            {"$and": [{"status": "SUCCESS"}, {"$or": or_filters}]},
            sort=[("_id", -1)]
        )


        if last_site_payment:
            for f in possible_fields:
                val = last_site_payment.get(f)
                if val and isinstance(val, str) and "/" in val:
                    try:
                        parts = val.split("/")
                        if len(parts) == 3:
                            max_seq = max(max_seq, int(parts[2]))
                    except (ValueError, IndexError):
                        continue
        return max_seq

    async def _next_invoice_number(self, gst_type: str) -> tuple[str, str, int]:
        # Determine the year (override from settings or system year)
        year_str = await self._get_setting("invoice_year", "")
        try:
            year = int(year_str) if year_str else datetime.datetime.now(UTC).year
        except ValueError:
            year = datetime.datetime.now(UTC).year

        sync_website = False  # Default: no website_payment conflict check
        if gst_type == "WITHOUT_GST":
            seq_key = "invoice_seq_without_gst"
            series  = "PINV"
            prefix  = "PInv"
        else:
            seq_key = "invoice_seq_with_gst"
            series = "INV"
            prefix = "Inv"
            sync_website = True  # WITH_GST invoices sync with website_payment table

        # 1. BOSS: Get the starting number from Settings
        start_str = await self._get_setting(seq_key, "1")
        current = max(int(start_str or "1"), 1)
        
        # 2. CONFLICT CHECK: Only check website_payment for SUCCESSful invoices
        if sync_website:
            website_max = await self._get_website_max_seq(prefix, year)
            if website_max >= current:
                current = website_max + 1

        # 3. UNIQUENESS: Final check in website table to prevent overlaps
        if sync_website:
            website_coll = Bill.get_pymongo_collection().database["website_payment"]
            while True:
                invoice_number = f"{prefix}/{year}/{current:03d}"
                site_exists = await website_coll.find_one({
                    "$or": [
                        {"invoice": invoice_number},
                        {"invoice_no": invoice_number}
                    ]
                })
                if not site_exists: break
                current += 1
        
        invoice_number = f"{prefix}/{year}/{current:03d}"

        # 4. SYNC: Save issued + 1 back to settings
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
            "invoice_header_bg", "invoice_seq_with_gst", "invoice_seq_without_gst", "invoice_year", "invoice_verifier_roles", "invoice_sender_roles", "invoice_creator_roles", "whatsapp_invoice_caption",
        ]
        # Use Beanie find with In operator for reliability
        rows = await AppSetting.find(In(AppSetting.key, keys)).to_list()
        mapping = {r.key: r.value for r in rows}

        def _to_float(v: Any, fb: float) -> float:
            try: return float(v) if v not in (None, "") else fb
            except: return fb

        def _to_int(v: Any, fb: int) -> int:
            try: return int(v) if v not in (None, "") else fb
            except: return fb

        import datetime as _dt
        current_system_year = _dt.datetime.now().year
        year_val = mapping.get("invoice_year")
        try:
            resolved_year = int(year_val) if year_val else current_system_year
        except (ValueError, TypeError):
            resolved_year = current_system_year

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
            "company_email": mapping.get("company_email") or "hetrmangukiya@gmail.com",
            # Additional keys for frontend
            "business_payment_upi_id": mapping.get("business_payment_upi_id") or "",
            "business_payment_qr_image_url": mapping.get("business_payment_qr_image_url") or "",
            "personal_payment_upi_id": mapping.get("personal_payment_upi_id") or "",
            "personal_payment_qr_image_url": mapping.get("personal_payment_qr_image_url") or "",
            # Sync keys
            "invoice_year": resolved_year,
            "invoice_seq_with_gst": _to_int(mapping.get("invoice_seq_with_gst"), 1),
            "invoice_seq_without_gst": _to_int(mapping.get("invoice_seq_without_gst"), 1),
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

        is_default_amt = (req.amount is None)
        gst_amount = round(base_amount * 0.18, 2) if req.gst_type == "WITH_GST" else 0.0
        total_amount = round(base_amount + gst_amount, 2)

        return {
            "payment_type": req.payment_type,
            "gst_type": req.gst_type,
            "requires_qr": req.payment_type != "CASH",
            "amount": total_amount,
            "base_amount": base_amount,
            "gst_amount": gst_amount,
            "total_amount": total_amount,
            "amount_source": "DEFAULT" if is_default_amt else "MANUAL",
            "qr_available": True, # At least static or PhonePe is always a fallback
            "payment_upi_id": settings_defaults.get("payment_upi_id"),
            "payment_account_name": settings_defaults.get("payment_account_name")
        }

    async def create_invoice(self, bill_in: BillCreate, current_user: User) -> Bill:
        # TODO: Implement MongoDB transactions for financial safety
        if not await self._can_create_invoice(current_user):
            raise HTTPException(status_code=403, detail="Permission Denied")

        # ─── Strict Payment Gateway Verification ───
        if bill_in.payment_type == "BUSINESS_ACCOUNT":
            if not bill_in.transaction_id:
                raise HTTPException(status_code=400, detail="Transaction ID is required for Business Account payments")
            
            # Re-verify with PhonePe Server-to-Server
            try:
                pp_status = await self.check_phonepe_payment_status(bill_in.transaction_id, current_user)
                # Allow PAYMENT_SUCCESS or PAYMENT_PENDING. Block only on definitive failures.
                if pp_status.get("code") not in ["PAYMENT_SUCCESS", "PAYMENT_PENDING", "INTERNAL_SERVER_ERROR"]:
                    raise HTTPException(
                        status_code=402, 
                        detail=f"Payment for transaction {bill_in.transaction_id} is {pp_status.get('state', 'FAILED')}. Status: {pp_status.get('code')}"
                    )
                # Success - we can proceed to record it
            except HTTPException:
                raise # Re-raise if it's already an HTTPException
            except Exception as e:
                print(f"[Strict Verify Error] {e}")
                raise HTTPException(status_code=502, detail="Failed to verify payment status with provider. Please try again.")

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
            invoice_status="VERIFIED" if bill_in.payment_type == "BUSINESS_ACCOUNT" else "PENDING_VERIFICATION",
            status="SUCCESS" if bill_in.payment_type == "BUSINESS_ACCOUNT" else "PENDING",
            transaction_id=bill_in.transaction_id,
            payment_gateway_status="SUCCESS" if bill_in.payment_type == "BUSINESS_ACCOUNT" else bill_in.payment_gateway_status,
            created_by_id=current_user.id,
        )
        await db_bill.insert()

        # ─── Keep shop in DELIVERY stage (bill tracker: step 1 of 3) ───
        # Stage advances to MAINTENANCE only AFTER WhatsApp send (step 3)
        if db_bill.shop_id:
            from app.modules.shops.models import Shop
            from app.core.enums import MasterPipelineStage
            shop = await Shop.get(db_bill.shop_id)
            if shop:
                shop.pipeline_stage = MasterPipelineStage.DELIVERY  # Stay in DELIVERY
                if db_bill.client_id:
                    shop.client_id = db_bill.client_id
                await shop.save()

        # ─── Activity Log ───
        await ActivityLogger().log_activity(
            user_id=current_user.id,
            user_role=current_user.role,
            action=ActionType.CREATE,
            entity_type=EntityType.BILL,
            entity_id=db_bill.id,
            new_data={"invoice_number": db_bill.invoice_number, "amount": db_bill.amount, "payment_type": db_bill.payment_type}
        )

        # ─── Notify Admins about new invoice ───
        try:
            from app.utils.notify_helpers import notify_admins
            client_name = db_bill.invoice_client_name or "Unknown Client"
            amount_fmt = f"₹{db_bill.amount:,.0f}"
            payment_label = {
                "BUSINESS_ACCOUNT": "Bank (Business)",
                "PERSONAL_ACCOUNT": "Bank (Personal)",
                "CASH": "Cash",
            }.get(db_bill.payment_type, db_bill.payment_type or "—")

            if db_bill.invoice_status == "PENDING_VERIFICATION":
                # Needs admin verification — urgent alert
                await notify_admins(
                    title=f"🧾 New Invoice Pending Verification — {db_bill.invoice_number}",
                    message=(
                        f"Invoice {db_bill.invoice_number} for {client_name} "
                        f"| Amount: {amount_fmt} | Mode: {payment_label} "
                        f"| Created by: {current_user.name}. Please verify."
                    ),
                    actor_id=current_user.id,
                )
            else:
                # BUSINESS_ACCOUNT invoices are auto-VERIFIED via PhonePe — informational
                await notify_admins(
                    title=f"✅ Invoice Auto-Verified (PhonePe) — {db_bill.invoice_number}",
                    message=(
                        f"Invoice {db_bill.invoice_number} for {client_name} "
                        f"| Amount: {amount_fmt} | Mode: {payment_label} "
                        f"| Created & auto-verified by: {current_user.name}."
                    ),
                    actor_id=current_user.id,
                )
        except Exception as e:
            print(f"[create_invoice] Warning: admin notification failed: {e}")

        return db_bill

    async def get_bill(self, bill_id: PydanticObjectId, current_user: User = None) -> Bill | None:
        bill = await Bill.get(bill_id)
        if not bill or bill.is_deleted: return None
        return bill

    async def get_all_bills(self, current_user: User, skip: int = 0, limit: Optional[int] = None, search: str = None, **kwargs):
        """Refined bill retrieval with dynamic aggregation of frontend filters.
        
        When `limit` is None (the default), ALL matching records are returned.
        When `limit` is an integer, only that many records are returned.
        """
        filters: Dict[str, Any] = {"is_deleted": False}
        
        # RBAC: Non-admins only see their own or non-archived bills
        if current_user.role != UserRole.ADMIN:
            filters["$or"] = [
                {"created_by_id": current_user.id},
                {"is_archived": False}
            ]
            
        if search:
            search_str = f".*{re.escape(search.strip())}.*"
            search_clause = {
                "$or": [
                    {"invoice_number": {"$regex": search_str, "$options": "i"}},
                    {"invoice_client_name": {"$regex": search_str, "$options": "i"}},
                    {"invoice_client_phone": {"$regex": search_str, "$options": "i"}}
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
             
        # shop_id filter — CRITICAL: scope invoices to the specific lead/shop
        shop_id_val = kwargs.get("shop_id")
        if shop_id_val is not None:
            try:
                filters["shop_id"] = PydanticObjectId(shop_id_val) if not isinstance(shop_id_val, PydanticObjectId) else shop_id_val
            except Exception:
                pass  # ignore invalid shop_id

        if "archived" in kwargs:
            val = kwargs["archived"]
            if val and str(val).upper() == "ALL":
                pass  # No archive filter — return both archived and non-archived
            elif val == "ARCHIVED":
                filters["is_archived"] = True
            elif val == "ACTIVE":
                filters["is_archived"] = False
            else:
                filters["is_archived"] = str(val).lower() == "true"

        # Build query — only apply limit when explicitly provided
        query = Bill.find(filters).sort("-created_at").skip(skip)
        if limit is not None:
            query = query.limit(limit)
        bills = await query.to_list()

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

        await ActivityLogger().log_activity(
            user_id=current_user.id,
            user_role=current_user.role,
            action=ActionType.STATUS_CHANGE,
            entity_type=EntityType.BILL,
            entity_id=bill.id,
            new_data={"status": "VERIFIED"}
        )

        return bill

    async def archive_invoice(self, bill_id: PydanticObjectId, current_user: User) -> Bill:
        bill = await self.get_bill(bill_id)
        if not bill: raise HTTPException(status_code=404, detail="Not Found")
        bill.is_archived = True
        await bill.save()

        # Sync with Shop
        if bill.shop_id:
            from app.modules.shops.models import Shop
            shop = await Shop.get(bill.shop_id)
            if shop:
                shop.is_archived = True
                shop.archived_by_id = current_user.id
                await shop.save()

        await ActivityLogger().log_activity(
            user_id=current_user.id,
            user_role=current_user.role,
            action=ActionType.STATUS_CHANGE,
            entity_type=EntityType.BILL,
            entity_id=bill.id,
            new_data={"archived": True}
        )

        return bill

    async def send_whatsapp_invoice(self, bill_id: PydanticObjectId, current_user: User, base_url: str = None) -> dict:
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
        
        # ─── Step 3 of 3: Advance shop to MAINTENANCE + link client_id ───
        if bill.shop_id:
            from app.modules.shops.models import Shop
            from app.core.enums import MasterPipelineStage
            shop = await Shop.get(bill.shop_id)
            if shop:
                if shop.pipeline_stage == MasterPipelineStage.DELIVERY:
                    shop.pipeline_stage = MasterPipelineStage.MAINTENANCE
                # Always sync client_id — critical for training session scheduling
                if bill.client_id and not shop.client_id:
                    shop.client_id = bill.client_id
                await shop.save()

        return {"bill": bill, "status": "sent"}

    async def refund_invoice(self, bill_id: PydanticObjectId, current_user: User) -> Bill:
        """Marks an invoice as REFUNDED and synchronizes the associated client status."""
        bill = await self.get_bill(bill_id)
        if not bill:
            raise HTTPException(status_code=404, detail="Invoice Not Found")
        
        bill.status = "REFUNDED"
        bill.invoice_status = "REFUNDED"
        
        if bill.client_id:
            from app.modules.clients.models import Client
            c = await Client.get(bill.client_id)
            if c:
                c.is_active = False
                c.status = "REFUNDED"
                await c.save()
        
        # Archive Lead/Project on Refund
        if bill.shop_id:
            from app.modules.shops.models import Shop
            shop = await Shop.get(bill.shop_id)
            if shop:
                shop.is_archived = True
                shop.archived_by_id = current_user.id
                await shop.save()

        await bill.save()

        await ActivityLogger().log_activity(
            user_id=current_user.id,
            user_role=current_user.role,
            action=ActionType.STATUS_CHANGE,
            entity_type=EntityType.BILL,
            entity_id=bill.id,
            new_data={"status": "REFUNDED", "archived_shop": bool(bill.shop_id)}
        )

        return bill

    async def generate_payment_qr_for_new_invoice(self, payment_type: str, gst_type: str, amount: float, phone: str = "9999999999", origin: str = None) -> dict:
        # Check if banking details configured
        is_configured = False
        upi_id = ""
        upi_name = ""
        qr_image_url = ""
        
        if payment_type == "BUSINESS_ACCOUNT":
            txn_id = f"T{datetime.datetime.now().strftime('%y%m%d%H%M%S')}{uuid.uuid4().hex[:4].upper()}"
            paise_amount = int(round(amount * 100))
            
            # Robust URL detection: If frontend sends 'origin', use it as the base for redirect
            base_url = origin or settings.PHONEPE_CALLBACK_BASE_URL
            if not base_url:
                # Fallback for local development if nothing is provided
                base_url = f"http://localhost:{settings.SRM_PORT if hasattr(settings, 'SRM_PORT') else 8000}"
                dummy_callback = "https://webhook.site/dummy-phonepe-callback"
            else:
                if not base_url.startswith("http"):
                    # Local development helper: default to http for localhost/127.0.0.1
                    if "localhost" in base_url or "127.0.0.1" in base_url:
                        base_url = f"http://{base_url}"
                    else:
                        base_url = f"https://{base_url}"
                
                # Ensure no trailing slash in base_url
                base_url = base_url.rstrip("/")

                # If it's a localhost origin, use a dummy callback for the simulator cloud
                if "localhost" in base_url or "127.0.0.1" in base_url:
                    dummy_callback = "https://webhook.site/dummy-phonepe-callback"
                else:
                    dummy_callback = f"{base_url}/api/billing/phonepe-callback"

            payload = {
                "merchantId": settings.PHONEPE_MERCHANT_ID,
                "merchantTransactionId": txn_id,
                "merchantUserId": f"U{phone[-10:]}",
                "amount": paise_amount,
                "redirectUrl": f"{base_url}/billing.html?status=success&txnId={txn_id}",
                "redirectMode": "REDIRECT",
                "callbackUrl": dummy_callback,
                "mobileNumber": phone[-10:],
                "expiresIn": 200,

                "paymentInstrument": {"type": "PAY_PAGE"}
            }
            
            # Encode & Sign
            payload_json = json.dumps(payload)
            payload_main = base64.b64encode(payload_json.encode()).decode()
            
            endpoint = "/pg/v1/pay"
            salt_key = settings.PHONEPE_SALT_KEY
            salt_idx = settings.PHONEPE_SALT_INDEX
            
            hash_raw = f"{payload_main}{endpoint}{salt_key}"
            hash_hex = hashlib.sha256(hash_raw.encode()).hexdigest()
            x_verify = f"{hash_hex}###{salt_idx}"
            
            # API Call
            pp_env = settings.PHONEPE_ENV or "sandbox"
            base_api = settings.PHONEPE_BASE_URL or "https://api-preprod.phonepe.com/apis/pg-sandbox"
            if pp_env == "production":
                base_api = "https://api.phonepe.com/apis/hermes"
                # Dynamic Security Check: Warn if using default test salts in production
                if settings.PHONEPE_MERCHANT_ID == "PGTESTPAYUAT86":
                    print("[WARNING] Running in PRODUCTION with DEFAULT UAT Merchant ID!")

            api_url = f"{base_api}{endpoint}"
            
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(
                        api_url,
                        json={"request": payload_main},
                        headers={"Content-Type": "application/json", "X-VERIFY": x_verify},
                    )
                    
                    if resp.status_code == 429:
                        raise HTTPException(status_code=429, detail="Too many requests to PhonePe. Please wait 1-2 minutes or use a different account.")
                    
                    try:
                        resp_data = resp.json()
                    except Exception:
                        print(f"[PhonePe Error] Non-JSON response ({resp.status_code}): {resp.text[:200]}")
                        raise HTTPException(status_code=502, detail="Invalid response from Payment Gateway")
                    
                if resp_data.get("success"):
                    pay_url = resp_data["data"]["instrumentResponse"]["redirectInfo"]["url"]
                    return {
                        "type": "gateway",
                        "gateway": "phonepe",
                        "pay_url": pay_url,
                        "transaction_id": txn_id,
                        "amount": amount
                    }
                else:
                    msg = resp_data.get("message", "PhonePe initiation failed")
                    code = resp_data.get("code", "UNKNOWN")
                    print(f"[PhonePe Rejection] {code}: {msg}")
                    raise HTTPException(status_code=400, detail=f"Gateway Error: {msg}")
                    
            except HTTPException:
                raise
            except Exception as e:
                print(f"[PhonePe Connection Error] {e}")
                raise HTTPException(status_code=502, detail=f"Payment Gateway unreachable: {str(e)}")

        # 2. Static QR & Shared Link fallback
        defaults = await self.get_invoice_defaults()
        
        # Decide which settings to use
        is_business = (payment_type == "BUSINESS_ACCOUNT")
        prefix = "business_" if is_business else "personal_"
        
        upi_id = defaults.get(f"{prefix}payment_upi_id") or defaults.get("payment_upi_id") or ""
        qr_url = defaults.get(f"{prefix}payment_qr_image_url") or defaults.get("payment_qr_image_url") or ""
        
        # dynamic_upi: upi://pay?pa=ID&pn=NAME&am=AMT&cu=INR
        clean_upi = upi_id.split('?')[0]
        name_encoded = quote("Harikrushn DigiVerse")
        dynamic_upi = f"upi://pay?pa={clean_upi}&pn={name_encoded}&am={amount}&cu=INR"
        
        return {
            "type": "static",
            "upi_id": upi_id,
            "qr_image_url": qr_url,
            "dynamic_upi_link": dynamic_upi,
            "amount": amount,
            "is_fallback": False # Reset fallback as requested by user
        }

    async def check_phonepe_payment_status(self, txn_id: str, current_user: User) -> Dict[str, Any]:
        """
        Polls PhonePe for transaction status and verifies ownership.
        """
        # Security: Check if this txn_id is already linked to a bill
        bill = await Bill.find_one(Bill.transaction_id == txn_id)
        if bill:
            # If bill exists, verify ownership (Admin/Creator only)
            is_admin = getattr(current_user, "role", "") == "ADMIN"
            is_creator = str(bill.created_by_id) == str(current_user.id)
            if not (is_admin or is_creator):
                raise HTTPException(status_code=403, detail="You do not have permission to check this payment status.")
        
        merchant_id = settings.PHONEPE_MERCHANT_ID
        salt_key = settings.PHONEPE_SALT_KEY
        salt_idx = settings.PHONEPE_SALT_INDEX
        
        # Endpoint: /pg/v1/status/{merchantId}/{merchantTransactionId}
        endpoint = f"/pg/v1/status/{merchant_id}/{txn_id}"
        
        # Signature: SHA256(endpoint + saltKey) + "###" + saltIndex
        hash_raw = f"{endpoint}{salt_key}"
        hash_hex = hashlib.sha256(hash_raw.encode()).hexdigest()
        x_verify = f"{hash_hex}###{salt_idx}"
        
        pp_env = settings.PHONEPE_ENV or "sandbox"
        base_api = settings.PHONEPE_BASE_URL or "https://api-preprod.phonepe.com/apis/pg-sandbox"
        if pp_env == "production":
            base_api = "https://api.phonepe.com/apis/hermes"
            
        full_url = f"{base_api}{endpoint}"
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    full_url,
                    headers={"Content-Type": "application/json", "X-VERIFY": x_verify, "X-MERCHANT-ID": merchant_id},
                )
                data = resp.json()
                
            # data structure: {success: bool, code: str, message: str, data: {merchantTransactionId, state, ...}}
            return {
                "success": data.get("success", False),
                "code": data.get("code", "UNKNOWN"),
                "message": data.get("message", "Request failed"),
                "txn_id": txn_id,
                "state": data.get("data", {}).get("state", "UNKNOWN")
            }
        except Exception as e:
            print(f"[PhonePe Status Error] {e}")
            raise HTTPException(status_code=502, detail=f"Failed to fetch payment status: {str(e)}")

    async def get_invoice_actions(self, bill: Bill, current_user: User) -> Dict[str, Any]:
        can_verify = await self._can_verify(current_user) and bill.invoice_status == "PENDING_VERIFICATION"
        can_send = await self._can_send(current_user) and bill.invoice_status in {"VERIFIED", "SENT"}
        
        can_archive = self._can_archive_invoice(current_user, bill) and not bill.is_archived
        can_unarchive = self._can_archive_invoice(current_user, bill) and bill.is_archived
        can_delete = (current_user.role == UserRole.ADMIN) and bill.is_archived

        allowed_verifier_roles = list(await self._allowed_verifier_roles())
        
        return {
            "can_verify": can_verify,
            "can_send_whatsapp": can_send,
            "can_archive": can_archive,
            "can_unarchive": can_unarchive,
            "can_delete_archived": can_delete,
            "allowed_verifier_roles": allowed_verifier_roles
        }

    async def save_invoice_settings(self, payload: dict) -> dict:
        print(f"[DEBUG] save_invoice_settings PAYLOAD: {payload}")
        for key, value in payload.items():
            if value is not None:
                print(f"[DEBUG] Saving setting: {key} = {value}")
                await self._set_setting(key, str(value))
        return {"status": "success"}


    async def check_whatsapp_health(self, current_user: User) -> dict:
        # Placeholder for real WhatsApp health logic
        return {"status": "healthy", "service": "whatsapp", "timestamp": datetime.datetime.now(UTC).isoformat()}

    async def unarchive_invoice(self, bill_id: PydanticObjectId, current_user: User) -> Bill:
        bill = await self.get_bill(bill_id)
        if not bill: raise HTTPException(status_code=404, detail="Not Found")
        bill.is_archived = False
        await bill.save()
        return bill

    async def archive_invoices_bulk(self, ids: List[PydanticObjectId], current_user: User) -> dict:
        await Bill.get_pymongo_collection().update_many(
            {"_id": {"$in": ids}},
            {"$set": {"is_archived": True, "archived_by_id": current_user.id}}
        )
        return {"status": "success", "count": len(ids)}

    async def delete_archived_invoice(self, bill_id: PydanticObjectId, current_user: User) -> dict:
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Permission Denied")
        bill = await self.get_bill(bill_id)
        if not bill: raise HTTPException(status_code=404, detail="Not Found")
        if not bill.is_archived:
            raise HTTPException(status_code=400, detail="Only archived invoices can be deleted")
        
        bill.is_deleted = True
        await bill.save()
        return {"status": "success"}

    async def permanent_delete_invoice(self, bill_id: PydanticObjectId, current_user: User) -> dict:
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Permission Denied")
        bill = await self.get_bill(bill_id)
        if not bill: raise HTTPException(status_code=404, detail="Not Found")
        if not bill.is_archived:
            raise HTTPException(status_code=400, detail="Only archived invoices can be permanently deleted")
        
        await bill.delete()
        return {"status": "success"}

    async def permanent_delete_invoice(self, bill_id: PydanticObjectId, current_user: User) -> dict:
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Permission Denied")
        bill = await self.get_bill(bill_id)
        if not bill: raise HTTPException(status_code=404, detail="Not Found")
        # Ensure it's archived before permanent deletion as a safety measure
        if not bill.is_archived:
            raise HTTPException(status_code=400, detail="Only archived invoices can be permanently deleted")
        
        await bill.delete()
        return {"status": "success"}

    async def delete_archived_invoices_bulk(self, ids: List[PydanticObjectId], current_user: User) -> dict:
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Permission Denied")
        
        await Bill.get_pymongo_collection().update_many(
            {"_id": {"$in": ids}, "is_archived": True},
            {"$set": {"is_deleted": True}}
        )
        return {"status": "success", "count": len(ids)}

    async def force_sent(self, bill_id: PydanticObjectId, current_user: User) -> Bill:
        bill = await self.get_bill(bill_id)
        if not bill: raise HTTPException(status_code=404, detail="Not Found")
        bill.invoice_status = "SENT"
        bill.whatsapp_sent = True
        await bill.save()
        return bill

