import datetime
from beanie import PydanticObjectId
from app.core.base_schema import MongoBaseSchema
from app.modules.todos.models import TodoStatus, TodoPriority

class TodoBase(MongoBaseSchema):
    title: str
    description: str | None = None
    due_date: datetime.datetime | None = None
    start_time: str | None = None
    end_time: str | None = None
    status: TodoStatus | None = TodoStatus.PENDING
    priority: TodoPriority | None = TodoPriority.MEDIUM
    assigned_to: str | None = None
    related_entity: str | None = None
    evidence_url: str | None = None
    client_id: PydanticObjectId | None = None

class TodoCreate(TodoBase):
    pass

class TodoUpdate(MongoBaseSchema):
    title: str | None = None
    description: str | None = None
    due_date: datetime.datetime | None = None
    start_time: str | None = None
    end_time: str | None = None
    status: TodoStatus | None = None
    priority: TodoPriority | None = None
    assigned_to: str | None = None
    related_entity: str | None = None
    evidence_url: str | None = None
    client_id: PydanticObjectId | None = None

class TodoRead(TodoBase):
    id: PydanticObjectId
    user_id: PydanticObjectId
    created_at: datetime.datetime
    updated_at: datetime.datetime

class TodoBulkDelete(MongoBaseSchema):
    ids: list[PydanticObjectId]
