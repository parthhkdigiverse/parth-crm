# backend/app/modules/meetings/service.py
from typing import Optional, List, Any
from datetime import datetime, timedelta, UTC
from beanie import PydanticObjectId
from beanie.operators import In, Or, And
from fastapi import HTTPException, status, Request
from app.modules.meetings.models import MeetingSummary, MeetingType
from app.core.enums import GlobalTaskStatus
from app.modules.meetings.schemas import MeetingSummaryCreate, MeetingSummaryUpdateBase
from app.modules.activity_logs.models import ActionType, EntityType
from app.modules.users.models import User, UserRole
from app.utils.ai_summarizer import generate_ai_summary
from app.utils.notify_helpers import notify_client_stakeholders, create_notification

class MeetingService:
    def __init__(self):
        # No db session needed in Beanie!
        pass

    async def get_meeting(self, meeting_id: PydanticObjectId, current_user: Optional[User] = None) -> Optional[MeetingSummary]:
        meeting = await MeetingSummary.find_one(MeetingSummary.id == meeting_id, MeetingSummary.is_deleted == False)
        if not meeting:
            return None
            
        if current_user and current_user.role != UserRole.ADMIN:
            # 1. Primary Authorization: Host or Attendee
            is_authorized = (
                meeting.host_id == current_user.id or
                current_user.id in (meeting.attendee_ids or [])
            )
            
            # 2. Secondary Authorization: PM/Sales Scope for the Client
            if not is_authorized:
                if meeting.client_id:
                    from app.modules.clients.service import ClientService
                    try:
                        # ClientService handles PM/Sales ownership and mixed role access
                        client = await ClientService().get_client(meeting.client_id, current_user)
                        if client:
                            is_authorized = True
                    except HTTPException:
                        pass
                
                # 3. Tertiary Authorization: Project-specific PM access
                if not is_authorized and meeting.project_id:
                    from app.modules.projects.models import Project
                    project = await Project.get(meeting.project_id)
                    if project and project.pm_id == current_user.id:
                        is_authorized = True
            
            if not is_authorized:
                raise HTTPException(status_code=403, detail="Access denied to this meeting")
                
        return meeting

    async def get_meetings(self, current_user: User, skip: int = 0, limit: Optional[int] = None) -> List[MeetingSummary]:
        find_query = MeetingSummary.find(MeetingSummary.is_deleted == False)
        
        if current_user.role != UserRole.ADMIN:
            visibility_conditions = [
                {"host_id": current_user.id},
                {"attendee_ids": current_user.id}
            ]
            
            # Sub-query for clients this user manages/owns/demoed or billed
            from app.modules.clients.models import Client
            from app.modules.shops.models import Shop
            from app.modules.billing.models import Bill
            
            # 1. Invoice Bridge
            billed_phones = await Bill.get_pymongo_collection().distinct(
                "invoice_client_phone", {"created_by_id": current_user.id}
            )
            # 2. Demo PM Bridge
            demo_shop_client_ids = await Shop.get_pymongo_collection().distinct(
                "client_id", {"project_manager_id": current_user.id, "is_deleted": False}
            )
            
            # 3. Direct Shop access (meetings linked to shops/projects directly)
            demo_shop_ids = await Shop.get_pymongo_collection().distinct(
                "_id", {"project_manager_id": current_user.id, "is_deleted": False}
            )
            
            managed_client_ids = await Client.get_pymongo_collection().distinct("_id", {
                "$or": [
                    {"owner_id": current_user.id},
                    {"pm_id": current_user.id},
                    {"referred_by_id": current_user.id},
                    {"phone": {"$in": billed_phones}},
                    {"_id": {"$in": [PydanticObjectId(cid) for cid in demo_shop_client_ids if cid]}}
                ],
                "is_deleted": False
            })
            
            if managed_client_ids:
                visibility_conditions.append({"client_id": {"$in": [PydanticObjectId(cid) for cid in managed_client_ids if cid]}})
            
            if demo_shop_ids:
                visibility_conditions.append({"project_id": {"$in": [PydanticObjectId(sid) for sid in demo_shop_ids if sid]}})
                
            find_query = find_query.find(Or(*visibility_conditions))

        query = find_query.skip(skip)
        if limit is not None:
            query = query.limit(limit)
        return await query.to_list()

    async def create_meeting(self, meeting_in: MeetingSummaryCreate, client_id: Optional[PydanticObjectId], current_user: User, request: Request):
        """Creates a new meeting summary, handles attendee logic, and synchronizes with external apps like Meet and Todo."""
        from app.utils.google_meet import generate_google_meet_link
        
        meeting_dict = meeting_in.model_dump()
        client_id = client_id or meeting_dict.get("client_id")
        project_id = meeting_dict.get("project_id")
        
        meeting_dict["client_id"] = client_id
        meeting_dict["project_id"] = project_id
        
        # Resolve target audience to attendee ObjectIDs
        target_type = meeting_dict.pop("target_type", "CLIENT")
        target_role = meeting_dict.pop("target_role", None)
        input_attendee_ids = meeting_dict.pop("attendee_ids", []) or []
        
        attendee_ids = []
        if target_type == "ALL_STAFF":
            staff = await User.find(User.is_active == True, User.is_deleted == False).to_list()
            attendee_ids = [u.id for u in staff]
        elif target_type == "ROLE_BASED" and target_role:
            staff = await User.find(User.role == target_role, User.is_active == True, User.is_deleted == False).to_list()
            attendee_ids = [u.id for u in staff]
        else:
            # Map input strings to PydanticObjectIds
            attendee_ids = [PydanticObjectId(aid) for aid in input_attendee_ids if aid]

        # Use the embedded List[PydanticObjectId] structure for attendee management
        meeting_dict["attendee_ids"] = list(set(attendee_ids))

        # Generate Google Meet link if requested
        if meeting_dict.get("meeting_type") in [MeetingType.GOOGLE_MEET.value, MeetingType.VIRTUAL.value, MeetingType.GOOGLE_MEET, MeetingType.VIRTUAL]:
            meeting_date = meeting_dict.get("date") or datetime.now(UTC)
            try:
                res = generate_google_meet_link(
                    title=meeting_dict.get("title", "Meeting"),
                    start_time=meeting_date,
                    description=meeting_dict.get("content", "")
                )
                meeting_dict["meet_link"] = res.get("meet_link")
                meeting_dict["calendar_event_id"] = res.get("calendar_event_id")
            except Exception as e:
                print(f"[GoogleMeet] Generation failed (non-fatal): {e}")

        db_meeting = MeetingSummary(**meeting_dict)
        if not db_meeting.host_id:
            db_meeting.host_id = current_user.id
        await db_meeting.insert()

        # -- Synchronization: Create linked Todo --
        from app.modules.todos.models import Todo
        host_id = db_meeting.host_id or current_user.id
        host_user = await User.get(host_id)
        
        db_todo = Todo(
            user_id=host_id,
            title=f"Meeting: {db_meeting.title}",
            description=db_meeting.content,
            due_date=db_meeting.date,
            start_time=db_meeting.start_time or (db_meeting.date.strftime("%H:%M:%S") if db_meeting.date else None),
            end_time=db_meeting.end_time or ((db_meeting.date + timedelta(minutes=30)).strftime("%H:%M:%S") if db_meeting.date else None),
            priority=db_meeting.priority,
            assigned_to=host_user.name if host_user else (current_user.name or current_user.email),
            related_entity=f"MEETING:{str(db_meeting.id)}",
            client_id=client_id,
            project_id=project_id
        )
        await db_todo.insert()
        db_meeting.todo_id = db_todo.id
        await db_meeting.save()

        # -- In-App Notifications --
        try:
            # Notify host if they are NOT the creator
            if db_meeting.host_id and db_meeting.host_id != current_user.id:
                notif_msg = f"A meeting has been scheduled with you as the host: '{db_meeting.title}'"
                if db_meeting.meet_link:
                    notif_msg += f"\nJOIN_MEET:{db_meeting.meet_link}"
                await create_notification(db_meeting.host_id, "Meeting Assignment", notif_msg, actor_id=current_user.id)

            # Notify attendees via sequential loop
            for aid in db_meeting.attendee_ids:
                if aid != current_user.id and aid != db_meeting.host_id: # Don't re-notify host if they are an attendee
                    notif_msg = f"You are invited to a meeting: '{db_meeting.title}'"
                    if db_meeting.meet_link:
                        notif_msg += f"\nJOIN_MEET:{db_meeting.meet_link}"
                    await create_notification(aid, "Meeting Invitation", notif_msg, actor_id=current_user.id)
            
            if client_id:
                from app.modules.clients.models import Client
                client = await Client.get(client_id)
                if client:
                    meeting_time = db_meeting.date.strftime("%I:%M %p, %d %b %Y") if db_meeting.date else "TBD"
                    await notify_client_stakeholders(client, "📅 Meeting Scheduled", f"Meeting '{db_meeting.title}' with {client.name} scheduled for {meeting_time}.", actor_id=current_user.id)
            elif project_id:
                from app.modules.projects.models import Project
                project = await Project.get(project_id)
                if project:
                    from app.modules.clients.models import Client
                    client = await Client.get(project.client_id)
                    meeting_time = db_meeting.date.strftime("%I:%M %p, %d %b %Y") if db_meeting.date else "TBD"
                    # If project has a client, notify stakeholders; otherwise just log/internal notif
                    if client:
                        await notify_client_stakeholders(client, "📅 Project Meeting Scheduled", f"Meeting '{db_meeting.title}' for project '{project.name}' scheduled for {meeting_time}.", actor_id=current_user.id)
        except Exception as e: 
            print(f"Notification error: {e}")

        return db_meeting

    async def update_meeting(self, meeting_id: PydanticObjectId, update_in: MeetingSummaryUpdateBase, current_user: User, request: Request):
        db_meeting = await self.get_meeting(meeting_id, current_user=current_user)
        if not db_meeting: 
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

        update_dict = update_in.model_dump(exclude_unset=True)
        for k, v in update_dict.items(): 
            setattr(db_meeting, k, v)
        await db_meeting.save()

        # -- Synchronization: Update linked Todo --
        if db_meeting.todo_id:
            from app.modules.todos.models import Todo, TodoStatus
            todo = await Todo.get(db_meeting.todo_id)
            if todo:
                if "title" in update_dict:
                    todo.title = f"Meeting: {db_meeting.title}"
                if "status" in update_dict:
                    if update_dict["status"] == GlobalTaskStatus.RESOLVED:
                        todo.status = TodoStatus.COMPLETED
                await todo.save()
        
        # -- Synchronization: Update notification link status --
        if update_dict.get("status") in [GlobalTaskStatus.RESOLVED, GlobalTaskStatus.CANCELLED]:
            if db_meeting.meet_link:
                try:
                    from app.modules.notifications.models import Notification
                    import re
                    notifs = await Notification.find({"message": re.compile(f"LINK:{db_meeting.meet_link}")}).to_list()
                    for notif in notifs:
                        if "STATUS:COMPLETED" not in notif.message:
                            notif.message += "\nSTATUS:COMPLETED"
                            await notif.save()
                except Exception as e:
                    print(f"[MeetingService] Notif sync error: {e}")
        
        return db_meeting

    async def import_meeting_summary(self, meeting_id: PydanticObjectId, current_user: User):
        """Fetches Google Meet transcript via AI summarizer utility and updates MeetingSummary state."""
        db_meeting = await self.get_meeting(meeting_id, current_user=current_user)
        if not db_meeting: 
            raise HTTPException(status_code=404, detail="Meeting not found")
        
        from app.utils.google_meet import fetch_transcript_from_drive
        transcript_text = None
        if db_meeting.calendar_event_id:
            transcript_text = fetch_transcript_from_drive(db_meeting.calendar_event_id)

        if not transcript_text:
            transcript_text = db_meeting.content or "No transcript or notes available."
        
        db_meeting.transcript = transcript_text
        ai_result = await generate_ai_summary(str(meeting_id), transcript_text)
        db_meeting.ai_summary = ai_result
        db_meeting.status = GlobalTaskStatus.RESOLVED
        await db_meeting.save()
        return db_meeting

    async def reschedule_meeting(self, meeting_id: PydanticObjectId, new_date: datetime, current_user: User, request: Request, start_time: Optional[str] = None, end_time: Optional[str] = None):
        """Reschedules a meeting, updates linked calendar events and notifies stakeholders."""
        db_meeting = await self.get_meeting(meeting_id)
        if not db_meeting: 
             raise HTTPException(status_code=404, detail="Meeting not found")

        db_meeting.date = new_date
        if start_time: db_meeting.start_time = start_time
        if end_time: db_meeting.end_time = end_time
        
        db_meeting.cancellation_reason = None
        db_meeting.reminder_sent = False
        await db_meeting.save()

        # Update linked Todo
        if db_meeting.todo_id:
            from app.modules.todos.models import Todo
            update_fields = {"due_date": new_date}
            if start_time: update_fields["start_time"] = start_time
            if end_time: update_fields["end_time"] = end_time
            await Todo.find(Todo.id == db_meeting.todo_id).update({"$set": update_fields})

        # Google Calendar Sync
        if db_meeting.calendar_event_id:
            try:
                from app.utils.google_meet import reschedule_google_calendar_event
                reschedule_google_calendar_event(db_meeting.calendar_event_id, new_date)
            except Exception as e:
                print(f"[GoogleCalendar] Reschedule failed: {e}")

        # Notification
        try:
            from app.modules.clients.models import Client
            client = await Client.get(db_meeting.client_id)
            if client:
                await notify_client_stakeholders(client, "🔁 Meeting Rescheduled", f"Meeting '{db_meeting.title}' rescheduled to {new_date.strftime('%d %b, %I:%M %p')}.", actor_id=current_user.id)
        except Exception as e: print(f"Reschedule notif error: {e}")

        return db_meeting

    async def cancel_meeting(self, meeting_id: PydanticObjectId, reason: Optional[str], current_user: User, request: Request):
        db_meeting = await self.get_meeting(meeting_id, current_user=current_user)
        if not db_meeting: 
            raise HTTPException(status_code=404, detail="Meeting not found")

        if db_meeting.status == GlobalTaskStatus.RESOLVED:
            raise HTTPException(status_code=400, detail="Cannot cancel a completed meeting.")

        db_meeting.status = GlobalTaskStatus.CANCELLED
        db_meeting.cancellation_reason = reason
        await db_meeting.save()

        try:
            from app.utils.notify_helpers import notify_client_stakeholders
            from app.modules.clients.models import Client
            client = await Client.get(db_meeting.client_id) if db_meeting.client_id else None
            if client:
                reason_suffix = f" Reason: {reason}" if reason else ""
                await notify_client_stakeholders(
                    client,
                    "❌ Meeting Cancelled",
                    f"Meeting '{db_meeting.title}' with {client.name} has been cancelled.{reason_suffix}",
                    actor_id=current_user.id,
                )
        except Exception as e:
            print(f"[MeetingService] Cancel notif error: {e}")

        return db_meeting

    async def initialize_google_meet(self, meeting_id: PydanticObjectId, current_user: User):
        """Generate and persist a Google Meet link for an existing meeting."""
        db_meeting = await self.get_meeting(meeting_id, current_user=current_user)
        if not db_meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")

        from app.utils.google_meet import generate_google_meet_link

        meeting_date = db_meeting.date or datetime.now(UTC)
        try:
            result = generate_google_meet_link(
                title=db_meeting.title,
                start_time=meeting_date,
                description=db_meeting.content or ""
            )
            db_meeting.meet_link = result.get("meet_link")
            db_meeting.calendar_event_id = result.get("calendar_event_id")
            await db_meeting.save()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Google Meet generation failed: {e}")

        return db_meeting

    async def get_ai_analysis(self, meeting_id: PydanticObjectId, current_user: User):
        """
        Returns the stored ai_summary if available (cached), otherwise
        generates one from the transcript or manual notes via Gemini.
        Mirrors the old SQL service logic.
        """
        db_meeting = await self.get_meeting(meeting_id, current_user=current_user)
        if not db_meeting:
            return {"error": "Meeting not found"}

        # Return cached result to avoid repeated Gemini calls
        if db_meeting.ai_summary:
            return db_meeting.ai_summary

        # Prefer stored transcript, fall back to manual notes
        source_text = db_meeting.transcript or db_meeting.content or "No notes provided."

        try:
            analysis = await generate_ai_summary(str(meeting_id), source_text)
            # Cache in DB
            db_meeting.ai_summary = analysis
            await db_meeting.save()
            return analysis
        except Exception as e:
            print(f"[MeetingService] AI Error: {e}")
            return {
                "highlights": ["Error processing AI analysis"],
                "next_steps": "Please check your API key and connection."
            }
