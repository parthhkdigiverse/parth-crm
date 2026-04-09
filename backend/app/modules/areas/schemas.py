from typing import List
from beanie import PydanticObjectId as BeaniePydanticObjectId
from app.core.base_schema import MongoBaseSchema, PydanticObjectId

class AreaBase(MongoBaseSchema):
    name: str
    description: str | None = None
    pincode: str | None = None
    city: str | None = None
    lat: float | None = None
    lng: float | None = None
    radius_meters: int | None = 500
    shop_limit: int | None = 20
    priority_level: str | None = "MEDIUM"
    auto_discovery_enabled: bool | None = False
    target_categories: List[str] | None = None

class AreaCreate(AreaBase):
    pass

class AreaUpdate(MongoBaseSchema):
    name: str | None = None
    description: str | None = None
    pincode: str | None = None
    city: str | None = None
    lat: float | None = None
    lng: float | None = None
    radius_meters: int | None = None
    shop_limit: int | None = None
    priority_level: str | None = None
    auto_discovery_enabled: bool | None = None
    target_categories: List[str] | None = None

class AreaAssign(MongoBaseSchema):
    user_ids: List[PydanticObjectId]
    shop_ids: List[PydanticObjectId] | None = None

class AssignedUser(MongoBaseSchema):
    id: PydanticObjectId
    name: str | None = None
    role: str | None = None

class AreaRead(AreaBase):
    id: PydanticObjectId
    assigned_user_id: PydanticObjectId | None = None
    shops_count: int | None = 0
    is_archived: bool | None = False
    archived_by_id: PydanticObjectId | None = None
    archived_by_name: str | None = None
    created_by_id: PydanticObjectId | None = None
    created_by_name: str | None = None
    assignment_status: str | None = "UNASSIGNED"
    assigned_users: List[AssignedUser] = []
