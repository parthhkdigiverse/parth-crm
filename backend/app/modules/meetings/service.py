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

    async def get_meeting(self, meeting_id: PydanticObjectId) -> Optional[MeetingSummary]:
        return await MeetingSummary.find_one(MeetingSummary.id == meeting_id, MeetingSummary.is_deleted == False)

    async def get_meetings(self, skip: int = 0, limit: Optional[int] = None) -> List[MeetingSummary]:
        query = MeetingSummary.find(MeetingSummary.is_deleted == False).skip(skip)
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
            start_time=db_meeting.date.strftime("%H:%M:%S") if db_meeting.date else None,
            end_time=(db_meeting.date + timedelta(minutes=30)).strftime("%H:%M:%S") if db_meeting.date else None,
            priority=db_meeting.priority,
            assigned_to=host_user.name if host_user else (current_user.name or current_user.email),
            related_entity=f"MEETING:{str(db_meeting.id)}",
            client_id=client_id,
            project_id=project_id
        )
        await db_todo.insert()
        db_meeting.todo_id = db_todo.id
        await db_meeting.save()

        # -- Synchronization: Create linked TimetableEvent --
        from app.modules.timetable.models import TimetableEvent
        try:
            await TimetableEvent(
                user_id=host_id,
                title=db_meeting.title,
                assignee_name=host_user.name if host_user else "Staff",
                date=db_meeting.date.date() if db_meeting.date else datetime.now(UTC).date(),
                start_time=db_meeting.date.strftime("%H:%M:%S") if db_meeting.date else None,
                end_time=(db_meeting.date + timedelta(hours=1)).strftime("%H:%M:%S") if db_meeting.date else None,
                location=str(db_meeting.meeting_type),
                priority=db_meeting.priority
            ).insert()
        except Exception as tt_err:
             print(f"[TimetableSync] Failed: {tt_err}")

        # -- In-App Notifications --
        try:
            # Notify attendees via sequential loop
            for aid in db_meeting.attendee_ids:
                if aid != current_user.id:
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
        db_meeting = await self.get_meeting(meeting_id)
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
                    if update_dict["status"] in [GlobalTaskStatus.RESOLVED, GlobalTaskStatus.DONE]:
                        todo.status = TodoStatus.COMPLETED
                await todo.save()
        
        return db_meeting

    async def import_meeting_summary(self, meeting_id: PydanticObjectId):
        """Fetches Google Meet transcript via AI summarizer utility and updates MeetingSummary state."""
        db_meeting = await self.get_meeting(meeting_id)
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

    async def reschedule_meeting(self, meeting_id: PydanticObjectId, new_date: datetime, current_user: User, request: Request):
        """Reschedules a meeting, updates linked calendar events and notifies stakeholders."""
        db_meeting = await self.get_meeting(meeting_id)
        if not db_meeting: 
             raise HTTPException(status_code=404, detail="Meeting not found")

        db_meeting.date = new_date
        db_meeting.status = GlobalTaskStatus.IN_PROGRESS
        db_meeting.cancellation_reason = None
        db_meeting.reminder_sent = False
        await db_meeting.save()

        # Update linked Todo
        if db_meeting.todo_id:
            from app.modules.todos.models import Todo
            await Todo.find(Todo.id == db_meeting.todo_id).update({"$set": {"due_date": new_date}})

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

    async def initialize_google_meet(self, meeting_id: PydanticObjectId):
        """Generate and persist a Google Meet link for an existing meeting."""
        db_meeting = await self.get_meeting(meeting_id)
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

    async def get_ai_analysis(self, meeting_id: PydanticObjectId):
        """
        Returns the stored ai_summary if available (cached), otherwise
        generates one from the transcript or manual notes via Gemini.
        Mirrors the old SQL service logic.
        """
        db_meeting = await self.get_meeting(meeting_id)
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
