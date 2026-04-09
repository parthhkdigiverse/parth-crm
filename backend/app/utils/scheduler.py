# backend/app/utils/scheduler.py
"""
scheduler.py — Background task runner using APScheduler (async-safe, Beanie version).

Uses AsyncIOScheduler so all Beanie queries run on the same event loop as uvicorn.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.enums import GlobalTaskStatus
from app.modules.meetings.models import MeetingSummary
from app.modules.notifications.models import Notification
from app.modules.users.models import User, UserRole
from app.modules.shops.models import Shop
from app.modules.clients.models import Client

# ── Use AsyncIOScheduler so jobs can safely run async Beanie queries ──────────
scheduler = AsyncIOScheduler(timezone="UTC")


async def check_upcoming_meetings():
    """
    Fired every 60 s.
    Finds SCHEDULED meetings whose date falls 14-16 minutes from now
    and creates a Notification for the assigned PM (or owner) if not already sent.
    """
    try:
        now = datetime.now(timezone.utc)
        window_start = now
        window_end   = now + timedelta(minutes=16)

        upcoming = await MeetingSummary.find(
            MeetingSummary.status == GlobalTaskStatus.OPEN,
            MeetingSummary.reminder_sent == False,
            MeetingSummary.date >= window_start,
            MeetingSummary.date <= window_end,
        ).to_list()

        admins = await User.find(User.role == UserRole.ADMIN).to_list()

        for meeting in upcoming:
            client = None
            if meeting.client_id:
                client = await Client.get(meeting.client_id)

            manager_name = "Unknown"
            if client and client.pm_id:
                pm_user = await User.get(client.pm_id)
                if pm_user:
                    manager_name = pm_user.name

            recipient_ids = set()
            if client:
                if client.pm_id:
                    recipient_ids.add(client.pm_id)
                if client.owner_id:
                    recipient_ids.add(client.owner_id)

            if not recipient_ids:
                print(f"[Scheduler] Meeting {meeting.id} has no PM/owner — skipping notification.")
                continue

            for recipient_id in recipient_ids:
                message_text = f"Heads up! Your session '{meeting.title}' with {client.name} starts in 15 minutes."
                if meeting.meet_link:
                    message_text += f"\nLINK:{meeting.meet_link}"

                notif = Notification(
                    user_id=recipient_id,
                    title="⏰ Upcoming Meeting",
                    message=message_text,
                    is_read=False,
                )
                await notif.insert()
                print(f"[Scheduler] Dispatched 15-min reminder for meeting {meeting.id} → user ID {recipient_id}")

            client_name = client.name if client else 'N/A'
            admin_msg_text = f"Session '{meeting.title}' with {client_name} (Manager: {manager_name}) starts in 15 minutes."
            if meeting.meet_link:
                admin_msg_text += f"\nLINK:{meeting.meet_link}"

            for admin in admins:
                if admin.id in recipient_ids:
                    continue
                
                admin_notif = Notification(
                    user_id=admin.id,
                    title=f"[Reminder] Upcoming Meeting: {meeting.title}",
                    message=admin_msg_text,
                    is_read=False,
                )
                await admin_notif.insert()

            meeting.reminder_sent = True
            await meeting.save()

    except Exception as exc:
        print(f"[Scheduler] Error in check_upcoming_meetings: {exc}")


async def close_finished_meetings():
    """
    Fired every 5 minutes.
    Finds SCHEDULED meetings that started more than 1 hour ago
    and forcefully marks them as COMPLETED. It also finds their corresponding 
    Notifications in the DB and taints the payload with STATUS:COMPLETED to break the frontend join link.
    """
    try:
        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)

        expired_meetings = await MeetingSummary.find(
            MeetingSummary.status == GlobalTaskStatus.OPEN,
            MeetingSummary.date <= one_hour_ago
        ).to_list()

        admins = await User.find(User.role == UserRole.ADMIN).to_list()

        for meeting in expired_meetings:
            meeting.status = GlobalTaskStatus.RESOLVED
            print(f"[Scheduler] Auto-completed expired meeting {meeting.id} ({meeting.title}).")

            if meeting.meet_link:
                notifs = await Notification.find(
                    {"message": {"$regex": f"LINK:{meeting.meet_link}"}}
                ).to_list()
                
                for notif in notifs:
                    if "STATUS:COMPLETED" not in notif.message:
                        notif.message += "\nSTATUS:COMPLETED"
                        await notif.save()
            
            client_name = "N/A"
            if meeting.client_id:
                client = await Client.get(meeting.client_id)
                if client:
                    client_name = client.name

            for admin in admins:
                notif = Notification(
                    user_id=admin.id,
                    title=f"[Alert] Missed Meeting: {meeting.title}",
                    message=f"The meeting '{meeting.title}' with {client_name} was missed (auto-closed after 1 hour)."
                )
                await notif.insert()

            await meeting.save()

    except Exception as exc:
        print(f"[Scheduler] Error in close_finished_meetings: {exc}")


async def check_missed_demos():
    """
    Fired every 10 minutes.
    Finds Shops with scheduled demos in the past (more than 1 hour ago)
    that haven't been completed or cancelled.
    """
    try:
        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)

        missed_demos = await Shop.find(
            Shop.demo_scheduled_at != None,
            Shop.demo_scheduled_at <= one_hour_ago,
            Shop.is_deleted == False
        ).to_list()

        if not missed_demos:
            return

        admins = await User.find(User.role == UserRole.ADMIN).to_list()
        
        for shop in missed_demos:
            pm_name = "Unassigned"
            if shop.project_manager_id:
                pm_user = await User.get(shop.project_manager_id)
                if pm_user:
                    pm_name = pm_user.name
            
            for admin in admins:
                notif = Notification(
                    user_id=admin.id,
                    title=f"[Alert] Missed Demo: {shop.name}",
                    message=f"The product demo for '{shop.name}' (Scheduled PM: {pm_name}) was missed."
                )
                await notif.insert()
            
            print(f"[Scheduler] Detected missed demo for {shop.name}. Notified admins.")
            shop.demo_scheduled_at = None
            shop.demo_notes = (shop.demo_notes or "") + "\n[System: Marked as Missed]"
            await shop.save()

    except Exception as exc:
        print(f"[Scheduler] Error in check_missed_demos: {exc}")


def start_scheduler():
    """Call this from main.py startup to begin background tasks."""
    scheduler.add_job(
        check_upcoming_meetings,
        trigger="interval",
        seconds=60,
        id="meeting_reminders",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        close_finished_meetings,
        trigger="interval",
        minutes=5,
        id="meeting_auto_closer",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        check_missed_demos,
        trigger="interval",
        minutes=10,
        id="demo_missed_checker",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    print("[Scheduler] APScheduler started — checking meetings every 60 s, closing old ones every 5 mins.")


def stop_scheduler():
    """Call this from main.py shutdown."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        print("[Scheduler] APScheduler stopped.")
