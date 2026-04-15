# backend/app/modules/feedback/models.py
from typing import Optional
from datetime import datetime, UTC
from pydantic import Field
from beanie import Document, Indexed, PydanticObjectId

class Feedback(Document):
    client_id: Optional[PydanticObjectId] = None
    client_name: Optional[str] = None # Full Name
    mobile: Optional[str] = None
    shop_name: Optional[str] = None
    product: Optional[str] = None
    rating: int = 0 # Legacy Sales Person Rating (1-5)
    product_rating: int = 0 # New Product Rating (1-5)
    agent_score: int = 0 # New Agent Performance Score (1-10)
    comments: Optional[str] = None
    agent_name: Optional[str] = None
    agent_role: Optional[str] = None
    referral_code: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_deleted: bool = False

    class Settings:
        name = "srm_feedbacks"

class UserFeedback(Document):
    user_id: Indexed(PydanticObjectId)
    subject: str
    message: str
    status: str = "PENDING"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_deleted: bool = False

    class Settings:
        name = "srm_user_feedbacks"
