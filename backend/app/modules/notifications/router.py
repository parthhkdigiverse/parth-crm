# backend/app/modules/notifications/router.py
from typing import List, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response
from beanie import PydanticObjectId
from app.core.dependencies import get_current_user
from app.modules.users.models import User
from app.modules.notifications.models import Notification
from app.modules.notifications.schemas import NotificationRead
from app.modules.settings.models import SystemSettings

router = APIRouter()

@router.get("/", response_model=List[NotificationRead])
async def read_notifications(
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: User = Depends(get_current_user)
) -> Any:
    """Get all notifications for current user, newest first."""
    try:
        user_id = current_user.id if current_user else None
        if not user_id:
            return []
            
        settings = await SystemSettings.find_one()
        delete_policy = settings.delete_policy if settings else "SOFT"
        
        query = Notification.find(Notification.user_id == user_id).sort("-created_at").skip(skip)
        if delete_policy == "SOFT":
            query = query.find(Notification.is_deleted != True)
            
        if limit is not None:
            query = query.limit(limit)
            
        return await query.to_list()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch notifications: {str(exc)}"
        )

@router.get("/unread-count")
async def get_unread_count(
    current_user: User = Depends(get_current_user)
) -> dict:
    """Returns the count of unread notifications — used by the bell badge."""
    user_id = current_user.id if current_user else None
    if not user_id:
        return {"unread": 0}
        
    settings = await SystemSettings.find_one()
    delete_policy = settings.delete_policy if settings else "SOFT"
    
    query = Notification.find(Notification.user_id == user_id, Notification.is_read == False)
    if delete_policy == "SOFT":
        query = query.find(Notification.is_deleted != True)
        
    count = await query.count()
    return {"unread": count}

@router.patch("/{notification_id}/read", response_model=NotificationRead)
async def mark_notification_as_read(
    notification_id: PydanticObjectId,
    current_user: User = Depends(get_current_user)
) -> Any:
    user_id = current_user.id if current_user else None
    notification = await Notification.find_one(
        Notification.id == notification_id,
        Notification.user_id == user_id
    )
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    notification.is_read = True
    await notification.save()
    return notification

@router.post("/mark-all-read")
async def mark_all_read(
    current_user: User = Depends(get_current_user)
) -> dict:
    """Mark all of the current user's notifications as read."""
    user_id = current_user.id if current_user else None
    if not user_id:
        return {"status": "ok"}
        
    await Notification.find(
        Notification.user_id == user_id,
        Notification.is_read == False
    ).set({"is_read": True})
    
    return {"status": "ok"}

@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    notification_id: PydanticObjectId,
    current_user: User = Depends(get_current_user)
) -> Response:
    user_id = current_user.id if current_user else None
    notification = await Notification.find_one(
        Notification.id == notification_id,
        Notification.user_id == user_id
    )
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
        
    settings = await SystemSettings.find_one()
    delete_policy = settings.delete_policy if settings else "SOFT"

    if delete_policy == "HARD":
        await notification.delete()
    else:
        notification.is_deleted = True
        await notification.save()
        
    return Response(status_code=status.HTTP_204_NO_CONTENT)
