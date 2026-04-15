# backend/app/modules/feedback/service.py
from beanie import PydanticObjectId
from beanie.operators import In
from app.modules.feedback.models import Feedback, UserFeedback
from app.modules.feedback.schemas import FeedbackCreate, UserFeedbackCreate
from app.modules.notifications.models import Notification
from app.modules.users.models import User, UserRole
from typing import List, Optional

class FeedbackService:
    def __init__(self):
        # No db session needed in Beanie!
        pass

    async def create_client_feedback(self, feedback_in: FeedbackCreate) -> Feedback:
        data = feedback_in.model_dump()
        # Remove fields that do not exist in the Document model (transient/UI fields)
        data.pop('agent_role', None)

        db_feedback = Feedback(**data)
        await db_feedback.insert()

        # Notify Admins asynchronously
        try:
            admins = await User.find(User.role == UserRole.ADMIN).to_list()
            for admin in admins:
                notif = Notification(
                    user_id=admin.id,
                    title=f"[Feedback] Client Feedback Received: {db_feedback.client_name or 'New Client'}",
                    message=f"New feedback received from {db_feedback.client_name or 'a client'}. Rating: {db_feedback.rating}/5."
                )
                await notif.insert()
        except Exception as e:
            print(f"Error creating feedback notification: {e}")

        return db_feedback

    async def _attach_roles(self, feedbacks: List[Feedback]) -> List[Feedback]:
        """Manual join replacement: Attach user roles and names to feedback based on referral codes."""
        if not feedbacks:
            return feedbacks
            
        ref_codes = list({fb.referral_code.strip().upper() for fb in feedbacks if fb.referral_code})
        user_map = {} # Map ref_code (upper) to user object
        if ref_codes:
            users = await User.find(In(User.referral_code, ref_codes)).to_list()
            for u in users:
                if u.referral_code:
                    user_map[u.referral_code.upper()] = u
                    
        for fb in feedbacks:
            ref = fb.referral_code.strip().upper() if fb.referral_code else None
            u = user_map.get(ref)
            if u:
                role_str = u.role.value if hasattr(u.role, 'value') else str(u.role)
                fb.agent_role = role_str.replace("_", " ").title()
                fb.agent_name = u.name
            else:
                fb.agent_role = "Sales Executive"
            
        return feedbacks

    async def get_client_feedbacks(self, client_id: PydanticObjectId, skip: int = 0, limit: Optional[int] = None):
        query = Feedback.find(Feedback.client_id == client_id).sort("-created_at").skip(skip)
        if limit is not None:
            query = query.limit(limit)
        feedbacks = await query.to_list()
        return await self._attach_roles(feedbacks)

    async def get_all_client_feedbacks(self, skip: int = 0, limit: Optional[int] = None):
        query = Feedback.find_all().sort("-created_at").skip(skip)
        if limit is not None:
            query = query.limit(limit)
        feedbacks = await query.to_list()
        return await self._attach_roles(feedbacks)

    async def get_feedbacks(self, current_user: User, skip: int = 0, limit: Optional[int] = None) -> List[Feedback]:
        """List feedbacks with restricted visibility for non-admins."""
        if current_user.role == UserRole.ADMIN:
            return await self.get_all_client_feedbacks(skip, limit)
        
        # 1. Identify all clients managed/owned by the user
        from app.modules.clients.models import Client as ClientModel
        raw_client_ids = await ClientModel.get_pymongo_collection().distinct("_id", {
            "$or": [
                {"pm_id": current_user.id},
                {"owner_id": current_user.id},
                {"referred_by_id": current_user.id}
            ]
        })
        client_ids = [PydanticObjectId(cid) for cid in raw_client_ids if cid]
        
        # 2. Identify all Admin referral codes (using motor collection for distinct)
        admin_ref_codes = await User.get_pymongo_collection().distinct("referral_code", {"role": UserRole.ADMIN.value})
        admin_ref_codes = [c.upper() for c in admin_ref_codes if c]
        
        # 3. Build strictly restricted query
        mongo_conditions = []
        
        # Condition A: Feedback collected by the user themselves
        if current_user.referral_code:
            mongo_conditions.append({
                "referral_code": {"$regex": f"^{current_user.referral_code.strip()}$", "$options": "i"}
            })
        
        # Condition B: Feedback for user's client AND collected by an Admin
        if client_ids and admin_ref_codes:
            mongo_conditions.append({
                "client_id": {"$in": client_ids},
                "referral_code": {"$in": admin_ref_codes}
            })
            
        if not mongo_conditions:
            return []
            
        # Execute the optimized query
        query = Feedback.find({"$or": mongo_conditions}).sort("-created_at").skip(skip)
        
        if limit is not None:
            query = query.limit(limit)
            
        feedbacks = await query.to_list()
        return await self._attach_roles(feedbacks)

    async def create_user_feedback(self, user_id: PydanticObjectId, feedback_in: UserFeedbackCreate) -> UserFeedback:
        db_feedback = UserFeedback(
            **feedback_in.model_dump(),
            user_id=user_id
        )
        await db_feedback.insert()
        return db_feedback

    async def get_user_feedbacks(self):
        return await UserFeedback.find_all().to_list()

    async def delete_feedback(self, feedback_id: PydanticObjectId):
        db_feedback = await Feedback.get(feedback_id)
        if not db_feedback:
             raise HTTPException(status_code=404, detail="Feedback not found")
        await db_feedback.delete()
        return True

    async def batch_delete_feedbacks(self, ids: List[PydanticObjectId]):
        """Delete multiple feedbacks by their IDs."""
        if not ids:
            return
        await Feedback.find(In(Feedback.id, ids)).delete()
