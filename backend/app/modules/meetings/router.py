# backend/app/modules/meetings/router.py
from datetime import date as dt_date, datetime, time, timedelta, timezone
from typing import List, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from beanie import PydanticObjectId
from beanie.operators import In
from app.core.dependencies import RoleChecker, get_current_user
from app.modules.users.models import User, UserRole
from app.modules.clients.models import Client
from app.modules.meetings.models import MeetingSummary
from app.modules.meetings.service import MeetingService
from app.modules.meetings.schemas import (
    MeetingSummaryCreate, MeetingSummaryRead, MeetingSummaryUpdate,
    MeetingCancel, MeetingReschedule
)
from app.core.enums import GlobalTaskStatus

router = APIRouter()
global_router = APIRouter()

# Role definitions
admin_checker = RoleChecker([UserRole.ADMIN])
staff_checker = RoleChecker([
    UserRole.ADMIN,
    UserRole.SALES,
    UserRole.TELESALES,
    UserRole.PROJECT_MANAGER,
    UserRole.PROJECT_MANAGER_AND_SALES
])
pm_checker = RoleChecker([
    UserRole.ADMIN,
    UserRole.PROJECT_MANAGER,
    UserRole.PROJECT_MANAGER_AND_SALES
])

PM_SCOPED_ROLES = {UserRole.PROJECT_MANAGER, UserRole.PROJECT_MANAGER_AND_SALES}


# ─── GLOBAL ENDPOINTS (/meetings/) ─────────────────────────────────────────

@global_router.get("/", response_model=List[MeetingSummaryRead])
async def read_all_meetings(
    skip: int = 0,
    limit: Optional[int] = None,
    client_id: Optional[str] = None,
    meeting_type: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[dt_date] = None,
    end_date: Optional[dt_date] = None,
    current_user: User = Depends(staff_checker)
) -> Any:
    """Get all meetings based on visibility permissions."""
    find_query = {}

    visibility_conditions = []
    
    if current_user.role != UserRole.ADMIN:
        # Fallbacks: you can see it if you host it, or you're an attendee
        visibility_conditions.append({"host_id": current_user.id})
        visibility_conditions.append({"attendee_ids": current_user.id})
        
        # If user is a PM, they also see all meetings for their clients
        if current_user.role in PM_SCOPED_ROLES:
            clients = await Client.find(Client.pm_id == current_user.id).to_list()
            assigned_client_ids = [c.id for c in clients]
            if assigned_client_ids:
                visibility_conditions.append({"client_id": {"$in": assigned_client_ids}})
                
        # If user is Sales, they see all meetings for clients they own
        if current_user.role in [UserRole.SALES, UserRole.TELESALES]:
            clients = await Client.find(Client.owner_id == current_user.id).to_list()
            owned_client_ids = [c.id for c in clients]
            if owned_client_ids:
                visibility_conditions.append({"client_id": {"$in": owned_client_ids}})
                
        if visibility_conditions:
            find_query["$or"] = visibility_conditions

    if client_id and client_id not in {"ALL", "all"}:
        try:
            find_query["client_id"] = PydanticObjectId(client_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid client_id format")
            
    if meeting_type and meeting_type not in {"ALL", "all"}:
        find_query["meeting_type"] = meeting_type
    if status and status not in {"ALL", "all"}:
        find_query["status"] = status

    date_filter = {}
    if start_date:
        date_filter["$gte"] = datetime.combine(start_date, time.min).replace(tzinfo=timezone.utc)
    if end_date:
        date_filter["$lt"] = datetime.combine(end_date + timedelta(days=1), time.min).replace(tzinfo=timezone.utc)

    if date_filter:
        find_query["date"] = date_filter

    query = MeetingSummary.find(find_query).sort("-date").skip(skip)
    if limit is not None:
        query = query.limit(limit)
    return await query.to_list()


@global_router.post("/", response_model=MeetingSummaryRead)
async def create_meeting_global(
    meeting_in: MeetingSummaryCreate,
    request: Request,
    current_user: User = Depends(staff_checker)
) -> Any:
    service = MeetingService()
    if meeting_in.client_id:
        client = await Client.get(meeting_in.client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        if current_user.role in PM_SCOPED_ROLES and client.pm_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied to this client")

    return await service.create_meeting(meeting_in, meeting_in.client_id, current_user, request)


@global_router.patch("/{meeting_id}", response_model=MeetingSummaryRead)
async def update_meeting_global(
    meeting_id: PydanticObjectId,
    meeting_in: MeetingSummaryUpdate,
    current_user: User = Depends(staff_checker)
) -> Any:
    service = MeetingService()
    return await service.update_meeting(meeting_id, meeting_in, current_user, None)



@global_router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meeting_global(
    meeting_id: PydanticObjectId,
    current_user: User = Depends(staff_checker)
):
    meeting = await MeetingSummary.get(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Admins can delete anything; others only their own or their PM-assigned clients
    if current_user.role != UserRole.ADMIN:
        if meeting.client_id:
            client = await Client.get(meeting.client_id)
            if client and current_user.role in PM_SCOPED_ROLES and client.pm_id != current_user.id:
                raise HTTPException(status_code=403, detail="Access denied")

    await meeting.delete()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@global_router.post("/batch-delete")
async def batch_delete_meetings(
    payload: dict,
    current_user: User = Depends(staff_checker)
):
    ids = [PydanticObjectId(i) for i in payload.get("ids", []) if i]
    if not ids:
        return {"message": "No IDs provided"}

    # Fetch meetings to check permissions
    meetings = await MeetingSummary.find(In(MeetingSummary.id, ids)).to_list()
    if not meetings:
        return {"message": "No meetings found"}

    ids_to_delete = []
    
    for meeting in meetings:
        can_delete = False
        if current_user.role == UserRole.ADMIN:
            can_delete = True
        else:
            # Check if host
            if meeting.host_id == current_user.id:
                can_delete = True
            # Check if PM of the client
            elif meeting.client_id:
                client = await Client.get(meeting.client_id)
                if client and current_user.role in PM_SCOPED_ROLES and client.pm_id == current_user.id:
                    can_delete = True
        
        if can_delete:
            ids_to_delete.append(meeting.id)

    if not ids_to_delete:
        raise HTTPException(status_code=403, detail="Access denied to all selected meetings")

    res = await MeetingSummary.find(In(MeetingSummary.id, ids_to_delete)).delete()
    return {"message": f"Successfully deleted {res.deleted_count} meetings"}


@global_router.post("/{meeting_id}/reschedule", response_model=MeetingSummaryRead)
async def reschedule_meeting(
    meeting_id: PydanticObjectId,
    reschedule_in: MeetingReschedule,
    request: Request,
    current_user: User = Depends(staff_checker)
) -> Any:
    return await MeetingService().reschedule_meeting(
        meeting_id=meeting_id,
        new_date=reschedule_in.new_date,
        current_user=current_user,
        request=request,
        start_time=reschedule_in.start_time,
        end_time=reschedule_in.end_time
    )


@global_router.post("/{meeting_id}/generate-ai-summary")
async def trigger_ai_summary(
    meeting_id: PydanticObjectId,
    current_user: User = Depends(staff_checker)
) -> Any:
    return await MeetingService().get_ai_analysis(meeting_id, current_user=current_user)


@global_router.post("/{meeting_id}/import-summary", response_model=MeetingSummaryRead)
async def import_meeting_summary(
    meeting_id: PydanticObjectId,
    current_user: User = Depends(pm_checker)
) -> Any:
    return await MeetingService().import_meeting_summary(meeting_id, current_user=current_user)


@global_router.post("/{meeting_id}/initialize-meet", response_model=MeetingSummaryRead)
async def init_meeting_link(
    meeting_id: PydanticObjectId,
    current_user: User = Depends(pm_checker)
) -> Any:
    return await MeetingService().initialize_google_meet(meeting_id, current_user=current_user)


@global_router.post("/{meeting_id}/cancel", response_model=MeetingSummaryRead)
async def cancel_meeting_global(
    meeting_id: PydanticObjectId,
    cancel_in: MeetingCancel,
    current_user: User = Depends(pm_checker)
) -> Any:
    return await MeetingService().cancel_meeting(meeting_id, cancel_in.reason, current_user, request)



# ─── CLIENT-SCOPED ENDPOINTS (/clients/{client_id}/meetings) ───────────────

@router.post("/{client_id}/meetings", response_model=MeetingSummaryRead)
async def create_meeting(
    client_id: PydanticObjectId,
    meeting_in: MeetingSummaryCreate,
    request: Request,
    current_user: User = Depends(staff_checker)
) -> Any:
    client = await Client.get(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    if current_user.role in PM_SCOPED_ROLES and client.pm_id != current_user.id:
        from app.modules.shops.models import Shop
        manages_shop = await Shop.find_one(Shop.client_id == client_id, Shop.project_manager_id == current_user.id)
        if not manages_shop:
            raise HTTPException(status_code=403, detail="Access denied to this client")

    service = MeetingService()
    return await service.create_meeting(meeting_in, client_id, current_user, request)


@router.get("/{client_id}/meetings", response_model=List[MeetingSummaryRead])
async def read_client_meetings(
    client_id: PydanticObjectId,
    current_user: User = Depends(staff_checker)
) -> Any:
    client = await Client.get(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Scope check: admins see all; staff limited to PM assignment or Client ownership
    if current_user.role != UserRole.ADMIN:
        is_owner = client.owner_id == current_user.id or client.referred_by_id == current_user.id
        is_pm = client.pm_id == current_user.id
        
        if not is_owner and not is_pm:
            from app.modules.shops.models import Shop
            manages_shop = await Shop.find_one(Shop.client_id == client_id, Shop.project_manager_id == current_user.id)
            if not manages_shop:
                raise HTTPException(status_code=403, detail="Access denied to this client's meetings")

    return await MeetingSummary.find(MeetingSummary.client_id == client_id, MeetingSummary.is_deleted == False).to_list()


@router.post("/{client_id}/meetings/{meeting_id}/cancel", response_model=MeetingSummaryRead)
async def cancel_meeting(
    client_id: PydanticObjectId,
    meeting_id: PydanticObjectId,
    cancel_in: MeetingCancel,
    current_user: User = Depends(pm_checker)
) -> Any:
    meeting = await MeetingSummary.get(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    client = await Client.get(client_id)
    if current_user.role in PM_SCOPED_ROLES and client and client.pm_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    if meeting.status == GlobalTaskStatus.RESOLVED:
        raise HTTPException(status_code=400, detail="Cannot cancel a completed meeting.")

    meeting.status = GlobalTaskStatus.CANCELLED
    meeting.cancellation_reason = cancel_in.reason
    await meeting.save()

    try:
        from app.utils.notify_helpers import notify_client_stakeholders
        if client:
            reason_suffix = f" Reason: {cancel_in.reason}" if cancel_in.reason else ""
            await notify_client_stakeholders(
                client,
                "❌ Meeting Cancelled",
                f"Meeting '{meeting.title}' with {client.name} has been cancelled.{reason_suffix}",
                actor_id=current_user.id,
            )
    except Exception as e:
        print(f"Notification error: {e}")

    return meeting
