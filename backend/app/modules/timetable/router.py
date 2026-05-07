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

    # --- Resolve User ID from Assignee Name if possible ---
    target_user_id = user_id
    assignee_name = event_in.assignee_name
    target_user = None

    if assignee_name and assignee_name not in ("All Employees", ""):
        import re
        clean_name = re.sub(r'\s*\([^)]*\)$', '', assignee_name.strip())
        pattern = re.compile(f"^{re.escape(clean_name)}$", re.IGNORECASE)
        target_user = await User.find_one(
            User.is_deleted == False,
            Or({"name": pattern}, {"email": pattern})
        )
        if target_user:
            target_user_id = target_user.id

    event = TimetableEvent(**event_in.model_dump(), user_id=target_user_id)
    await event.insert()

    # --- Notify assignee if different from creator ---
    if target_user and target_user.id != user_id:
        try:
            from app.utils.notify_helpers import create_notification
            await create_notification(
                user_id=target_user.id,
                title="📅 New Activity Scheduled",
                message=(
                    f"{current_user.name or 'Admin'} scheduled "
                    f"'{event.title}' for you on {event.date}."
                ),
                actor_id=current_user.id
            )
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

    def get_hm(val, default_h=0):
        if not val:
            return default_h, 0
        if isinstance(val, str):
            import re
            m = re.search(r'(\d+):(\d+)\s*(AM|PM)?', val, re.I)
            if m:
                try:
                    h = int(m.group(1))
                    m_val = int(m.group(2))
                    ampm = m.group(3)
                    if ampm:
                        if ampm.upper() == 'PM' and h < 12: h += 12
                        elif ampm.upper() == 'AM' and h == 12: h = 0
                    return h, m_val
                except Exception: pass
            
            m2 = re.search(r'(\d+)\s*(AM|PM)?', val, re.I)
            if m2:
                try:
                    h = int(m2.group(1))
                    ampm = m2.group(2)
                    if ampm:
                        if ampm.upper() == 'PM' and h < 12: h += 12
                        elif ampm.upper() == 'AM' and h == 12: h = 0
                    return h, 0
                except Exception: pass
        try:
            return val.hour, val.minute
        except Exception:
            return default_h, 0

    user_id = current_user.id if current_user else None
    username = (current_user.name or current_user.email or "Unknown User") if current_user else "Demo Admin"
    is_admin = current_user.role == UserRole.ADMIN if current_user else True

    # 1. Fetch all data sources first
    v_query = Visit.find(Visit.is_deleted == False, Visit.visit_date >= start_date, Visit.visit_date <= end_date)
    if not is_admin:
        v_query = v_query.find(Visit.user_id == user_id)
    visits = await v_query.to_list()

    m_query = MeetingSummary.find(MeetingSummary.is_deleted == False, MeetingSummary.date >= start_date, MeetingSummary.date <= end_date)
    meetings = await m_query.to_list()

    t_query = Todo.find(Todo.is_deleted == False, Todo.due_date >= start_date, Todo.due_date <= end_date)
    if not is_admin:
        t_query = t_query.find(Todo.user_id == user_id)
    todos = await t_query.to_list()

    s_date, e_date = start_date.date(), end_date.date()
    tt_query = TimetableEvent.find(TimetableEvent.is_deleted == False, TimetableEvent.date >= s_date, TimetableEvent.date <= e_date)
    if not is_admin:
        tt_query = tt_query.find(TimetableEvent.user_id == user_id)
    custom_events = await tt_query.to_list()

    demo_query = Shop.find(Shop.demo_scheduled_at != None)
    if not is_admin:
        demo_query = demo_query.find(Shop.project_manager_id == user_id)
    demo_shops = await demo_query.to_list()

    # 2. Collect IDs for bulk fetching
    collected_shop_ids = set()
    collected_user_ids = set()
    collected_client_ids = set()

    for v in visits:
        if v.shop_id: collected_shop_ids.add(v.shop_id)
        if v.user_id: collected_user_ids.add(v.user_id)
    
    for m in meetings:
        if m.client_id: collected_client_ids.add(m.client_id)
    
    for t in todos:
        if t.user_id: collected_user_ids.add(t.user_id)
        
    for c in custom_events:
        if c.user_id: collected_user_ids.add(c.user_id)
        
    for s in demo_shops:
        collected_shop_ids.add(s.id)
        if s.project_manager_id: collected_user_ids.add(s.project_manager_id)

    # 3. Bulk Fetch
    shops_task = Shop.find(In(Shop.id, list(collected_shop_ids)), Shop.is_deleted == False).to_list()
    clients_task = Client.find(In(Client.id, list(collected_client_ids)), Client.is_deleted == False).to_list()
    users_task = User.find(In(User.id, list(collected_user_ids))).to_list()

    # Optional: could use asyncio.gather for even more speed
    import asyncio
    shops_list, clients_list, users_list = await asyncio.gather(shops_task, clients_task, users_task)

    # 4. Create Maps
    shop_map = {s.id: s for s in shops_list}
    client_map = {c.id: c for c in clients_list}
    user_name_map = {u.id: (u.name or u.email or "Unknown") for u in users_list}
    
    # Also need Client owner_ids for meeting user mapping
    for c in clients_list:
        if c.owner_id: collected_user_ids.add(c.owner_id)
    
    # If we found new user IDs (client owners), fetch again or just include them initially
    # Improving step 2 to include client owners
    for c in clients_list:
        if c.owner_id and c.owner_id not in user_name_map:
             u = await User.get(c.owner_id)
             if u: user_name_map[u.id] = (u.name or u.email)

    # 5. Process Events
    # --- Process Visits ---
    for v in visits:
        shop = shop_map.get(v.shop_id)
        if not shop: continue
        
        h = v.visit_date.hour if v.visit_date.hour >= 7 else 10
        real_user = user_name_map.get(v.user_id, username)

        events.append({
            "id": str(v.id),
            "title": f"Visit: {shop.name}",
            "date": date_str(v.visit_date),
            "user": real_user,
            "sh": h, "sm": 0, "eh": h+1, "em": 0,
            "loc": (shop.area_name if hasattr(shop, 'area_name') and shop.area_name else "Shop"),
            "event_type": "VISIT",
            "status": v.status,
            "reference_id": str(v.shop_id),
            "description": v.remarks
        })

    # --- Process Meetings ---
    for m in meetings:
        client = client_map.get(m.client_id)
        
        is_visible = is_admin
        if not is_visible:
            # Check user role overrides or explicit inclusion
            if m.host_id == user_id or (m.attendee_ids and user_id in m.attendee_ids):
                is_visible = True
            elif client:
                role_val = current_user.role.value
                if role_val in ["PROJECT_MANAGER", "PROJECT_MANAGER_AND_SALES"] and client.pm_id == user_id:
                    is_visible = True
                elif role_val not in ["PROJECT_MANAGER", "PROJECT_MANAGER_AND_SALES"] and client.owner_id == user_id:
                    is_visible = True
                    
        if not is_visible:
            continue
            
        # Determine start/end times precisely
        sh, sm = get_hm(m.start_time, m.date.hour if m.date.hour >= 7 else 14)
        eh, em = get_hm(m.end_time, sh + 1)
        if not m.end_time:
            # If no end_time stored, default to 1 hour (down from 1.5h bug)
            eh, em = sh + 1, 0

        # Display name for user column 
        real_user = user_name_map.get(m.host_id, username)
        if client and client.owner_id and m.host_id != client.owner_id:
            real_user = f"{real_user} / {user_name_map.get(client.owner_id, 'Rep')}"

        title = f"Meeting: {client.name}" if client else f"Meeting: {m.title}"
        if m.project_id and not client:
            title = f"Project Sync: {m.title}"

        events.append({
            "id": str(m.id),
            "title": title,
            "date": date_str(m.date),
            "user": real_user,
            "sh": sh, "sm": sm, "eh": eh, "em": em,
            "loc": "Office/Online",
            "event_type": "MEETING",
            "status": m.status,
            "priority": m.priority or "MEDIUM",
            "reference_id": str(m.client_id) if m.client_id else "",
            "description": m.content
        })

    # --- Process Todos ---
    for t in todos:
        if t.related_entity and "MEETING:" in t.related_entity: continue
            
        h = t.due_date.hour if t.due_date and hasattr(t.due_date, 'hour') else 9
        sh, sm = get_hm(t.start_time, h)
        eh, em = get_hm(t.end_time, sh + 1)
        
        real_user = t.assigned_to or user_name_map.get(t.user_id, username)

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

    # --- Process Custom Events ---
    for c in custom_events:
        real_user = c.assignee_name or user_name_map.get(c.user_id, username)
        
        sh, sm = get_hm(c.start_time, 9)
        eh, em = get_hm(c.end_time, sh + 1)

        events.append({
            "id": str(c.id),
            "title": c.title,
            "date": c.date.strftime("%Y-%m-%d"),
            "user": real_user,
            "sh": sh, "sm": sm,
            "eh": eh, "em": em,
            "loc": c.location or "",
            "event_type": "TIMETABLE",
            "status": c.status or "PENDING",
            "priority": c.priority or "MEDIUM",
            "reference_id": str(c.id),
            "description": None
        })

    # --- Process Demos ---
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    for shop in demo_shops:
        start_dt = shop.demo_scheduled_at
        if not start_dt: continue
        
        local_start = (start_dt if start_dt.tzinfo else start_dt.replace(tzinfo=UTC)).astimezone(ist_tz)
        local_end = local_start + timedelta(hours=1)
        
        pm_name = user_name_map.get(shop.project_manager_id, username)
        status_val = "COMPLETED" if shop.demo_stage and shop.demo_stage > 0 else "OPEN"
        
        events.append({
            "id": str(shop.id),
            "title": f"Demo: {shop.name}",
            "date": local_start.strftime("%Y-%m-%d"),
            "user": pm_name,
            "sh": local_start.hour, "sm": local_start.minute,
            "eh": local_end.hour, "em": local_end.minute,
            "loc": shop.demo_meet_link or "Scheduled Demo",
            "event_type": "MEETING",
            "status": status_val,
            "reference_id": str(shop.id),
            "description": "Demo session for new lead"
        })

    return {"events": events}
    return {"events": events}
