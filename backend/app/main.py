# backend/app/main.py
import sys
import os
import traceback
import motor.motor_asyncio
import dns.resolver
from contextlib import asynccontextmanager

# ── Fix for dnspython/pymongo in restricted environments ───────────────────
# If /etc/resolv.conf is inaccessible, dnspython fails. We manually configure a fallback.
try:
    dns.resolver.default_resolver = dns.resolver.Resolver(configure=True)
except Exception:
    dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
    dns.resolver.default_resolver.nameservers = ['8.8.8.8', '8.8.4.4', '1.1.1.1']
# ─────────────────────────────────────────────────────────────────────────────

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse, Response
from beanie import init_beanie

# Core Imports
from app.api.router import api_router
from app.core.config import settings
from app.utils.scheduler import start_scheduler, stop_scheduler

# Beanie Model Imports
from app.modules.users.models import User
from app.modules.areas.models import Area
from app.modules.shops.models import Shop
from app.modules.clients.models import Client
from app.modules.projects.models import Project
from app.modules.visits.models import Visit
from app.modules.issues.models import Issue
from app.modules.meetings.models import MeetingSummary
from app.modules.feedback.models import Feedback, UserFeedback
from app.modules.payments.models import Payment
from app.modules.billing.models import Bill
from app.modules.salary.models import LeaveRecord, SalarySlip
from app.modules.incentives.models import IncentiveSlab, EmployeePerformance, IncentiveSlip
from app.modules.notifications.models import Notification
from app.modules.settings.models import SystemSettings, AppSetting
from app.modules.todos.models import Todo
from app.modules.timetable.models import TimetableEvent
from app.modules.attendance.models import Attendance
from app.modules.activity_logs.models import ActivityLog

DOCUMENT_MODELS = [
    User, Area, Shop, Client, Project,
    Visit, Issue, MeetingSummary,
    Feedback, UserFeedback,
    Payment, Bill,
    LeaveRecord, SalarySlip, AppSetting,
    IncentiveSlab, EmployeePerformance, IncentiveSlip,
    Notification, SystemSettings,
    Todo, TimetableEvent, Attendance, ActivityLog,
]

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup & shutdown hooks."""
    # ── Startup ──────────────────────────────────────────────────
    try:
        print(f"[Lifespan] Connecting to MongoDB (DB: aisetu_db)...")
        print(f"[Lifespan] URI: {settings.MONGODB_URI}")
        mongo_client = motor.motor_asyncio.AsyncIOMotorClient(settings.MONGODB_URI)
        mongo_client.append_metadata = lambda *args, **kwargs: None
        db_name = "aisetu_db"
        
        await init_beanie(
            database=mongo_client[db_name],
            document_models=DOCUMENT_MODELS,
        )
        print("[Lifespan] Database initialized successfully.")
        
        print("[Lifespan] Starting scheduler...")
        start_scheduler()
        print("[Lifespan] Scheduler started successfully.")
    except Exception as startup_error:
        print(f"[Lifespan] STARTUP ERROR: {startup_error}")
        traceback.print_exc()
        raise startup_error
    
    yield
    
    # ── Shutdown ─────────────────────────────────────────────────
    try:
        print("[Lifespan] Stopping scheduler...")
        stop_scheduler()
        print("[Lifespan] Scheduler stopped successfully.")
    except Exception as shutdown_error:
        print(f"[Lifespan] SHUTDOWN ERROR: {shutdown_error}")
        traceback.print_exc()


app = FastAPI(title="SRM AI SETU API", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # Set to False to allow "*" in allow_origins with JWT headers
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Exception Handler
@app.middleware("http")
async def catch_exceptions_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal Server Error", "error": str(e)}
        )

# Static Files
app_path = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(app_path))
frontend_path = os.path.join(project_root, "frontend")

if os.path.exists(frontend_path):
    app.mount("/frontend", StaticFiles(directory=frontend_path), name="frontend")
else:
    print(f"WARNING: Static frontend path not found at {frontend_path}")

# Uploads / Static Assets
backend_path = os.path.join(project_root, "backend")
static_path = os.path.join(backend_path, "static")
os.makedirs(static_path, exist_ok=True)  # ensure it exists on first boot
app.mount("/backend_static", StaticFiles(directory=static_path), name="backend_static")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    favicon_path = os.path.join(frontend_path, "favicon.ico")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path)
    return Response(status_code=204)



app.include_router(api_router, prefix="/api")

@app.get("/api/config")
async def get_config(request: Request):
    # Final calculated API Base URL for internal/fallback use.
    # If empty, the frontend (api.js) will use window.location.origin.
    if settings.API_BASE_URL:
        API_BASE_URL = settings.API_BASE_URL
    else:
        API_BASE_URL = "" # Let frontend decide
        
    return {
        "API_BASE_URL": API_BASE_URL
    }

# This must remain at the bottom of the file, below all app.include_router() calls!
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static_assets")

# html=True tells FastAPI to automatically serve index.html on '/' and match other .html files.
template_path = os.path.join(frontend_path, "template")
if os.path.exists(template_path):
    app.mount("/", StaticFiles(directory=template_path, html=True), name="frontend_templates")
else:
    print(f"WARNING: Frontend templates path not found at {template_path}")
