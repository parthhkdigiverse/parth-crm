# backend/app/modules/todos/router.py
from typing import List, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response
from datetime import datetime, UTC
from beanie import PydanticObjectId
from beanie.operators import Or

from app.core.dependencies import get_current_user
from app.modules.users.models import User, UserRole
from app.modules.todos.models import Todo, TodoStatus
from app.modules.todos.schemas import TodoCreate, TodoRead, TodoUpdate
from app.modules.notifications.models import Notification

router = APIRouter()

def _is_admin(user: User) -> bool:
    return bool(user and user.role == UserRole.ADMIN)

async def _resolve_target_user(assigned_to: Optional[str]) -> Optional[User]:
    if not assigned_to:
        return None

    import re
    # Strip any trailing role suffix from UI, e.g., "Nency Savaliya (SALES)" -> "Nency Savaliya"
    clean_name = re.sub(r'\s*\([^)]*\)$', '', assigned_to.strip())
    normalized = clean_name.lower()
    
    if not normalized:
        return None

    pattern = re.compile(f"^{re.escape(normalized)}$", re.IGNORECASE)
    
    return await User.find_one(
        User.is_deleted == False,
        User.is_active == True,
        Or({"email": pattern}, {"name": pattern})
    )

@router.post("/", response_model=TodoRead, status_code=status.HTTP_201_CREATED)
async def create_todo(
    todo_in: TodoCreate,
    current_user: User = Depends(get_current_user)
) -> Any:
    owner = current_user
    payload = todo_in.model_dump()

    if _is_admin(current_user) and payload.get("assigned_to") == "All Employees":
        active_users = await User.find(User.is_deleted == False, User.is_active == True).to_list()
        created_todos = []
        for u in active_users:
            new_payload = payload.copy()
            new_payload["assigned_to"] = u.name or u.email
            todo = Todo(**new_payload, user_id=u.id)
            await todo.insert()
            created_todos.append(todo)
            
            # Notify User
            notif = Notification(
                user_id=u.id,
                title=f"[Task] New Task Assigned: {payload.get('title')}",
                message=f"Admin assigned you a new task: {payload.get('title')}."
            )
            await notif.insert()

        return created_todos[0] if created_todos else None

    if _is_admin(current_user) and payload.get("assigned_to"):
        owner = await _resolve_target_user(payload.get("assigned_to"))
        if not owner:
            raise HTTPException(status_code=404, detail="Assigned user not found")
        payload["assigned_to"] = owner.name or owner.email
    else:
        payload["assigned_to"] = current_user.name or current_user.email

    todo = Todo(**payload, user_id=owner.id if owner else current_user.id)
    await todo.insert()

    # Notify User if assigned to someone else
    recipient_id = owner.id if owner else current_user.id
    if recipient_id != current_user.id:
        try:
            notif = Notification(
                user_id=recipient_id,
                title=f"[Task] New Task Assigned: {todo.title}",
                message=f"{current_user.name} assigned you a new task: {todo.title}."
            )
            await notif.insert()
        except Exception as e:
            print(f"Error creating task assignment notification: {e}")

    # --- Synchronization: Create Meeting if client_id is present and NOT already a meeting task ---
    if todo.client_id and not (todo.related_entity and todo.related_entity.startswith("MEETING:")):
        from app.modules.meetings.models import MeetingSummary, MeetingType
        from app.core.enums import GlobalTaskStatus
        meeting = MeetingSummary(
            title=todo.title,
            content=todo.description or "",
            date=todo.due_date or datetime.now(UTC),
            status=GlobalTaskStatus.OPEN,
            meeting_type=MeetingType.IN_PERSON,
            client_id=todo.client_id,
            todo_id=todo.id,
            host_id=owner.id if owner else current_user.id
        )
        await meeting.insert()
    # -----------------------------------------------------------

    return todo


@router.get("/", response_model=List[TodoRead])
async def read_todos(
    skip: int = 0,
    limit: Optional[int] = None,
    status: Optional[TodoStatus] = None,
    assigned_to: Optional[str] = None,
    current_user: User = Depends(get_current_user)
) -> Any:
    query = Todo.find(Todo.is_deleted == False)

    if not _is_admin(current_user):
        query = query.find(Todo.user_id == current_user.id)

    if status:
        query = query.find(Todo.status == status)
    if assigned_to:
        query = query.find(Todo.assigned_to == assigned_to)

    # Build query — only apply limit when explicitly provided
    executable_query = query.sort("-created_at").skip(skip)
    if limit is not None:
        executable_query = executable_query.limit(limit)
    return await executable_query.to_list()

@router.patch("/{todo_id}", response_model=TodoRead)
async def update_todo(
    todo_id: PydanticObjectId,
    todo_in: TodoUpdate,
    current_user: User = Depends(get_current_user)
) -> Any:
    todo_query = Todo.find(Todo.id == todo_id)
    if not _is_admin(current_user):
        todo_query = todo_query.find(Todo.user_id == current_user.id)
    
    todo = await todo_query.first_or_none()
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
        
    update_data = todo_in.model_dump(exclude_unset=True)

    if _is_admin(current_user) and "assigned_to" in update_data and update_data.get("assigned_to"):
        owner = await _resolve_target_user(update_data.get("assigned_to"))
        if not owner:
            raise HTTPException(status_code=404, detail="Assigned user not found")
        todo.user_id = owner.id
        update_data["assigned_to"] = owner.name or owner.email
    elif not _is_admin(current_user):
        update_data.pop("assigned_to", None)

    for field, value in update_data.items():
        setattr(todo, field, value)
        
    await todo.save()

    # --- Synchronization: Update linked Meeting ---
    from app.modules.meetings.models import MeetingSummary
    meeting = await MeetingSummary.find_one(MeetingSummary.todo_id == todo.id)
    if meeting:
        if "title" in update_data:
            meeting.title = todo.title
        if "description" in update_data:
            meeting.content = todo.description
        if "due_date" in update_data:
            meeting.date = todo.due_date
        if "status" in update_data:
            from app.core.enums import GlobalTaskStatus
            if todo.status == TodoStatus.COMPLETED:
                meeting.status = GlobalTaskStatus.RESOLVED
        await meeting.save()
    # ----------------------------------------------

    return todo

@router.delete("/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_todo(
    todo_id: PydanticObjectId,
    current_user: User = Depends(get_current_user)
) -> None:
    todo_query = Todo.find(Todo.id == todo_id)
    if not _is_admin(current_user):
        todo_query = todo_query.find(Todo.user_id == current_user.id)
        
    todo = await todo_query.first_or_none()
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
        
    from app.modules.settings.models import SystemSettings
    settings = await SystemSettings.find_one()
    is_hard = settings and settings.delete_policy == "HARD"

    # --- Synchronization: Handle linked Meeting ---
    from app.modules.meetings.models import MeetingSummary
    meeting = await MeetingSummary.find_one(MeetingSummary.todo_id == todo.id)
    if meeting:
        if is_hard:
            await meeting.delete()
        else:
            meeting.is_deleted = True
            await meeting.save()
    # ----------------------------------------------

    if is_hard:
        await todo.delete()
    else:
        todo.is_deleted = True
        await todo.save()
        
    return Response(status_code=status.HTTP_204_NO_CONTENT)
