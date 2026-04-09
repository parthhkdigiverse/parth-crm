"""
migrate_db.py — One-Time ETL: PostgreSQL → MongoDB Atlas
==========================================================
Reads data from your existing local PostgreSQL database using raw SQLAlchemy
Core (no ORM models needed on the Postgres side) and writes it into MongoDB
using your new Beanie Document models.

Usage:
    cd "d:\\Office Work\\CRM SETU Feature Upgrade\\CRM_AI_SETU"
    venv\\Scripts\\python migrate_db.py

Requirements already in venv:
    sqlalchemy, psycopg2, motor, beanie, pydantic

IMPORTANT:
  - Run this ONCE against a fresh (empty) MongoDB database.
  - Back up your Postgres DB before running.
  - Set POSTGRES_URL and MONGODB_URI below, or let them load from .env.
"""

import asyncio
import sys
import os
from datetime import datetime, timezone, date
from urllib.parse import urlparse, unquote
from bson import ObjectId

# ─── Path bootstrap (allows importing from backend/) ────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)

# ─── SQLAlchemy (Postgres READ) ──────────────────────────────────────────────
import psycopg2
from sqlalchemy import create_engine, text, inspect as sa_inspect

# ─── Beanie / Motor (MongoDB WRITE) ─────────────────────────────────────────
import motor.motor_asyncio
from beanie import init_beanie, PydanticObjectId

# ─── Load .env ───────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(os.path.join(BACKEND, ".env"))

# ════════════════════════════════════════════════════════════════════════════
# CONFIGURATION — edit these or export as environment variables
# ════════════════════════════════════════════════════════════════════════════
POSTGRES_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/AI SETU")
MONGODB_URI  = os.getenv("MONGODB_URI",  "mongodb+srv://user:pass@cluster0.xxxxx.mongodb.net/aisetu_srm")
MONGO_DB_NAME = "aisetu_srm"

# ════════════════════════════════════════════════════════════════════════════
# Postgres connection helper (handles spaces in DB names)
# ════════════════════════════════════════════════════════════════════════════
def _pg_connection():
    parsed = urlparse(POSTGRES_URL)
    return psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        dbname=unquote(parsed.path.lstrip("/")),
        user=parsed.username,
        password=unquote(parsed.password) if parsed.password else "",
    )

def make_pg_engine():
    return create_engine("postgresql+psycopg2://", creator=_pg_connection)

# ════════════════════════════════════════════════════════════════════════════
# ID Mapping — central registry for int → ObjectId translation
# ════════════════════════════════════════════════════════════════════════════
id_map: dict[str, dict[int, ObjectId]] = {}

def new_oid(table: str, pg_id: int) -> ObjectId:
    """Generate a new ObjectId for a given postgres table + row id,
    storing the mapping so FK references can resolve it later."""
    oid = ObjectId()
    id_map.setdefault(table, {})[pg_id] = oid
    return oid

def resolve(table: str, pg_id) -> PydanticObjectId | None:
    """Resolve a postgres int FK to its new MongoDB ObjectId."""
    if pg_id is None:
        return None
    oid = id_map.get(table, {}).get(int(pg_id))
    if oid is None:
        return None
    return PydanticObjectId(str(oid))

def safe_dt(val) -> datetime | None:
    """Normalise datetime to UTC-aware or None."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    return None

def safe_date(val) -> date | None:
    if isinstance(val, date):
        return val
    return None

def row_dict(row) -> dict:
    """Convert a SQLAlchemy Row to a plain dict."""
    return dict(row._mapping)

# ════════════════════════════════════════════════════════════════════════════
# Import all Beanie document models
# ════════════════════════════════════════════════════════════════════════════
from app.modules.users.models        import User, UserRole
from app.modules.areas.models        import Area
from app.modules.shops.models        import Shop
from app.modules.clients.models      import Client, ClientPMHistory
from app.modules.projects.models     import Project
from app.modules.visits.models       import Visit, VisitStatus
from app.modules.issues.models       import Issue, IssueSeverity
from app.modules.meetings.models     import MeetingSummary, MeetingType
from app.modules.feedback.models     import Feedback, UserFeedback
from app.modules.payments.models     import Payment, PaymentStatus
from app.modules.billing.models      import Bill
from app.modules.salary.models       import LeaveRecord, SalarySlip, LeaveStatus, AppSetting
from app.modules.incentives.models   import IncentiveSlab, EmployeePerformance, IncentiveSlip
from app.modules.notifications.models import Notification
from app.modules.settings.models     import SystemSettings
from app.core.enums                  import GlobalTaskStatus

ALL_DOCUMENT_MODELS = [
    User, Area, Shop, Client, Project,
    Visit, Issue, MeetingSummary,
    Feedback, UserFeedback,
    Payment, Bill,
    LeaveRecord, SalarySlip, AppSetting,
    IncentiveSlab, EmployeePerformance, IncentiveSlip,
    Notification, SystemSettings,
]

# ════════════════════════════════════════════════════════════════════════════
# MIGRATION FUNCTIONS
# ════════════════════════════════════════════════════════════════════════════

async def migrate_users(conn):
    print("\n[1/15] Migrating USERS …")
    rows = conn.execute(text("SELECT * FROM users ORDER BY id")).fetchall()
    inserted = 0
    for r in rows:
        d = row_dict(r)
        pg_id = d["id"]
        oid = new_oid("users", pg_id)

        # Map role string to enum, defaulting to TELESALES
        try:
            role = UserRole(d.get("role", "TELESALES"))
        except ValueError:
            role = UserRole.TELESALES

        doc = User(
            id=PydanticObjectId(str(oid)),
            email=d.get("email", f"user_{pg_id}@placeholder.local"),
            hashed_password=d.get("hashed_password", ""),
            name=d.get("name"),
            phone=d.get("phone"),
            role=role,
            referral_code=d.get("referral_code"),
            is_active=bool(d.get("is_active", True)),
            is_deleted=bool(d.get("is_deleted", False)),
            preferences={},
            employee_code=d.get("employee_code"),
            joining_date=safe_date(d.get("joining_date")),
            base_salary=float(d.get("base_salary") or 0),
            target=int(d.get("target") or 0),
            incentive_enabled=bool(d.get("incentive_enabled", True)),
            department=d.get("department"),
        )
        await doc.insert()
        inserted += 1
    print(f"    ✓ {inserted} users inserted.")


async def migrate_areas(conn):
    print("\n[2/15] Migrating AREAS …")
    if not sa_inspect(conn).has_table("areas"):
        print("    ⚠ Table 'areas' not found in Postgres — skipping.")
        return

    rows = conn.execute(text("SELECT * FROM areas ORDER BY id")).fetchall()
    inserted = 0
    for r in rows:
        d = row_dict(r)
        pg_id = d["id"]
        oid = new_oid("areas", pg_id)

        # Fetch M2M area_assignments
        assigned_ids = []
        try:
            aa = conn.execute(
                text("SELECT user_id FROM area_assignments WHERE area_id = :aid"),
                {"aid": pg_id}
            ).fetchall()
            assigned_ids = [PydanticObjectId(str(id_map["users"][a[0]])) for a in aa if a[0] in id_map.get("users", {})]
        except Exception:
            pass

        doc = Area(
            id=PydanticObjectId(str(oid)),
            name=d.get("name", f"Area_{pg_id}"),
            description=d.get("description"),
            pincode=d.get("pincode"),
            city=d.get("city"),
            assigned_user_id=resolve("users", d.get("assigned_user_id")),
            lat=d.get("lat"),
            lng=d.get("lng"),
            is_deleted=bool(d.get("is_deleted", False)),
            is_archived=bool(d.get("is_archived", False)),
            archived_by_id=resolve("users", d.get("archived_by_id")),
            assignment_status=d.get("assignment_status", "UNASSIGNED"),
            assigned_by_id=resolve("users", d.get("assigned_by_id")),
            accepted_at=safe_dt(d.get("accepted_at")),
            created_by_id=resolve("users", d.get("created_by_id")),
            radius_meters=int(d.get("radius_meters") or 500),
            shop_limit=int(d.get("shop_limit") or 20),
            priority_level=d.get("priority_level", "MEDIUM"),
            auto_discovery_enabled=bool(d.get("auto_discovery_enabled", False)),
            assigned_user_ids=assigned_ids,
        )
        await doc.insert()
        inserted += 1
    print(f"    ✓ {inserted} areas inserted.")


async def migrate_shops(conn):
    print("\n[3/15] Migrating SHOPS …")
    rows = conn.execute(text("SELECT * FROM shops ORDER BY id")).fetchall()
    inserted = 0
    for r in rows:
        d = row_dict(r)
        pg_id = d["id"]
        oid = new_oid("shops", pg_id)

        # Fetch M2M shop_assignments (owner assignment list)
        assigned_owner_ids = []
        try:
            sa = conn.execute(
                text("SELECT user_id FROM shop_assignments WHERE shop_id = :sid"),
                {"sid": pg_id}
            ).fetchall()
            assigned_owner_ids = [
                PydanticObjectId(str(id_map["users"][a[0]]))
                for a in sa if a[0] in id_map.get("users", {})
            ]
        except Exception:
            pass

        # Map pipeline_stage / status
        from app.core.enums import MasterPipelineStage
        stage_val = d.get("pipeline_stage") or d.get("status") or "LEAD"
        try:
            pipeline_stage = MasterPipelineStage(stage_val)
        except ValueError:
            pipeline_stage = MasterPipelineStage.LEAD

        doc = Shop(
            id=PydanticObjectId(str(oid)),
            name=d.get("name", f"Shop_{pg_id}"),
            address=d.get("address"),
            contact_person=d.get("contact_person"),
            phone=d.get("phone"),
            email=d.get("email"),
            source=d.get("source", "Other"),
            project_type=d.get("project_type"),
            requirements=d.get("requirements"),
            pipeline_stage=pipeline_stage,
            is_deleted=bool(d.get("is_deleted", False)),
            is_archived=bool(d.get("is_archived", False)),
            archived_by_id=resolve("users", d.get("archived_by_id")),
            owner_id=resolve("users", d.get("owner_id")),
            area_id=resolve("areas", d.get("area_id")),
            client_id=resolve("clients", d.get("client_id")),
            created_at=safe_dt(d.get("created_at")) or datetime.now(timezone.utc),
            assignment_status=d.get("assignment_status", "UNASSIGNED"),
            assigned_by_id=resolve("users", d.get("assigned_by_id")),
            accepted_at=safe_dt(d.get("accepted_at")),
            created_by_id=resolve("users", d.get("created_by_id")),
            project_manager_id=resolve("users", d.get("project_manager_id")),
            demo_stage=int(d.get("demo_stage") or 0),
            demo_scheduled_at=safe_dt(d.get("demo_scheduled_at")),
            demo_title=d.get("demo_title"),
            demo_type=d.get("demo_type"),
            demo_notes=d.get("demo_notes"),
            demo_meet_link=d.get("demo_meet_link"),
            scheduled_by_id=resolve("users", d.get("scheduled_by_id")),
            assigned_owner_ids=assigned_owner_ids,
        )
        await doc.insert()
        inserted += 1
    print(f"    ✓ {inserted} shops inserted.")


async def migrate_clients(conn):
    print("\n[4/15] Migrating CLIENTS …")
    rows = conn.execute(text("SELECT * FROM clients ORDER BY id")).fetchall()
    inserted = 0
    for r in rows:
        d = row_dict(r)
        pg_id = d["id"]
        oid = new_oid("clients", pg_id)

        # Fetch embedded PM history from old SQL table
        pm_history_docs = []
        try:
            ph_rows = conn.execute(
                text("SELECT pm_id, assigned_at FROM client_pm_history WHERE client_id = :cid ORDER BY assigned_at"),
                {"cid": pg_id}
            ).fetchall()
            for ph in ph_rows:
                pm_mongo_id = resolve("users", ph[0])
                if pm_mongo_id:
                    pm_history_docs.append(ClientPMHistory(
                        pm_id=pm_mongo_id,
                        assigned_at=safe_dt(ph[1]) or datetime.now(timezone.utc),
                    ))
        except Exception:
            pass

        doc = Client(
            id=PydanticObjectId(str(oid)),
            name=d.get("name", f"Client_{pg_id}"),
            email=d.get("email"),
            phone=d.get("phone", f"0000000{pg_id:04d}"),
            organization=d.get("organization"),
            address=d.get("address"),
            project_type=d.get("project_type"),
            requirements=d.get("requirements"),
            referral_code=d.get("referral_code"),
            referred_by_id=resolve("users", d.get("referred_by_id")),
            owner_id=resolve("users", d.get("owner_id")),
            pm_id=resolve("users", d.get("pm_id")),
            pm_assigned_by_id=resolve("users", d.get("pm_assigned_by_id")),
            pm_history=pm_history_docs,
            is_active=bool(d.get("is_active", True)),
            status=d.get("status", "ACTIVE"),
            is_deleted=bool(d.get("is_deleted", False)),
            created_at=safe_dt(d.get("created_at")) or datetime.now(timezone.utc),
        )
        await doc.insert()
        inserted += 1
    print(f"    ✓ {inserted} clients inserted.")


async def migrate_projects(conn):
    print("\n[5/15] Migrating PROJECTS …")
    if not sa_inspect(conn).has_table("projects"):
        print("    ⚠ Table 'projects' not found — skipping.")
        return
    rows = conn.execute(text("SELECT * FROM projects ORDER BY id")).fetchall()
    inserted = 0
    for r in rows:
        d = row_dict(r)
        pg_id = d["id"]
        oid = new_oid("projects", pg_id)

        client_id = resolve("clients", d.get("client_id"))
        pm_id = resolve("users", d.get("pm_id"))
        if not client_id or not pm_id:
            print(f"    ⚠ Project {pg_id} skipped: missing client/pm FK resolution.")
            continue

        try:
            status = GlobalTaskStatus(d.get("status", "OPEN"))
        except ValueError:
            status = GlobalTaskStatus.OPEN

        doc = Project(
            id=PydanticObjectId(str(oid)),
            name=d.get("name", f"Project_{pg_id}"),
            description=d.get("description"),
            client_id=client_id,
            pm_id=pm_id,
            status=status,
            start_date=safe_dt(d.get("start_date")),
            end_date=safe_dt(d.get("end_date")),
            budget=float(d.get("budget") or 0),
            is_deleted=bool(d.get("is_deleted", False)),
            created_at=safe_dt(d.get("created_at")) or datetime.now(timezone.utc),
            updated_at=safe_dt(d.get("updated_at")) or datetime.now(timezone.utc),
        )
        await doc.insert()
        inserted += 1
    print(f"    ✓ {inserted} projects inserted.")


async def migrate_visits(conn):
    print("\n[6/15] Migrating VISITS …")
    rows = conn.execute(text("SELECT * FROM visits ORDER BY id")).fetchall()
    inserted = 0
    for r in rows:
        d = row_dict(r)
        pg_id = d["id"]
        oid = new_oid("visits", pg_id)

        shop_id = resolve("shops", d.get("shop_id"))
        user_id = resolve("users", d.get("user_id"))
        if not shop_id or not user_id:
            print(f"    ⚠ Visit {pg_id} skipped: missing shop/user FK.")
            continue

        try:
            vstatus = VisitStatus(d.get("status", "SATISFIED"))
        except ValueError:
            vstatus = VisitStatus.SATISFIED

        doc = Visit(
            id=PydanticObjectId(str(oid)),
            shop_id=shop_id,
            user_id=user_id,
            status=vstatus,
            remarks=d.get("remarks"),
            decline_remarks=d.get("decline_remarks"),
            visit_date=safe_dt(d.get("visit_date")) or datetime.now(timezone.utc),
            photo_url=d.get("photo_url"),
            storefront_photo_url=d.get("storefront_photo_url"),
            selfie_photo_url=d.get("selfie_photo_url"),
            duration_seconds=int(d.get("duration_seconds") or 0),
            created_at=safe_dt(d.get("created_at")) or datetime.now(timezone.utc),
            updated_at=safe_dt(d.get("updated_at")) or datetime.now(timezone.utc),
            is_deleted=bool(d.get("is_deleted", False)),
        )
        await doc.insert()
        inserted += 1
    print(f"    ✓ {inserted} visits inserted.")


async def migrate_issues(conn):
    print("\n[7/15] Migrating ISSUES …")
    if not sa_inspect(conn).has_table("issues"):
        print("    ⚠ Table 'issues' not found — skipping.")
        return
    rows = conn.execute(text("SELECT * FROM issues ORDER BY id")).fetchall()
    inserted = 0
    for r in rows:
        d = row_dict(r)
        pg_id = d["id"]
        oid = new_oid("issues", pg_id)

        client_id = resolve("clients", d.get("client_id"))
        reporter_id = resolve("users", d.get("reporter_id"))
        if not client_id or not reporter_id:
            print(f"    ⚠ Issue {pg_id} skipped: missing client/reporter FK.")
            continue

        try:
            status = GlobalTaskStatus(d.get("status", "OPEN"))
        except ValueError:
            status = GlobalTaskStatus.OPEN

        try:
            severity = IssueSeverity(d.get("severity", "MEDIUM"))
        except ValueError:
            severity = IssueSeverity.MEDIUM

        doc = Issue(
            id=PydanticObjectId(str(oid)),
            title=d.get("title", f"Issue_{pg_id}"),
            description=d.get("description"),
            status=status,
            severity=severity,
            remarks=d.get("remarks"),
            is_deleted=bool(d.get("is_deleted", False)),
            opened_at=safe_dt(d.get("opened_at")),
            created_at=safe_dt(d.get("created_at")) or datetime.now(timezone.utc),
            updated_at=safe_dt(d.get("updated_at")) or datetime.now(timezone.utc),
            client_id=client_id,
            project_id=resolve("projects", d.get("project_id")),
            reporter_id=reporter_id,
            assigned_to_id=resolve("users", d.get("assigned_to_id")),
            assigned_group=d.get("assigned_group"),
        )
        await doc.insert()
        inserted += 1
    print(f"    ✓ {inserted} issues inserted.")


async def migrate_meetings(conn):
    print("\n[8/15] Migrating MEETINGS …")
    if not sa_inspect(conn).has_table("meeting_summaries"):
        print("    ⚠ Table 'meeting_summaries' not found — skipping.")
        return

    rows = conn.execute(text("SELECT * FROM meeting_summaries ORDER BY id")).fetchall()
    inserted = 0
    for r in rows:
        d = row_dict(r)
        pg_id = d["id"]
        oid = new_oid("meetings", pg_id)

        # Fetch attendees from the old meeting_participants junction table
        attendee_ids = []
        try:
            prt = conn.execute(
                text("SELECT user_id FROM meeting_participants WHERE meeting_id = :mid"),
                {"mid": pg_id}
            ).fetchall()
            attendee_ids = [
                PydanticObjectId(str(id_map["users"][p[0]]))
                for p in prt if p[0] in id_map.get("users", {})
            ]
        except Exception:
            pass

        try:
            status = GlobalTaskStatus(d.get("status", "OPEN"))
        except ValueError:
            status = GlobalTaskStatus.OPEN

        try:
            meeting_type = MeetingType(d.get("meeting_type", "In-Person"))
        except ValueError:
            meeting_type = MeetingType.IN_PERSON

        doc = MeetingSummary(
            id=PydanticObjectId(str(oid)),
            title=d.get("title", f"Meeting_{pg_id}"),
            content=d.get("content", ""),
            date=safe_dt(d.get("date")) or datetime.now(timezone.utc),
            status=status,
            meeting_type=meeting_type,
            meet_link=d.get("meet_link"),
            calendar_event_id=d.get("calendar_event_id"),
            transcript=d.get("transcript"),
            cancellation_reason=d.get("cancellation_reason"),
            client_id=resolve("clients", d.get("client_id")),
            host_id=resolve("users", d.get("host_id")),
            attendee_ids=attendee_ids,
            is_deleted=bool(d.get("is_deleted", False)),
            reminder_sent=bool(d.get("reminder_sent", False)),
            priority=d.get("priority", "MEDIUM"),
        )
        await doc.insert()
        inserted += 1
    print(f"    ✓ {inserted} meetings inserted.")


async def migrate_feedback(conn):
    print("\n[9/15] Migrating FEEDBACK …")
    # Client feedback
    if sa_inspect(conn).has_table("feedbacks"):
        rows = conn.execute(text("SELECT * FROM feedbacks ORDER BY id")).fetchall()
        inserted = 0
        for r in rows:
            d = row_dict(r)
            doc = Feedback(
                client_id=resolve("clients", d.get("client_id")),
                client_name=d.get("client_name"),
                mobile=d.get("mobile"),
                shop_name=d.get("shop_name"),
                product=d.get("product"),
                rating=int(d.get("rating") or 0),
                comments=d.get("comments"),
                agent_name=d.get("agent_name"),
                referral_code=d.get("referral_code"),
                created_at=safe_dt(d.get("created_at")) or datetime.now(timezone.utc),
                is_deleted=bool(d.get("is_deleted", False)),
            )
            await doc.insert()
            inserted += 1
        print(f"    ✓ {inserted} client feedbacks inserted.")

    # User feedback
    if sa_inspect(conn).has_table("user_feedbacks"):
        rows = conn.execute(text("SELECT * FROM user_feedbacks ORDER BY id")).fetchall()
        inserted = 0
        for r in rows:
            d = row_dict(r)
            user_oid = resolve("users", d.get("user_id"))
            if not user_oid:
                continue
            doc = UserFeedback(
                user_id=user_oid,
                subject=d.get("subject", ""),
                message=d.get("message", ""),
                status=d.get("status", "PENDING"),
                created_at=safe_dt(d.get("created_at")) or datetime.now(timezone.utc),
                is_deleted=bool(d.get("is_deleted", False)),
            )
            await doc.insert()
            inserted += 1
        print(f"    ✓ {inserted} user feedbacks inserted.")


async def migrate_payments(conn):
    print("\n[10/15] Migrating PAYMENTS …")
    if not sa_inspect(conn).has_table("payments"):
        print("    ⚠ Table 'payments' not found — skipping.")
        return
    rows = conn.execute(text("SELECT * FROM payments ORDER BY id")).fetchall()
    inserted = 0
    for r in rows:
        d = row_dict(r)
        client_id = resolve("clients", d.get("client_id"))
        gen_by = resolve("users", d.get("generated_by_id"))
        if not client_id or not gen_by:
            continue

        try:
            pstatus = PaymentStatus(d.get("status", "PENDING"))
        except ValueError:
            pstatus = PaymentStatus.PENDING

        doc = Payment(
            client_id=client_id,
            amount=float(d.get("amount") or 0),
            qr_code_data=d.get("qr_code_data"),
            status=pstatus,
            generated_by_id=gen_by,
            verified_by_id=resolve("users", d.get("verified_by_id")),
            created_at=safe_dt(d.get("created_at")) or datetime.now(timezone.utc),
            is_deleted=bool(d.get("is_deleted", False)),
            verified_at=safe_dt(d.get("verified_at")),
        )
        await doc.insert()
        inserted += 1
    print(f"    ✓ {inserted} payments inserted.")


async def migrate_bills(conn):
    print("\n[11/15] Migrating BILLS …")
    if not sa_inspect(conn).has_table("bills"):
        print("    ⚠ Table 'bills' not found — skipping.")
        return
    rows = conn.execute(text("SELECT * FROM bills ORDER BY id")).fetchall()
    inserted = 0
    for r in rows:
        d = row_dict(r)
        doc = Bill(
            shop_id=resolve("shops", d.get("shop_id")),
            client_id=resolve("clients", d.get("client_id")),
            invoice_client_name=d.get("invoice_client_name", "Unknown"),
            invoice_client_phone=d.get("invoice_client_phone", "0000000000"),
            invoice_client_email=d.get("invoice_client_email"),
            invoice_client_address=d.get("invoice_client_address"),
            invoice_client_org=d.get("invoice_client_org"),
            amount=float(d.get("amount") or 12000),
            payment_type=d.get("payment_type", "PERSONAL_ACCOUNT"),
            gst_type=d.get("gst_type", "WITH_GST"),
            invoice_series=d.get("invoice_series", "INV"),
            invoice_sequence=int(d.get("invoice_sequence") or 1),
            requires_qr=bool(d.get("requires_qr", True)),
            is_deleted=bool(d.get("is_deleted", False)),
            is_archived=bool(d.get("is_archived", False)),
            archived_by_id=resolve("users", d.get("archived_by_id")),
            invoice_status=d.get("invoice_status", "DRAFT"),
            status=d.get("status", "PENDING"),
            invoice_number=d.get("invoice_number"),
            whatsapp_sent=bool(d.get("whatsapp_sent", False)),
            created_by_id=resolve("users", d.get("created_by_id")),
            verified_by_id=resolve("users", d.get("verified_by_id")),
            verified_at=safe_dt(d.get("verified_at")),
            service_description=d.get("service_description"),
            billing_month=d.get("billing_month"),
            created_at=safe_dt(d.get("created_at")) or datetime.now(timezone.utc),
            updated_at=safe_dt(d.get("updated_at")) or datetime.now(timezone.utc),
        )
        await doc.insert()
        inserted += 1
    print(f"    ✓ {inserted} bills inserted.")


async def migrate_salary(conn):
    print("\n[12/15] Migrating SALARY (Leave Records + Slips) …")
    # Leave Records
    if sa_inspect(conn).has_table("leave_records"):
        rows = conn.execute(text("SELECT * FROM leave_records ORDER BY id")).fetchall()
        inserted = 0
        for r in rows:
            d = row_dict(r)
            user_id = resolve("users", d.get("user_id"))
            if not user_id:
                continue
            try:
                lstatus = LeaveStatus(d.get("status", "PENDING"))
            except ValueError:
                lstatus = LeaveStatus.PENDING
            doc = LeaveRecord(
                user_id=user_id,
                start_date=safe_date(d.get("start_date")),
                end_date=safe_date(d.get("end_date")),
                leave_type=d.get("leave_type", "CASUAL"),
                day_type=d.get("day_type", "FULL"),
                reason=d.get("reason"),
                status=lstatus,
                approved_by=resolve("users", d.get("approved_by")),
                remarks=d.get("remarks"),
                created_at=safe_dt(d.get("created_at")) or datetime.now(timezone.utc),
                updated_at=safe_dt(d.get("updated_at")) or datetime.now(timezone.utc),
                is_deleted=bool(d.get("is_deleted", False)),
            )
            await doc.insert()
            inserted += 1
        print(f"    ✓ {inserted} leave records inserted.")

    # Salary Slips
    if sa_inspect(conn).has_table("salary_slips"):
        rows = conn.execute(text("SELECT * FROM salary_slips ORDER BY id")).fetchall()
        inserted = 0
        for r in rows:
            d = row_dict(r)
            user_id = resolve("users", d.get("user_id"))
            if not user_id:
                continue
            doc = SalarySlip(
                user_id=user_id,
                month=d.get("month", ""),
                generated_at=safe_date(d.get("generated_at")) or datetime.now(timezone.utc).date(),
                base_salary=float(d.get("base_salary") or 0),
                paid_leaves=int(d.get("paid_leaves") or 0),
                unpaid_leaves=int(d.get("unpaid_leaves") or 0),
                deduction_amount=float(d.get("deduction_amount") or 0),
                incentive_amount=float(d.get("incentive_amount") or 0),
                slab_bonus=float(d.get("slab_bonus") or 0),
                total_earnings=float(d.get("total_earnings") or 0),
                final_salary=float(d.get("final_salary") or 0),
                status=d.get("status", "CONFIRMED"),
                confirmed_by=resolve("users", d.get("confirmed_by")),
                confirmed_at=safe_date(d.get("confirmed_at")),
                is_visible_to_employee=bool(d.get("is_visible_to_employee", False)),
                employee_remarks=d.get("employee_remarks"),
                manager_remarks=d.get("manager_remarks"),
                file_url=d.get("file_url"),
                is_deleted=bool(d.get("is_deleted", False)),
            )
            await doc.insert()
            inserted += 1
        print(f"    ✓ {inserted} salary slips inserted.")


async def migrate_incentives(conn):
    print("\n[13/15] Migrating INCENTIVES …")

    # Incentive Slabs
    if sa_inspect(conn).has_table("incentive_slabs"):
        rows = conn.execute(text("SELECT * FROM incentive_slabs ORDER BY id")).fetchall()
        inserted = 0
        for r in rows:
            d = row_dict(r)
            pg_id = d["id"]
            oid = new_oid("incentive_slabs", pg_id)
            doc = IncentiveSlab(
                id=PydanticObjectId(str(oid)),
                min_units=int(d.get("min_units") or 1),
                max_units=int(d.get("max_units") or 10),
                incentive_per_unit=float(d.get("incentive_per_unit") or 0),
                slab_bonus=float(d.get("slab_bonus") or 0),
            )
            await doc.insert()
            inserted += 1
        print(f"    ✓ {inserted} incentive slabs inserted.")

    # Employee Performances
    if sa_inspect(conn).has_table("employee_performances"):
        rows = conn.execute(text("SELECT * FROM employee_performances ORDER BY id")).fetchall()
        inserted = 0
        for r in rows:
            d = row_dict(r)
            user_id = resolve("users", d.get("user_id"))
            if not user_id:
                continue
            doc = EmployeePerformance(
                user_id=user_id,
                period=d.get("period", ""),
                closed_units=int(d.get("closed_units") or 0),
            )
            await doc.insert()
            inserted += 1
        print(f"    ✓ {inserted} employee performances inserted.")

    # Incentive Slips
    if sa_inspect(conn).has_table("incentive_slips"):
        rows = conn.execute(text("SELECT * FROM incentive_slips ORDER BY id")).fetchall()
        inserted = 0
        for r in rows:
            d = row_dict(r)
            user_id = resolve("users", d.get("user_id"))
            if not user_id:
                continue
            doc = IncentiveSlip(
                user_id=user_id,
                period=d.get("period", ""),
                target=int(d.get("target") or 0),
                achieved=int(d.get("achieved") or 0),
                percentage=float(d.get("percentage") or 0),
                applied_slab=d.get("applied_slab"),
                amount_per_unit=float(d.get("amount_per_unit") or 0),
                total_incentive=float(d.get("total_incentive") or 0),
                slab_bonus_amount=float(d.get("slab_bonus_amount") or 0),
                is_visible_to_employee=bool(d.get("is_visible_to_employee", False)),
                employee_remarks=d.get("employee_remarks"),
                manager_remarks=d.get("manager_remarks"),
                generated_at=safe_dt(d.get("generated_at")) or datetime.now(timezone.utc),
            )
            await doc.insert()
            inserted += 1
        print(f"    ✓ {inserted} incentive slips inserted.")


async def migrate_notifications(conn):
    print("\n[14/15] Migrating NOTIFICATIONS …")
    if not sa_inspect(conn).has_table("notifications"):
        print("    ⚠ Table 'notifications' not found — skipping.")
        return
    rows = conn.execute(text("SELECT * FROM notifications ORDER BY id")).fetchall()
    inserted = 0
    for r in rows:
        d = row_dict(r)
        user_id = resolve("users", d.get("user_id"))
        if not user_id:
            continue
        doc = Notification(
            user_id=user_id,
            title=d.get("title", ""),
            message=d.get("message", ""),
            is_read=bool(d.get("is_read", False)),
            is_deleted=bool(d.get("is_deleted", False)),
            created_at=safe_dt(d.get("created_at")) or datetime.now(timezone.utc),
        )
        await doc.insert()
        inserted += 1
    print(f"    ✓ {inserted} notifications inserted.")


async def migrate_app_settings(conn):
    print("\n[15/15] Migrating APP SETTINGS …")
    if not sa_inspect(conn).has_table("app_settings"):
        print("    ⚠ Table 'app_settings' not found — skipping.")
        return
    rows = conn.execute(text("SELECT * FROM app_settings")).fetchall()
    inserted = 0
    for r in rows:
        d = row_dict(r)
        doc = AppSetting(
            key=d.get("key", ""),
            value=d.get("value"),
        )
        await doc.insert()
        inserted += 1
    print(f"    ✓ {inserted} app settings inserted.")


# ════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════

async def main():
    print("=" * 60)
    print("  CRM AI SETU — PostgreSQL  →  MongoDB Atlas Migration")
    print("=" * 60)

    # ── Connect to MongoDB ────────────────────────────────────────
    print("\n[INIT] Connecting to MongoDB Atlas …")
    mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
    await init_beanie(
        database=mongo_client[MONGO_DB_NAME],
        document_models=ALL_DOCUMENT_MODELS,
    )
    print("       MongoDB connected ✓")

    # ── Connect to PostgreSQL ─────────────────────────────────────
    print("[INIT] Connecting to PostgreSQL …")
    pg_engine = make_pg_engine()
    print("       PostgreSQL connected ✓\n")

    with pg_engine.connect() as conn:
        inspector = sa_inspect(conn)
        pg_tables = inspector.get_table_names()
        print(f"[INFO] Found {len(pg_tables)} tables in Postgres: {', '.join(sorted(pg_tables))}\n")

        # Run migrations in dependency order
        await migrate_users(conn)
        await migrate_areas(conn)
        await migrate_shops(conn)
        await migrate_clients(conn)
        await migrate_projects(conn)
        await migrate_visits(conn)
        await migrate_issues(conn)
        await migrate_meetings(conn)
        await migrate_feedback(conn)
        await migrate_payments(conn)
        await migrate_bills(conn)
        await migrate_salary(conn)
        await migrate_incentives(conn)
        await migrate_notifications(conn)
        await migrate_app_settings(conn)

    print("\n" + "=" * 60)
    print("  Migration COMPLETE ✓")
    print(f"  ID mappings built for: {list(id_map.keys())}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
