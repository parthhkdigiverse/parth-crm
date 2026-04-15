import asyncio
# backend/verify_attendance_logic.py
import sys
import os
from datetime import datetime, timedelta, timezone

# Add parent directory to path to import app modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from app.modules.users.models import User, UserRole
from app.modules.attendance.models import Attendance
from app.modules.salary.models import LeaveRecord
from app.modules.attendance.service import AttendanceService

async def verify():
    print("Initializing Database...")
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client.get_default_database()
    await init_beanie(database=db, document_models=[User, Attendance, LeaveRecord])
    
    today = AttendanceService.get_ist_today()
    print(f"IST Today: {today}")
    
    # Test for all users
    print("Fetching attendance summary for all users (today)...")
    try:
        summary = await AttendanceService.get_attendance_summary(
            target_user=None,
            start_date=today,
            end_date=today,
            reconcile=False,
            current_user=None # Not used for logic, only for permissions in router
        )
        
        print(f"Total Hours today (all users): {summary['total_hours']}")
        print(f"Records found: {len(summary['records'])}")
        
        for rec in summary['records']:
            status = rec['day_status']
            user_name = rec['user_name']
            punched_in = rec['is_punched_in']
            hours = rec['total_hours']
            print(f" - {user_name}: {status} (Punched In: {punched_in}, Hours: {hours:.2f})")
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(verify())
