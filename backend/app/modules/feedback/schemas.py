from datetime import datetime
from beanie import PydanticObjectId
from app.core.base_schema import MongoBaseSchema

class FeedbackBase(MongoBaseSchema):
    rating: int
    comments: str | None = None
    client_name: str | None = None
    mobile: str | None = None
    shop_name: str | None = None
    product: str | None = None
    product_rating: int = 0 
    agent_score: int = 0
    agent_name: str | None = None
    agent_role: str | None = None
    referral_code: str | None = None
    client_id: PydanticObjectId | None = None

class FeedbackCreate(FeedbackBase):
    pass

class FeedbackRead(FeedbackBase):
    id: PydanticObjectId
    created_at: datetime

class UserFeedbackBase(MongoBaseSchema):
    subject: str
    message: str

class UserFeedbackCreate(UserFeedbackBase):
    pass

class UserFeedbackUpdate(MongoBaseSchema):
    status: str

class UserFeedbackRead(UserFeedbackBase):
    id: PydanticObjectId
    user_id: PydanticObjectId
    status: str
    created_at: datetime
