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
from .invoice_pdf import generate_bill_pdf

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
            # Payment — generic
            "payment_upi_id": mapping.get("payment_upi_id") or "",
            "payment_account_name": mapping.get("payment_account_name") or "Harikrushn DigiVerse LLP",
            "payment_qr_image_url": mapping.get("payment_qr_image_url") or "",
            "payment_bank_name": mapping.get("payment_bank_name") or "",
            "payment_account_number": mapping.get("payment_account_number") or "",
            "payment_ifsc": mapping.get("payment_ifsc") or "",
            "payment_branch": mapping.get("payment_branch") or "",
            # Payment — business account
            "business_payment_upi_id": mapping.get("business_payment_upi_id") or "",
            "business_payment_account_name": mapping.get("business_payment_account_name") or "",
            "business_payment_qr_image_url": mapping.get("business_payment_qr_image_url") or "",
            "business_payment_bank_name": mapping.get("business_payment_bank_name") or "",
            "business_payment_account_number": mapping.get("business_payment_account_number") or "",
            "business_payment_ifsc": mapping.get("business_payment_ifsc") or "",
            "business_payment_branch": mapping.get("business_payment_branch") or "",
            # Payment — personal account
            "personal_payment_upi_id": mapping.get("personal_payment_upi_id") or "",
            "personal_payment_account_name": mapping.get("personal_payment_account_name") or "",
            "personal_payment_qr_image_url": mapping.get("personal_payment_qr_image_url") or "",
            "personal_payment_bank_name": mapping.get("personal_payment_bank_name") or "",
            "personal_payment_account_number": mapping.get("personal_payment_account_number") or "",
            "personal_payment_ifsc": mapping.get("personal_payment_ifsc") or "",
            "personal_payment_branch": mapping.get("personal_payment_branch") or "",
            # Company details — FIX: were fetched but never returned (used by _build_invoice_html)
            "company_name": mapping.get("company_name") or "Harikrushn DigiVerse LLP",
            "company_address": mapping.get("company_address") or "Surat, Gujarat, India",
            "company_phone": mapping.get("company_phone") or "+91 8866005029",
            "company_email": mapping.get("company_email") or "hetrmangukiya@gmail.com",
            "company_gstin": mapping.get("company_gstin") or "",
            "company_pan": mapping.get("company_pan") or "",
            "company_cin": mapping.get("company_cin") or "",
            "company_cst_code": mapping.get("company_cst_code") or "",
            # Invoice appearance — FIX: invoice_header_bg was fetched but not returned
            "invoice_header_bg": mapping.get("invoice_header_bg") or "#2E5B82",
            # Role settings — FIX: were fetched but not returned
            "invoice_verifier_roles": mapping.get("invoice_verifier_roles") or "ADMIN",
            "invoice_sender_roles": mapping.get("invoice_sender_roles") or "ADMIN,SALES",
            "invoice_creator_roles": mapping.get("invoice_creator_roles") or "ADMIN,SALES",
            "whatsapp_invoice_caption": mapping.get("whatsapp_invoice_caption") or "",
            # Sequence tracking
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
            # FIX: auto-fill billing_month if not provided (schema now Optional)
            billing_month=bill_in.billing_month or datetime.datetime.now(UTC).strftime("%b %Y"),
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
        
        # ─── Strict RBAC Check ───
        if current_user and current_user.role != UserRole.ADMIN:
            # 1. Allow if they created the bill
            if bill.created_by_id == current_user.id:
                return bill
                
            # 2. Allow if they own/manage the client
            if bill.client_id:
                # Use Client model to check ownership context
                from app.modules.clients.models import Client
                client = await Client.get(bill.client_id)
                if client and (client.owner_id == current_user.id or client.pm_id == current_user.id or client.referred_by_id == current_user.id):
                    return bill
            
            # 3. Allow if they own/manage the shop
            if bill.shop_id:
                from app.modules.shops.models import Shop
                shop = await Shop.get(bill.shop_id)
                if shop:
                    is_managed = (
                        shop.owner_id == current_user.id or
                        shop.project_manager_id == current_user.id or
                        current_user.id in getattr(shop, 'assigned_user_ids', []) or
                        current_user.id in getattr(shop, 'assigned_owner_ids', [])
                    )
                    if is_managed:
                        return bill
            
            raise HTTPException(status_code=403, detail="Access denied to this invoice.")
            
        return bill

    async def get_all_bills(self, current_user: User, skip: int = 0, limit: Optional[int] = None, search: str = None, **kwargs):
        """Refined bill retrieval with dynamic aggregation of frontend filters.
        
        When `limit` is None (the default), ALL matching records are returned.
        When `limit` is an integer, only that many records are returned.
        """
        filters: Dict[str, Any] = {"is_deleted": False}
        
        # RBAC: Non-admins only see their own or their managed client/shop bills
        if current_user.role != UserRole.ADMIN:
            from app.modules.clients.models import Client
            from app.modules.shops.models import Shop
            
            # Identify managed clients
            raw_client_ids = await Client.get_pymongo_collection().distinct("_id", {
                "$or": [
                    {"owner_id": current_user.id},
                    {"pm_id": current_user.id},
                    {"referred_by_id": current_user.id}
                ],
                "is_deleted": False
            })
            managed_client_ids = [PydanticObjectId(rid) for rid in raw_client_ids if rid]

            # Identify managed shops
            raw_shop_ids = await Shop.get_pymongo_collection().distinct("_id", {
                "$or": [
                    {"owner_id": current_user.id},
                    {"project_manager_id": current_user.id},
                    {"assigned_user_ids": current_user.id},
                    {"assigned_owner_ids": current_user.id}
                ],
                "is_deleted": False
            })
            managed_shop_ids = [PydanticObjectId(rid) for rid in raw_shop_ids if rid]

            filters["$or"] = [
                {"created_by_id": current_user.id},
                In("client_id", managed_client_ids),
                In("shop_id", managed_shop_ids)
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

        # Build query
        base_query = Bill.find(filters)
        total_count = await base_query.count()
        
        query = base_query.sort("-created_at").skip(skip)
        if limit is not None:
            query = query.limit(limit)
        bills = await query.to_list()

        # Optimization: Pre-fetch roles and settings for actions calculation
        is_admin = current_user.role == UserRole.ADMIN
        can_verify_global = await self._can_verify(current_user)
        can_send_global = await self._can_send(current_user)
        
        # Batch Fetch Creator Names
        creator_ids = list({b.created_by_id for b in bills if b.created_by_id})
        creators_map = {}
        if creator_ids:
            creators = await User.find(In(User.id, creator_ids)).to_list()
            creators_map = {u.id: u.name for u in creators}

        res = []
        for b in bills:
            d = b.model_dump()
            d["id"] = str(b.id)
            d["creator_name"] = creators_map.get(b.created_by_id, "Admin")
            
            # Embed Actions directly to eliminate frontend N+1 calls
            # FIX: Use bool() to handle None values from migrated MongoDB records where
            # is_archived may be null instead of False — bool(None) = False, bool(True) = True
            can_refund_row = can_send_global and not bool(b.is_archived) and b.invoice_status in {"SENT", "CONFIRMED"}
            can_cancel_refund_row = can_send_global and b.invoice_status == "REFUNDED"
            
            d["actions"] = {
                "can_verify": can_verify_global and b.invoice_status == "PENDING_VERIFICATION",
                "can_send_whatsapp": can_send_global and b.invoice_status in {"VERIFIED", "SENT"},
                "can_archive": (is_admin or b.created_by_id == current_user.id) and not bool(b.is_archived),
                "can_unarchive": (is_admin or b.created_by_id == current_user.id) and bool(b.is_archived),
                "can_delete": is_admin and bool(b.is_archived),
                # Refund buttons removed from Billing page as per user request
                # Refund should be managed via Client page
            }
            res.append(d)
        # Status Counts for the filtered set (ignoring skip/limit)
        stats_pipeline = [
            {"$match": filters},
            {"$group": {
                "_id": "$invoice_status",
                "count": {"$sum": 1},
                "revenue": {"$sum": {"$cond": [{"$eq": ["$invoice_status", "SENT"]}, "$amount", 0]}}
            }}
        ]
        raw_stats = await Bill.get_pymongo_collection().aggregate(stats_pipeline).to_list()
        
        stats = {
            "total": total_count,
            "pending": sum(s["count"] for s in raw_stats if s["_id"] == "PENDING_VERIFICATION"),
            "sent": sum(s["count"] for s in raw_stats if s["_id"] == "SENT"),
            "revenue": sum(s["revenue"] for s in raw_stats)
        }

        return {"items": res, "total": total_count, "stats": stats}

    async def verify_invoice(self, bill_id: PydanticObjectId, current_user: User) -> Bill:
        if not await self._can_verify(current_user):
            raise HTTPException(status_code=403, detail="Permission Denied")
        bill = await self.get_bill(bill_id)
        if not bill:
            raise HTTPException(status_code=404, detail="Not Found")
        # FIX: Status transition guard — prevent re-verifying SENT/REFUNDED/ARCHIVED bills
        if bill.invoice_status not in {"PENDING_VERIFICATION", "DRAFT"}:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot verify an invoice with status: {bill.invoice_status}. Only PENDING_VERIFICATION invoices can be verified."
            )
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
        if not bill:
            raise HTTPException(status_code=404, detail="Not Found")
        # FIX: Permission check was present in old CRM, dropped in migration.
        # UI hides the button correctly but API was open to all staff directly.
        if not self._can_archive_invoice(current_user, bill):
            raise HTTPException(status_code=403, detail="You do not have permission to archive this invoice")
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

        # Mark as SENT in database
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

        # ─── Step 4 of 4: Real Meta Cloud API Integration ───
        phone_raw = bill.invoice_client_phone or ""
        clean_phone = "".join(filter(str.isdigit, phone_raw))
        if len(clean_phone) == 10:
            clean_phone = "91" + clean_phone
        # We generate the PDF and attempt to send it via Meta Cloud API.
        # If it fails, the frontend still has the fallback wa_url to open WhatsApp Web.
        
        invoice_settings = await self.get_invoice_defaults()
        html = _build_invoice_html(bill, invoice_settings, for_pdf=True)
        pdf_io = generate_bill_pdf(html)
        pdf_bytes = pdf_io.getvalue()
        
        filename = f"Invoice_{bill.invoice_number.replace('/', '_')}.pdf"
        caption = f"Hi {bill.invoice_client_name}, your invoice {bill.invoice_number} has been generated."
        
        # Clean phone for Meta (must be international format without +)
        meta_phone = clean_phone
        
        sent_via_meta = await self._send_meta_whatsapp_document(
            phone=meta_phone,
            pdf_content=pdf_bytes,
            filename=filename,
            caption=caption
        )

        # Build WhatsApp redirection URL for fallback (text-based)
        msg = f"Hi {bill.invoice_client_name},\n\nYour invoice {bill.invoice_number} for {bill.billing_month} has been generated.\n\n"
        msg += f"View/Download Invoice: {base_url}api/billing/{bill.id}/invoice-html\n\n"
        msg += "Thank you for choosing Harikrushn DigiVerse LLP!"
        
        encoded_msg = quote(msg)
        wa_url = f"https://wa.me/{clean_phone}?text={encoded_msg}"

        return {
            "bill": bill, 
            "status": "sent" if sent_via_meta else "marked_sent",
            "sent_via_meta": sent_via_meta,
            "wa_url": wa_url
        }

    async def _send_meta_whatsapp_document(self, phone: str, pdf_content: bytes, filename: str, caption: str) -> bool:
        """Sends a document via Meta Cloud API."""
        token = settings.WHATSAPP_TOKEN
        phone_id = settings.WHATSAPP_PHONE_NUMBER_ID
        
        if not token or not phone_id:
            print("[WA] Meta Cloud API credentials missing.")
            return False

        # 1. Upload Media
        upload_url = f"https://graph.facebook.com/v17.0/{phone_id}/media"
        headers = {"Authorization": f"Bearer {token}"}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                files = {
                    "file": (filename, pdf_content, "application/pdf"),
                    "type": (None, "application/pdf"),
                    "messaging_product": (None, "whatsapp"),
                }
                resp = await client.post(upload_url, headers=headers, files=files)
                if resp.status_code != 200:
                    print(f"[WA] Media Upload Failed: {resp.text}")
                    return False
                
                media_id = resp.json().get("id")
                if not media_id: return False

                # 2. Send Message
                msg_url = f"https://graph.facebook.com/v17.0/{phone_id}/messages"
                payload = {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": phone,
                    "type": "document",
                    "document": {
                        "id": media_id,
                        "filename": filename,
                        "caption": caption
                    }
                }
                resp = await client.post(msg_url, headers=headers, json=payload)
                if resp.status_code != 200:
                    print(f"[WA] Message Send Failed: {resp.text}")
                    return False
                
                print(f"[WA] Document sent successfully to {phone} (Media ID: {media_id})")
                return True
        except Exception as e:
            print(f"[WA] Meta API Exception: {e}")
            return False


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
        
        # FIX: Use bool() to handle None values from MongoDB migration (is_archived may be null)
        can_archive = self._can_archive_invoice(current_user, bill) and not bool(bill.is_archived)
        can_unarchive = self._can_archive_invoice(current_user, bill) and bool(bill.is_archived)
        can_delete = (current_user.role == UserRole.ADMIN) and bool(bill.is_archived)
        # FIX: Role-gated can_refund (was dropped in migration; any staff could refund)

        allowed_verifier_roles = list(await self._allowed_verifier_roles())

        return {
            "can_verify": can_verify,
            "can_send_whatsapp": can_send,
            "can_archive": can_archive,
            "can_unarchive": can_unarchive,
            "can_delete": can_delete,
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
        if not bill:
            raise HTTPException(status_code=404, detail="Not Found")
        # FIX: Permission check was missing (existed in old CRM, dropped in migration)
        if not self._can_archive_invoice(current_user, bill):
            raise HTTPException(status_code=403, detail="You do not have permission to unarchive this invoice")
        bill.is_archived = False
        await bill.save()
        # FIX: Activity log was missing entirely — every other status change is logged
        await ActivityLogger().log_activity(
            user_id=current_user.id,
            user_role=current_user.role,
            action=ActionType.STATUS_CHANGE,
            entity_type=EntityType.BILL,
            entity_id=bill.id,
            new_data={"archived": False}
        )
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

    # FIX: Removed duplicate permanent_delete_invoice definition (was dead code — Python used the second one)

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
        # FIX: Add role guard — was open to all staff_access roles
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Only admins can force-mark an invoice as SENT")
        bill = await self.get_bill(bill_id)
        if not bill:
            raise HTTPException(status_code=404, detail="Not Found")
        # FIX: Status guard — prevent marking a DRAFT/PENDING as SENT without verification
        if bill.invoice_status != "VERIFIED":
            raise HTTPException(
                status_code=400,
                detail=f"Force-sent only allowed on VERIFIED invoices. Current status: {bill.invoice_status}"
            )
        bill.invoice_status = "SENT"
        bill.whatsapp_sent = True
        await bill.save()
        await ActivityLogger().log_activity(
            user_id=current_user.id,
            user_role=current_user.role,
            action=ActionType.STATUS_CHANGE,
            entity_type=EntityType.BILL,
            entity_id=bill.id,
            new_data={"status": "SENT", "method": "FORCE_SENT_MANUAL"}
        )
        return bill


def _build_invoice_html(bill, settings: dict, for_pdf: bool = False) -> str:
    from datetime import datetime, timezone

    company_name    = settings.get("company_name")    or "Harikrushn DigiVerse LLP"
    company_address = settings.get("company_address") or ""
    company_phone   = settings.get("company_phone")   or ""
    company_email   = settings.get("company_email")   or ""
    company_gstin   = settings.get("company_gstin")   or ""
    company_pan     = settings.get("company_pan")     or ""
    company_cin     = settings.get("company_cin")     or ""
    company_cst     = settings.get("company_cst_code") or ""
    
    # Resolve payment details based on bill payment type
    prefix = "business_" if bill.payment_type == "BUSINESS_ACCOUNT" else "personal_" if bill.payment_type == "PERSONAL_ACCOUNT" else ""
    
    upi_id          = settings.get(f"{prefix}payment_upi_id") or settings.get("payment_upi_id") or ""
    upi_name        = settings.get(f"{prefix}payment_account_name") or settings.get("payment_account_name") or company_name
    qr_img_url      = settings.get(f"{prefix}payment_qr_image_url") or settings.get("payment_qr_image_url") or ""
    bank_name       = settings.get(f"{prefix}payment_bank_name") or settings.get("payment_bank_name") or ""
    bank_account_no = settings.get(f"{prefix}payment_account_number") or settings.get("payment_account_number") or ""
    bank_ifsc       = settings.get(f"{prefix}payment_ifsc") or settings.get("payment_ifsc") or ""
    bank_branch     = settings.get(f"{prefix}payment_branch") or settings.get("payment_branch") or ""

    header_bg = settings.get("invoice_header_bg") or "#2E5B82"

    def _is_dark_hex(hex_color: str) -> bool:
      val = (hex_color or "").strip().lstrip("#")
      if len(val) != 6:
        return True
      try:
        r = int(val[0:2], 16)
        g = int(val[2:4], 16)
        b = int(val[4:6], 16)
      except ValueError:
        return True
      luma = (0.2126 * r) + (0.7152 * g) + (0.0722 * b)
      return luma < 140

    header_is_dark = _is_dark_hex(header_bg)
    header_text = "#f8fafc" if header_is_dark else "#0f172a"
    header_sub_text = "#cbd5e1" if header_is_dark else "#334155"
    logo_src = "/frontend/images/white%20logo.png" if header_is_dark else "/frontend/images/logo.png"

    _dt = bill.created_at if bill.created_at else datetime.now(timezone.utc)
    invoice_date = _dt.strftime("%d %b %Y, %I:%M %p").lstrip("0")

    client_name    = bill.invoice_client_name    or "—"
    client_phone   = bill.invoice_client_phone   or "—"
    client_email   = bill.invoice_client_email   or ""
    client_address = bill.invoice_client_address or ""
    client_org     = bill.invoice_client_org     or ""

    service_desc   = bill.service_description or "SRM AI SETU Software – Annual Subscription"
    amount         = bill.amount or 0.0

    is_with_gst = (bill.gst_type or "WITH_GST") == "WITH_GST"

    # Amount in bill.amount is treated as total payable amount.
    # For WITH_GST invoices, split into taxable + 9% CGST + 9% SGST.
    if is_with_gst:
      subtotal = round(amount / 1.18, 2)
      cgst_rate = 9
      sgst_rate = 9
      cgst_amt = round(subtotal * cgst_rate / 100, 2)
      sgst_amt = round(subtotal * sgst_rate / 100, 2)
    else:
      subtotal = amount
      cgst_rate = 0
      sgst_rate = 0
      cgst_amt = 0.0
      sgst_amt = 0.0

    total_tax      = cgst_amt + sgst_amt
    total_before_round = subtotal + total_tax
    rounded_total  = round(total_before_round)
    round_off      = round(rounded_total - total_before_round, 2)

    if bill.payment_type == "BUSINESS_ACCOUNT":
        payment_type_label = "Bank Account"
    elif bill.payment_type == "PERSONAL_ACCOUNT":
        if is_with_gst:
            payment_type_label = "Bank Account"
        else:
            payment_type_label = "Personal Account"
    elif bill.payment_type == "CASH":
        payment_type_label = "Cash"
    else:
        payment_type_label = bill.payment_type or "-"
    gst_type_label = "With GST" if is_with_gst else "Without GST"

    status_label = {
        "DRAFT":                "Draft",
        "PENDING_VERIFICATION": "Pending",
        "VERIFIED":             "Verified",
        "SENT":                 "Paid",
    }.get(bill.invoice_status, bill.invoice_status)

    company_ids = []
    if company_gstin: company_ids.append(f"GSTIN: {company_gstin}")
    if company_pan: company_ids.append(f"PAN: {company_pan}")
    if company_cin: company_ids.append(f"LLPIN: {company_cin}")
    company_ids_str = " | ".join(company_ids)
    
    item_rate = subtotal if is_with_gst else rounded_total
    
    if is_with_gst:
        tax_cols_th = '<th style="width:80px;text-align:right;">Discount</th><th style="width:90px;text-align:right;">Taxable</th>'
        tax_cols_td = f'<td style="text-align:right;">-</td><td style="text-align:right;font-weight:700;">₹{subtotal:,.2f}</td>'
        summary_html = f"""
        <tr><td>Total Before Tax</td><td>₹{subtotal:,.2f}</td></tr>
        <tr><td>CGST ({cgst_rate}%)</td><td>₹{cgst_amt:,.2f}</td></tr>
        <tr><td>SGST ({sgst_rate}%)</td><td>₹{sgst_amt:,.2f}</td></tr>
        <tr><td>Round Off</td><td>₹{round_off:,.2f}</td></tr>
        <tr class="grand-row"><td>Total Amount</td><td>₹{rounded_total:,.2f}</td></tr>
        """
    else:
        tax_cols_th = ''
        tax_cols_td = ''
        summary_html = f"""
        <tr class="grand-row"><td>Total Amount</td><td>₹{rounded_total:,.2f}</td></tr>
        """
        
    inv_terms = settings.get("invoice_terms_conditions") or "• Subject to Surat Jurisdiction"
    terms_html = "<br>".join([line for line in inv_terms.split("\\n") if line.strip()])

    # ── Amount in words ──────────────────────────────────────────────────────
    def _num_to_words(n: int) -> str:
        if n == 0:
            return "Zero"
        ones = ["", "One","Two","Three","Four","Five","Six","Seven","Eight","Nine",
                "Ten","Eleven","Twelve","Thirteen","Fourteen","Fifteen","Sixteen",
                "Seventeen","Eighteen","Nineteen"]
        tens = ["","","Twenty","Thirty","Forty","Fifty","Sixty","Seventy","Eighty","Ninety"]
        def _below_1000(num):
            if num == 0: return ""
            if num < 20: return ones[num]
            if num < 100: return tens[num // 10] + (" " + ones[num % 10] if num % 10 else "")
            return ones[num // 100] + " Hundred" + (" " + _below_1000(num % 100) if num % 100 else "")
        parts = []
        cr = n // 10000000; n %= 10000000
        lk = n // 100000;   n %= 100000
        th = n // 1000;     n %= 1000
        if cr: parts.append(_below_1000(cr) + " Crore")
        if lk: parts.append(_below_1000(lk) + " Lakh")
        if th: parts.append(_below_1000(th) + " Thousand")
        if n:  parts.append(_below_1000(n))
        return " ".join(parts)

    amount_words = _num_to_words(int(rounded_total)) + " Only"

    # ── PDF vs WEB Style Handling ────────────────────────────────────────────
    # xhtml2pdf does not support CSS Variables, Flexbox, or Grid. 
    # For PDF, we must use Tables for layout and inline/explicit styles.
    
    if for_pdf:
        # PDF Specific Styles (Table based layout)
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  @page {{ size: A4; margin: 1cm; }}
  body {{ font-family: Helvetica, Arial, sans-serif; font-size: 11pt; color: #111; margin: 0; padding: 0; }}
  .co-header {{ background-color: {header_bg}; color: {header_text}; padding: 15px; margin-bottom: 15px; }}
  .co-name {{ font-size: 18pt; font-weight: bold; }}
  .co-sub {{ font-size: 9pt; color: {header_sub_text}; }}
  .ti-label {{ font-size: 20pt; font-weight: bold; text-align: right; }}
  .meta-tbl td {{ font-size: 10pt; color: {header_text}; }}
  .status-chip {{ border: 1px solid {header_text}; padding: 2px 8px; font-size: 9pt; font-weight: bold; margin-top: 5px; }}
  
  .sec-head {{ background-color: {header_bg}; color: {header_text}; font-size: 10pt; font-weight: bold; padding: 5px 10px; text-transform: uppercase; margin-top: 15px; }}
  
  table.full-width {{ width: 100%; border-collapse: collapse; }}
  table.grid-tbl th, table.grid-tbl td {{ border: 1px solid #ccc; padding: 8px; font-size: 10pt; }}
  table.grid-tbl th {{ background-color: {header_bg}; color: {header_text}; font-weight: bold; text-align: center; }}
  
  .items-tbl th {{ background-color: {header_bg}; color: {header_text}; padding: 10px; font-size: 10pt; text-align: left; }}
  .items-tbl td {{ border: 1px solid #eee; padding: 12px 10px; font-size: 10pt; }}
  
  .summary-box {{ width: 250px; margin-left: auto; border-collapse: collapse; }}
  .summary-box td {{ border: 1px solid #eee; padding: 8px 12px; font-size: 10pt; }}
  .grand-row td {{ background-color: {header_bg}; color: {header_text}; font-weight: bold; font-size: 12pt; }}
  
  .words-strip {{ border: 1px solid #eee; padding: 12px; font-size: 10pt; margin: 15px 0; }}
  .footer-tbl td {{ padding-top: 50px; text-align: center; font-size: 9pt; }}
  .sign-line {{ border-top: 1.5px solid #111; width: 150px; margin: 0 auto 5px; }}
</style>
</head>
<body>
  <div class="co-header">
    <table class="full-width">
      <tr>
        <td width="60%">
          <div class="co-name">{company_name}</div>
          <div class="co-sub">{company_address}</div>
          <div class="co-sub">Phone: {company_phone} | Email: {company_email}</div>
          <div class="co-sub">{company_ids_str}</div>
        </td>
        <td width="40%" align="right">
          <div class="ti-label">TAX INVOICE</div>
          <table align="right" class="meta-tbl">
            <tr><td align="right">Invoice No:</td><td><b>{bill.invoice_number}</b></td></tr>
            <tr><td align="right">Date:</td><td><b>{invoice_date}</b></td></tr>
          </table>
          <br>
          <div class="status-chip">{status_label}</div>
        </td>
      </tr>
    </table>
  </div>

  <div class="sec-head">Bill Details</div>
  <table class="full-width grid-tbl">
    <thead>
      <tr>
        <th>Reverse Charge</th>
        <th>State</th>
        <th>Code</th>
        <th>Place of Supply</th>
        <th>Payment Type</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td align="center">No</td>
        <td align="center">Gujarat</td>
        <td align="center">24</td>
        <td align="center">NA</td>
        <td align="center">{payment_type_label}</td>
      </tr>
    </tbody>
  </table>

  <div class="sec-head">Bill To Party</div>
  <table class="full-width grid-tbl">
    <thead>
      <tr>
        <th align="left" width="55%">Customer Details</th>
        <th width="22%">GSTIN</th>
        <th width="23%">PAN</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>
          <div style="font-size:12pt; font-weight:bold;">{client_name}</div>
          {f'<i>{client_org}</i><br>' if client_org else ''}
          {f'Email: {client_email}<br>' if client_email else ''}
          {f'Phone: {client_phone}<br>' if client_phone and client_phone != "—" else ''}
          {client_address}
        </td>
        <td align="center">N.A</td>
        <td align="center">N.A</td>
      </tr>
    </tbody>
  </table>

  <div class="sec-head">Product / Service</div>
  <table class="full-width grid-tbl items-tbl">
    <thead>
      <tr>
        <th width="30" align="center">S.No</th>
        <th>Description</th>
        <th width="60" align="center">SAC</th>
        <th width="40" align="center">Qty</th>
        <th width="100" align="right">Rate</th>
        <th width="100" align="right">Amount</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td align="center">1</td>
        <td><b>{service_desc}</b></td>
        <td align="center">9992</td>
        <td align="center">1</td>
        <td align="right">₹{item_rate:,.2f}</td>
        <td align="right">₹{item_rate:,.2f}</td>
      </tr>
    </tbody>
  </table>

  <table class="summary-box">
    {summary_html.replace('<td>', '<td align="left">')}
  </table>

  <div class="words-strip">
    <b>IN WORDS:</b> {amount_words}
  </div>

  <div class="sec-head">Terms &amp; Conditions</div>
  <div style="padding: 10px; font-size: 9pt; color: #555; border: 1px solid #eee;">
    {terms_html}
  </div>

  <table class="full-width footer-tbl">
    <tr>
      <td width="50%">
        <div class="sign-line"></div>
        Received By, Signed &amp; Stamped
      </td>
      <td width="50%">
        <div class="sign-line"></div>
        For {company_name}<br>Authorised Signatory
      </td>
    </tr>
  </table>
  
  <div style="font-size: 8pt; color: #aaa; text-align: right; margin-top: 10px;">
    This is a computer generated invoice.
  </div>
</body>
</html>"""

    # WEB Version (Browser optimized with Flex/Grid/Variables)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Tax Invoice — {bill.invoice_number}</title>
<style>
  *{{margin:0;padding:0;box-sizing:border-box;}}
  @page{{size:A4;margin:0;}}
  :root{{--invoice-accent:{header_bg};--invoice-accent-text:{header_text};--invoice-light-border:#d1d5db;}}
  body{{font-family:Arial,Helvetica,sans-serif;background:#f4f6f9;font-size:14px;color:#111;}}
  .wrapper{{width:210mm;min-height:297mm;margin:0 auto;background:#fff;}}
  /* ── print bar ── */
  .print-bar{{background:var(--invoice-accent);padding:10px 18px;display:flex;gap:10px;align-items:center;}}
  .print-bar button{{border:none;padding:8px 22px;font-size:13px;font-weight:700;border-radius:6px;cursor:pointer;}}
  .btn-print{{background:var(--invoice-accent);color:#fff;}}
  .btn-close{{background:var(--invoice-accent);color:#fff;}}
  @media print{{.print-bar{{display:none!important;}}body{{background:#fff;-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important;}}}}
  /* ── invoice page ── */
  .inv-page{{padding:4mm 4mm 4mm 4mm;}}
  /* company header */
  .co-header{{display:flex;justify-content:space-between;align-items:flex-start;
    border:1px solid #d1d5db;padding:8px 10px;margin-bottom:8px;}}
  .co-left .co-name{{font-size:17px;font-weight:900;letter-spacing:.2px;}}
  .co-left .co-sub{{font-size:11.5px;margin-top:3px;max-width:420px;line-height:1.5;}}
  .co-right{{text-align:right;}}
  .co-right .ti-label{{font-size:16px;font-weight:900;letter-spacing:.6px;}}
  .co-right table td{{font-size:12px;padding:1px 4px;}}
  .co-right table td:first-child{{color:inherit;opacity:0.8;text-align:right;white-space:nowrap;}}
  .co-right table td:last-child{{font-weight:700;text-align:left;}}
  .status-chip{{display:inline-block;margin-top:6px;padding:3px 10px;
    border:1.5px solid currentColor;font-size:11px;font-weight:800;letter-spacing:1px;
    text-transform:uppercase;border-radius:3px;}}
  /* section heading rows */
  .sec-head{{font-size:11px;font-weight:800;letter-spacing:1.2px;text-transform:uppercase;
    background:var(--invoice-accent);padding:4px 8px;color:var(--invoice-accent-text);border-bottom:1px solid var(--invoice-light-border);}}
  /* bordered grid tables */
  .grid-tbl{{width:100%;border-collapse:collapse;margin-bottom:8px;}}
  .grid-tbl th,.grid-tbl td{{border:1px solid #ccc;padding:6px 8px;font-size:13px;}}
  .grid-tbl thead th{{background:var(--invoice-accent);font-weight:800;text-align:center;font-size:12px;
    text-transform:uppercase;letter-spacing:.5px;color:var(--invoice-accent-text);}}
  /* items table */
  .items-tbl{{width:100%;border-collapse:collapse;margin-bottom:8px;}}
  .items-tbl th{{background:var(--invoice-accent);color:var(--invoice-accent-text);padding:8px 8px;font-size:12px;
    letter-spacing:.6px;text-transform:uppercase;font-weight:700;border:1px solid var(--invoice-accent);}}
  .items-tbl td{{border:1px solid #dde1e7;padding:8px 8px;vertical-align:top;font-size:13px;}}
  .items-tbl tbody tr:nth-child(even){{background:#ffffff;}}
  /* summary */
  .summary-tbl{{width:100%;border-collapse:collapse;}}
  .summary-tbl td{{border:1px solid #dde1e7;padding:6px 10px;font-size:13px;}}
  .summary-tbl td:last-child{{text-align:right;font-weight:600;}}
  .summary-tbl .grand-row td{{background:var(--invoice-accent);color:var(--invoice-accent-text);font-weight:800;font-size:14.5px;border-color:var(--invoice-accent);}}
  /* words strip */
  .words-strip{{border:1px solid #dde1e7;padding:8px 12px;font-size:13px;
    margin-bottom:8px;background:#ffffff;}}
  /* footer */
  .inv-footer{{border-top:1.5px solid #222;margin-top:8px;padding-top:8px;
    display:flex;justify-content:space-between;align-items:flex-end;}}
  .sign-block{{text-align:center;}}
  .sign-line{{width:160px;border-top:1.5px solid #111;margin-bottom:4px;margin-top:24px;}}
  .sign-lbl{{font-size:10px;color:#555;}}
  .powered{{font-size:9.5px;color:#94a3b8;margin-top:6px;text-align:right;}}
</style>
</head>
<body>
<div class="wrapper">

  <!-- Print bar -->
  <div class="print-bar no-print">
    <button class="btn-print" onclick="window.print()">🖨&nbsp; Print / Save PDF</button>
    <button class="btn-close" onclick="window.parent.postMessage('close-invoice-preview', '*'); window.close();">✕ Close</button>
  </div>

  <div class="inv-page">

    <!-- ── COMPANY HEADER ── -->
    <div class="co-header" style="background:{header_bg};color:{header_text};">
      <div class="co-left">
        <img src="{logo_src}" alt="AI SETU Logo" onerror="this.style.display='none'" style="height:44px;object-fit:contain;margin-bottom:4px;display:block;">
        <div class="co-name">{company_name}</div>
        {'<div class="co-sub" style="color:' + header_sub_text + ';">' + company_address + '</div>' if company_address else ''}
        {'<div class="co-sub" style="color:' + header_sub_text + ';">Phone: ' + company_phone + ' | Email: ' + company_email + '</div>' if (company_phone or company_email) else ''}
        {f'<div class="co-sub" style="color:{header_sub_text};">' + company_ids_str + '</div>' if company_ids_str else ''}
      </div>
      <div class="co-right">
        <div class="ti-label">Tax Invoice</div>
        <table style="margin-left:auto;margin-top:6px;color:{header_text};">
          <tr><td>Invoice No:</td><td>{bill.invoice_number}</td></tr>
          <tr><td>Date:</td><td>{invoice_date}</td></tr>
        </table>
        <div class="status-chip">{status_label}</div>
      </div>
    </div>

    <!-- ── BILL DETAILS ── -->
    <div class="sec-head">Bill Details</div>
    <table class="grid-tbl" style="margin-bottom:10px;">
      <thead>
        <tr>
          <th>Reverse Charge</th>
          <th>State</th>
          <th>Code</th>
          <th>Place of Supply</th>
          <th>Payment Type</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td style="text-align:center;">No</td>
          <td style="text-align:center;">Gujarat</td>
          <td style="text-align:center;">24</td>
          <td style="text-align:center;">NA</td>
          <td style="text-align:center;">{payment_type_label}</td>
        </tr>
      </tbody>
    </table>

    <!-- ── BILL TO PARTY ── -->
    <div class="sec-head">Bill To Party</div>
    <table class="grid-tbl" style="margin-bottom:10px;">
      <thead>
        <tr>
          <th style="width:55%;">Customer Details</th>
          <th style="width:22%;">GSTIN</th>
          <th style="width:23%;">PAN</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>
            <strong style="font-size:14px;">{client_name}</strong>
            {'<br><em>' + client_org + '</em>' if client_org else ''}
            {'<br><span style="color:#444;">Email: ' + client_email + '</span>' if client_email else ''}
            {'<br>Phone: ' + client_phone if client_phone and client_phone != '—' else ''}
            {'<br>' + client_address if client_address else ''}
          </td>
          <td style="text-align:center;color:#555;">N.A</td>
          <td style="text-align:center;color:#555;">N.A</td>
        </tr>
      </tbody>
    </table>

    <!-- ── PRODUCT / SERVICE ── -->
    <div class="sec-head">Product / Service</div>
    <table class="items-tbl" style="margin-bottom:10px;">
      <thead>
        <tr>
          <th style="width:36px;text-align:center;">S.No</th>
          <th>Description</th>
          <th style="width:60px;text-align:center;">SAC</th>
          <th style="width:40px;text-align:center;">Qty</th>
          <th style="width:100px;text-align:right;">Rate</th>
          <th style="width:100px;text-align:right;">Amount</th>
          {tax_cols_th}
        </tr>
      </thead>
      <tbody>
        <tr>
          <td style="text-align:center;">1</td>
          <td style="font-weight:600;">{service_desc}</td>
          <td style="text-align:center;">9992</td>
          <td style="text-align:center;">1</td>
          <td style="text-align:right;">₹{item_rate:,.2f}</td>
          <td style="text-align:right;">₹{item_rate:,.2f}</td>
          {tax_cols_td}
        </tr>
      </tbody>
    </table>

    <!-- ── SUMMARY ── -->
    <div class="sec-head">Summary</div>
    <div style="display:flex;gap:16px;margin-bottom:10px;">
      <table class="summary-tbl" style="flex:1;">
        {summary_html}
      </table>
    </div>

    <!-- ── AMOUNT IN WORDS ── -->
    <div class="words-strip">
      <strong>IN WORDS:</strong> {amount_words}
    </div>


    <!-- ── TERMS ── -->
    <div class="sec-head" style="margin-top:10px;">Terms &amp; Conditions</div>
    <div style="padding:10px 14px;font-size:12px;color:#555;border:1px solid #dde1e7;border-top:none;line-height:1.5;">
      {terms_html}
    </div>

    <!-- ── FOOTER ── -->
    <div class="inv-footer">
      <div class="sign-block">
        <div class="sign-line"></div>
        <div class="sign-lbl">Received By, Signed &amp; Stamped</div>
      </div>
      <div class="sign-block">
        <div class="sign-line"></div>
        <div class="sign-lbl">For {company_name}<br>Authorised Signatory</div>
      </div>
    </div>
    <div class="powered">This is a computer generated invoice. For support, contact {company_phone or company_address or company_name}.</div>

  </div><!-- /inv-page -->
</div><!-- /wrapper -->
</body>
</html>"""

