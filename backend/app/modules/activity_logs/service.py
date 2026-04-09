# backend/app/modules/activity_logs/service.py
from beanie import PydanticObjectId
from app.modules.activity_logs.models import ActivityLog, ActionType, EntityType
from app.modules.users.models import UserRole, User
from typing import Optional, List, Any
from fastapi import Request

class ActivityLogger:
    def __init__(self):
        # No db session needed in Beanie!
        self.sensitive_fields = {"password", "hashed_password", "token", "access_token", "refresh_token", "secret", "otp"}

    def _filter_sensitive_data(self, data: dict):
        if not data:
            return None
        return {k: (v if k not in self.sensitive_fields else "[REDACTED]") for k, v in data.items()}

    async def log_activity(
        self,
        user_id: Optional[PydanticObjectId],
        user_role: UserRole,
        action: ActionType,
        entity_type: EntityType,
        entity_id: Any, # Use Any for flexibility, though usually PydanticObjectId
        old_data: Optional[dict] = None,
        new_data: Optional[dict] = None,
        request: Request = None
    ):
        # Handle Synthetic/Demo users (id=0) or None
        if user_id == 0:
            user_id = None
            
        ip_address = request.client.host if request else None
        role_str = user_role.value if hasattr(user_role, 'value') else str(user_role)

        activity_log = ActivityLog(
            user_id=user_id,
            user_role=role_str,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else None,
            old_data=self._filter_sensitive_data(old_data),
            new_data=self._filter_sensitive_data(new_data),
            ip_address=ip_address
        )
        await activity_log.insert()
        return activity_log

    async def get_logs(self, skip: int = 0, limit: Optional[int] = None, current_user = None):
        try:
            find_query = ActivityLog.find_all()
            
            if current_user and current_user.role != UserRole.ADMIN:
                find_query = ActivityLog.find(ActivityLog.user_id == current_user.id)
            
            # Build query — only apply limit when explicitly provided
            query = find_query.sort("-created_at").skip(skip)
            if limit is not None:
                query = query.limit(limit)
            logs = await query.to_list()
            
            for log in logs:
                if log.user_id:
                    # Sequential fetch instead of join
                    user = await User.get(log.user_id)
                    if user:
                        log.user_name = user.name or user.email or user.employee_code or f"User #{log.user_id}"
                    else:
                        log.user_name = f"User #{log.user_id}"
                else:
                    log.user_name = "System"
            return logs
        except Exception as e:
            print(f"Error fetching logs: {e}")
            return []
