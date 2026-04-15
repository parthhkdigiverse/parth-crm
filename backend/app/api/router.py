# backend/app/api/router.py
from fastapi import APIRouter

# Module Imports
from app.modules.auth import router as auth
from app.modules.issues import router as issues
from app.modules.issues.router import global_router as issues_global_router
from app.modules.meetings import router as meetings
from app.modules.feedback import router as feedback
from app.modules.salary import router as salary
from app.modules.incentives import router as incentives
from app.modules.activity_logs import router as activity_logs
from app.modules.users import router as users
from app.modules.clients import router as clients
from app.modules.areas import router as areas
from app.modules.visits import router as visits
from app.modules.shops import router as shops
from app.modules.reports import router as reports
from app.modules.payments import router as payments
from app.modules.projects import router as projects
from app.modules.todos import router as todos
from app.modules.notifications import router as notifications
from app.modules.billing import router as billing
from app.modules.timetable import router as timetable
from app.modules.search import router as search
from app.modules.idcards import router as idcards
from app.modules.employees import router as employees
from app.modules.settings import router as settings
from app.modules.attendance import router as attendance


api_router = APIRouter()

# Settings
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])

# Auth & Users
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(employees.router, prefix="/employees", tags=["employees"])

# Clients & Related (Issues, Meetings, Feedback)
api_router.include_router(clients.router, prefix="/clients", tags=["clients"])
api_router.include_router(issues.router, prefix="/clients", tags=["issues"])
api_router.include_router(issues_global_router, prefix="/issues", tags=["issues"])
api_router.include_router(meetings.router, prefix="/clients", tags=["meetings"])
api_router.include_router(meetings.global_router, prefix="/meetings", tags=["meetings"])
api_router.include_router(feedback.router, prefix="/feedback", tags=["feedback"])

# Field Operations
api_router.include_router(areas.router, prefix="/areas", tags=["areas"])
api_router.include_router(visits.router, prefix="/visits", tags=["visits"])
api_router.include_router(shops.router, prefix="/shops", tags=["shops"])

# HR & Payroll
api_router.include_router(salary.router, prefix="/hrm", tags=["salary_leave"])
api_router.include_router(incentives.router, prefix="/incentives", tags=["incentives"])
api_router.include_router(attendance.router, prefix="/attendance", tags=["attendance"])

# Project Management & Tools
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(todos.router, prefix="/todos", tags=["todos"])
api_router.include_router(timetable.router, prefix="/timetable", tags=["timetable"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])

# Analytics & Logs
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(activity_logs.router, prefix="/activity-logs", tags=["activity_logs"])

# Finance & Billing
api_router.include_router(payments.router, tags=["payments"])
api_router.include_router(billing.router, prefix="/billing", tags=["billing"])

# Utilities
api_router.include_router(search, prefix="/search", tags=["search"])
api_router.include_router(idcards.router, prefix="/idcards", tags=["idcards"])


@api_router.get("/system/ip")
def get_system_ip():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return {"ip": ip}
    except Exception:
        return {"ip": "127.0.0.1"}

@api_router.get("/")
async def health_check():
    return {"status": "ok"}

@api_router.get("/health")
def health_check():
    return {"status": "ok"}
