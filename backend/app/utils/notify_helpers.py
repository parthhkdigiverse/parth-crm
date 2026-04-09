# backend/app/utils/notify_helpers.py
"""
Centralized notification helper for the CRM (Beanie/MongoDB version).

Usage:
    from app.utils.notify_helpers import create_notification, notify_admins, notify_group

    await create_notification(user_id=target_user_id, title="📅 Meeting Scheduled",
                              message="...", actor_id=current_user.id)
"""
from typing import Optional, List, Union
from beanie import PydanticObjectId
from app.modules.notifications.models import Notification
from app.modules.users.models import User, UserRole


# ─── Role → assigned_group mapping ──────────────────────────────────────────

_GROUP_ROLE_MAP: dict[str, list[str]] = {
    "GROUP_ALL":      ["ADMIN", "SALES", "TELESALES", "PROJECT_MANAGER", "PROJECT_MANAGER_AND_SALES"],
    "GROUP_SALES":    ["SALES", "TELESALES"],
    "GROUP_PM":       ["PROJECT_MANAGER", "PROJECT_MANAGER_AND_SALES"],
    "GROUP_PM_SALES": ["PROJECT_MANAGER", "PROJECT_MANAGER_AND_SALES", "SALES", "TELESALES"],
}


async def create_notification(
    user_id: Union[str, PydanticObjectId],
    title: str,
    message: str,
    actor_id: Optional[Union[str, PydanticObjectId]] = None,
) -> Optional[Notification]:
    """
    Create a single in-app notification for user_id.

    Args:
        user_id:  Recipient's user ID
        title:    Notification title (emoji prefix encouraged)
        message:  Notification body text
        actor_id: The user who triggered the event.
                  If actor_id == user_id the notification is SKIPPED (anti-spam).

    Returns:
        The created Notification ORM instance, or None if skipped.
    """
    if not user_id:
        return None
        
    # Standardize IDs to string for comparison
    uid_str = str(user_id)
    actor_str = str(actor_id) if actor_id else None

    # Anti-spam: never notify someone about their own action
    if actor_str and actor_str == uid_str:
        return None

    notif = Notification(
        user_id=PydanticObjectId(uid_str),
        title=title,
        message=message,
        is_read=False,
    )
    await notif.insert()
    return notif


async def notify_many(
    user_ids: List[Union[str, PydanticObjectId]],
    title: str,
    message: str,
    actor_id: Optional[Union[str, PydanticObjectId]] = None,
) -> None:
    """
    Batch-create notifications for a list of user IDs.
    Deduplicates the list and applies the anti-spam filter.
    """
    seen: set[str] = set()
    for uid in user_ids:
        if not uid:
            continue
            
        uid_str = str(uid)
        if uid_str not in seen:
            seen.add(uid_str)
            await create_notification(uid_str, title, message, actor_id=actor_id)


async def notify_admins(
    title: str,
    message: str,
    actor_id: Optional[Union[str, PydanticObjectId]] = None,
) -> None:
    """
    Notify all active ADMIN users.
    """
    admins = await User.find(User.role == UserRole.ADMIN, User.is_active == True).to_list()
    for admin in admins:
        await create_notification(admin.id, title, message, actor_id=actor_id)


async def notify_group(
    assigned_group: str,
    title: str,
    message: str,
    actor_id: Optional[Union[str, PydanticObjectId]] = None,
) -> None:
    """
    Notify all active users whose role maps to assigned_group.
    Supports: GROUP_ALL, GROUP_SALES, GROUP_PM, GROUP_PM_SALES.
    """
    role_names = _GROUP_ROLE_MAP.get(assigned_group, [])
    if not role_names:
        return

    # Map role names to UserRole enums
    roles = [UserRole(r) for r in role_names]
    
    users = await User.find(
        {"role": {"$in": roles}, "is_active": True}
    ).to_list()
    
    for user in users:
        await create_notification(user.id, title, message, actor_id=actor_id)


async def notify_client_stakeholders(
    client,      # Client ORM instance
    title: str,
    message: str,
    actor_id: Optional[Union[str, PydanticObjectId]] = None,
    extra_ids: Optional[List[Union[str, PydanticObjectId]]] = None,
) -> None:
    """
    Notify all relevant stakeholders for a client:
        - pm_id           (Project Manager)
        - owner_id        (Sales rep / deal owner)
        - referred_by_id  (Onboarding/referral rep)

    Deduplicates and applies anti-spam filter.
    """
    candidate_ids = [
        getattr(client, "pm_id", None),
        getattr(client, "owner_id", None),
        getattr(client, "referred_by_id", None),
    ]
    if extra_ids:
        candidate_ids.extend(extra_ids)

    await notify_many([uid for uid in candidate_ids if uid], title, message, actor_id=actor_id)
