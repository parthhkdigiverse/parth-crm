# backend/app/modules/timetable/router.py
from typing import List, Any, Optional
from fastapi import APIRouter, Depends, Query, status, HTTPException, Response
from datetime import datetime, timedelta, UTC, timezone, date as dt_date
from beanie import PydanticObjectId
from beanie.operators import Or, And, In

from app.core.dependencies import get_current_user
from app.modules.users.models import User, UserRole
from app.modules.timetable.schemas import TimelineEvent, TimetableResponse, TimetableEventCreate, TimetableEventRead, TimetableEventUpdate
from app.modules.timetable.models import TimetableEvent
from app.modules.visits.models import Visit
from app.modules.meetings.models import MeetingSummary
from app.modules.todos.models import Todo
from app.modules.shops.models import Shop
from app.modules.clients.models import Client
from app.modules.notifications.models import Notification
from app.modules.settings.models import SystemSettings

router = APIRouter()

@router.post("/", response_model=TimetableEventRead, status_code=status.HTTP_201_CREATED)
async def create_timetable_event(
    event_in: TimetableEventCreate,
    current_user: User = Depends(get_current_user)
) -> Any:
    user_id = current_user.id if current_user else None
    
    if not user_id:
        fallback = await User.find_one()
        if fallback:
            user_id = fallback.id
            
    if current_user and current_user.role == UserRole.ADMIN and event_in.assignee_name == "All Employees":
        active_users = await User.find(User.is_active == True, User.is_deleted == False).to_list()
        created_events = []
        for u in active_users:
            new_event = TimetableEvent(**event_in.model_dump(), user_id=u.id)
            new_event.assignee_name = u.name or u.email
            await new_event.insert()
            created_events.append(new_event)
            
            try:
                notif = Notification(
                    user_id=u.id,
                    title="New Global Activity",
                    message=f"Admin scheduled a company-wide activity: '{event_in.title}' on {event_in.date}."
                )
                await notif.insert()
            except Exception:
                pass
                
        return created_events[0] if created_events else None

    event = TimetableEvent(**event_in.model_dump(), user_id=user_id)
    await event.insert()

    # --- Notify assignee if different from creator ---
    try:
        assignee_name = event.assignee_name
        if assignee_name and assignee_name not in ("All Employees", ""):
            import re
            pattern = re.compile(f"^{re.escape(assignee_name.strip())}$", re.IGNORECASE)
            target = await User.find_one(
                User.is_deleted == False,
                Or({"name": pattern}, {"email": pattern})
            )
            
            if target and target.id != user_id:
                notif = Notification(
                    user_id=target.id,
                    title="New Activity Scheduled",
                    message=(
                        f"{current_user.name or 'Admin'} scheduled "
                        f"'{event.title}' for you on {event.date}."
                    ),
                    is_read=False
                )
                await notif.insert()
    except Exception as _ne:
        print(f"[Timetable] Notification error: {_ne}")

    return event

@router.patch("/{event_id}", response_model=TimetableEventRead)
async def update_timetable_event(
    event_id: PydanticObjectId,
    event_in: TimetableEventUpdate,
    current_user: User = Depends(get_current_user)
) -> Any:
    query = TimetableEvent.find(TimetableEvent.id == event_id, TimetableEvent.is_deleted == False)
    if current_user and current_user.role != UserRole.ADMIN:
        query = query.find(TimetableEvent.user_id == current_user.id)
    
    event = await query.first_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Timetable event not found")
        
    update_data = event_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(event, field, value)
        
    await event.save()
    return event


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_timetable_event(
    event_id: PydanticObjectId,
    current_user: User = Depends(get_current_user)
) -> None:
    query = TimetableEvent.find(TimetableEvent.id == event_id, TimetableEvent.is_deleted == False)
    if current_user and current_user.role != UserRole.ADMIN:
        query = query.find(TimetableEvent.user_id == current_user.id)
    
    event = await query.first_or_none()
    
    if not event:
        raise HTTPException(status_code=404, detail="Timetable event not found")
        
    settings = await SystemSettings.find_one()
    is_hard = settings and settings.delete_policy == "HARD"

    if is_hard:
        await event.delete()
    else:
        event.is_deleted = True
        await event.save()
        
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/", response_model=TimetableResponse)
async def get_timetable(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    current_user: User = Depends(get_current_user)
) -> Any:
    if not start_date:
        start_date = datetime.now(UTC) - timedelta(days=30)
    if not end_date:
        end_date = datetime.now(UTC) + timedelta(days=30)

    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=UTC)
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=UTC)

    if end_date.time() == datetime.min.time():
        end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)

    events = []

    def date_str(dt):
        return dt.strftime("%Y-%m-%d") if dt else ""

    user_id = current_user.id if current_user else None
    username = (current_user.name or current_user.email or "Unknown User") if current_user else "Demo Admin"
    is_admin = current_user.role == UserRole.ADMIN if current_user else True

    # 1. Fetch Visits
    v_query = Visit.find(Visit.is_deleted == False, Visit.visit_date >= start_date, Visit.visit_date <= end_date)
    if not is_admin:
        v_query = v_query.find(Visit.user_id == user_id)
        
    visits = await v_query.to_list()
    # Filter by Shop deleted status requires manual lookup
    valid_shop_ids = await Shop.get_motor_collection().distinct("_id", {"is_deleted": False})
    valid_shop_str = [str(x) for x in valid_shop_ids]

    for v in visits:
        if str(v.shop_id) not in valid_shop_str:
            continue
            
        shop = await Shop.get(v.shop_id)
        h = v.visit_date.hour if v.visit_date.hour >= 7 else 10
        
        real_user = username
        try:
            if v.user_id:
                u = await User.get(v.user_id)
                if u: real_user = u.name or u.email
        except:
            pass

        events.append({
            "id": str(v.id),
            "title": f"Visit: {shop.name if shop else 'Unknown Shop'}",
            "date": date_str(v.visit_date),
            "user": real_user,
            "sh": h, "sm": 0, "eh": h+1, "em": 0,
            "loc": (shop.area.name if shop and getattr(shop, 'area', None) else "Shop"),
            "event_type": "VISIT",
            "status": v.status,
            "reference_id": str(v.shop_id),
            "description": v.remarks
        })

    # 2. Fetch Meetings
    m_query = MeetingSummary.find(MeetingSummary.is_deleted == False, MeetingSummary.date >= start_date, MeetingSummary.date <= end_date)
    meetings = await m_query.to_list()
    
    valid_client_ids = await Client.get_motor_collection().distinct("_id", {"is_deleted": False})
    valid_client_str = [str(x) for x in valid_client_ids]
    
    for m in meetings:
        if m.client_id and str(m.client_id) not in valid_client_str:
            continue
            
        client = await Client.get(m.client_id) if m.client_id else None
        
        # Admin or specific PM/Owner filters
        if not is_admin and client:
            role_val = current_user.role.value
            if role_val in ["PROJECT_MANAGER", "PROJECT_MANAGER_AND_SALES"] and client.pm_id != user_id: continue
            if role_val not in ["PROJECT_MANAGER", "PROJECT_MANAGER_AND_SALES"] and client.owner_id != user_id: continue

        h = m.date.hour if m.date.hour >= 7 else 14
        real_user = username
        if client and client.owner_id:
            u = await User.get(client.owner_id)
            if u: real_user = u.name or u.email

        events.append({
            "id": str(m.id),
            "title": f"Meeting: {client.name if client else 'Unknown Client'}",
            "date": date_str(m.date),
            "user": real_user,
            "sh": h, "sm": 0, "eh": h+1, "em": 30,
            "loc": "Office/Online",
            "event_type": "MEETING",
            "status": m.status,
            "priority": m.priority or "MEDIUM",
            "reference_id": str(m.client_id) if m.client_id else "",
            "description": m.content
        })

    # 3. Fetch Todos
    t_query = Todo.find(Todo.is_deleted == False, Todo.due_date >= start_date, Todo.due_date <= end_date)
    if not is_admin:
        t_query = t_query.find(Todo.user_id == user_id)
        
    todos = await t_query.to_list()
    for t in todos:
        if t.related_entity and "MEETING:" in t.related_entity:
            continue
            
        h = t.due_date.hour if t.due_date and t.due_date.hour >= 7 else 9
        sh = t.start_time.hour if t.start_time else h
        sm = t.start_time.minute if t.start_time else 0
        eh = t.end_time.hour if t.end_time else (sh + 1)
        em = t.end_time.minute if t.end_time else 0
        
        real_user = t.assigned_to or username
        if not t.assigned_to and is_admin:
            u = await User.get(t.user_id)
            if u: real_user = u.name or u.email

        events.append({
            "id": str(t.id),
            "title": f"Todo: {t.title}",
            "date": date_str(t.due_date),
            "user": real_user,
            "sh": sh, "sm": sm, "eh": eh, "em": em,
            "loc": t.related_entity or "",
            "event_type": "TODO",
            "status": t.status,
            "priority": t.priority,
            "reference_id": str(t.id),
            "description": t.description
        })

    # 4. Fetch Custom Timetable Events
    # Map UTC start_date and end_date to exact dates
    s_date = start_date.date()
    e_date = end_date.date()
    
    tt_query = TimetableEvent.find(
        TimetableEvent.is_deleted == False,
        TimetableEvent.date >= s_date,
        TimetableEvent.date <= e_date
    )
    if not is_admin:
        tt_query = tt_query.find(TimetableEvent.user_id == user_id)
        
    custom_events = await tt_query.to_list()
    for c in custom_events:
        real_user = c.assignee_name or username
        if not c.assignee_name and is_admin:
            u = await User.get(c.user_id)
            if u: real_user = u.name or u.email

        events.append({
            "id": str(c.id),
            "title": c.title,
            "date": c.date.strftime("%Y-%m-%d"),
            "user": real_user,
            "sh": c.start_time.hour, "sm": c.start_time.minute,
            "eh": c.end_time.hour, "em": c.end_time.minute,
            "loc": c.location or "",
            "event_type": "TIMETABLE",
            "status": "PENDING",
            "priority": c.priority or "MEDIUM",
            "reference_id": str(c.id),
            "description": None
        })

    # 5. Fetch Scheduled Shop Demos
    demo_query = Shop.find(Shop.demo_scheduled_at != None)
    if not is_admin:
        demo_query = demo_query.find(Shop.project_manager_id == user_id)
        
    demo_shops = await demo_query.to_list()
    ist_tz = timezone(timedelta(hours=5, minutes=30))

    for shop in demo_shops:
        start_dt = shop.demo_scheduled_at
        if not start_dt: continue
        
        if start_dt.tzinfo:
            local_start = start_dt.astimezone(ist_tz)
        else:
            local_start = start_dt.replace(tzinfo=UTC).astimezone(ist_tz)
            
        local_end = local_start + timedelta(hours=1)
        
        pm_name = username
        if shop.project_manager_id:
            pm_user = await User.get(shop.project_manager_id)
            if pm_user: pm_name = pm_user.name or pm_user.email
            
        status_val = "COMPLETED" if shop.demo_stage and shop.demo_stage > 0 else "OPEN"
        loc_val = shop.demo_meet_link or "Scheduled Demo"
        
        events.append({
            "id": str(shop.id), # Avoiding math collision, strings are safe in Pydantic
            "title": f"Demo: {shop.name}",
            "date": local_start.strftime("%Y-%m-%d"),
            "user": pm_name,
            "sh": local_start.hour, "sm": local_start.minute,
            "eh": local_end.hour, "em": local_end.minute,
            "loc": loc_val,
            "event_type": "MEETING",
            "status": status_val,
            "reference_id": str(shop.id),
            "description": "Demo session for new lead"
        })

    return {"events": events}
