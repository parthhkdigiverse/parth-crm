# backend/app/modules/activity_logs/router.py
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Any, Optional
from app.core.dependencies import get_current_active_user
from app.modules.activity_logs.service import ActivityLogger
from app.modules.users.models import User, UserRole

router = APIRouter()

@router.get("/", response_model=List[Any]) # Nuclear relaxation to Any
async def read_activity_logs(
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: User = Depends(get_current_active_user)
):
    """
    Fetch activity logs. Admin-only access for full history,
    staff roles can see restricted history.
    """
    allowed_roles = [
        UserRole.ADMIN, 
        UserRole.SALES, 
        UserRole.TELESALES, 
        UserRole.PROJECT_MANAGER, 
        UserRole.PROJECT_MANAGER_AND_SALES
    ]
    if current_user and current_user.role not in allowed_roles:
         raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have enough privileges to view activity logs"
        )
    
    logger = ActivityLogger()
    logs = await logger.get_logs(skip=skip, limit=limit, current_user=current_user)
    
    # Manually serialize to dict to avoid Pydantic validation crashes on legacy data
    import json
    result = []
    for log in logs:
        log_dict = log.model_dump() if hasattr(log, "model_dump") else dict(log)
        # Ensure ID is string and also capture nested ObjectIds/datetimes
        if "_id" in log_dict: log_dict["id"] = log_dict.pop("_id")
        
        # Generic ObjectId/datetime to string conversion
        clean_dict = json.loads(json.dumps(log_dict, default=str))
        result.append(clean_dict)
    return result
