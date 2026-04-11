# backend/app/modules/todos/models.py
import enum
from typing import Optional
from datetime import datetime, time, UTC
from pydantic import Field
from beanie import Document, Indexed, PydanticObjectId

class TodoStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"

class TodoPriority(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

class Todo(Document):
    user_id: PydanticObjectId
    
    title: Indexed(str)
    description: Optional[str] = None
    
    due_date: Optional[datetime] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    status: TodoStatus = TodoStatus.PENDING
    priority: TodoPriority = TodoPriority.MEDIUM
    assigned_to: Optional[str] = None
    related_entity: Optional[str] = None
    evidence_url: Optional[str] = None
    is_deleted: bool = False
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    client_id: Optional[PydanticObjectId] = None
    project_id: Optional[PydanticObjectId] = None

    class Settings:
        name = "srm_todos"
        bson_encoders = {
            time: str
        }
