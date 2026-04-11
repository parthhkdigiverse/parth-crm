# backend/app/modules/issues/service.py
from typing import Optional, List, Any
from beanie import PydanticObjectId
from beanie.operators import In, Or, And
from fastapi import HTTPException, status, Request, BackgroundTasks
from app.modules.issues.models import Issue
from app.modules.issues.schemas import IssueCreate, IssueUpdate
from app.modules.users.models import User, UserRole
from app.modules.clients.models import Client
from app.modules.notifications.service import EmailService
from app.modules.notifications.models import Notification
from app.utils.notify_helpers import create_notification, notify_admins, notify_group
from datetime import datetime, UTC

class IssueService:
    def __init__(self):
        # No db session needed in Beanie!
        pass

    async def get_issue(self, issue_id: PydanticObjectId) -> Optional[Issue]:
        return await Issue.find_one(Issue.id == issue_id, Issue.is_deleted == False)

    async def get_all_issues(
        self,
        skip: int = 0,
        limit: Optional[int] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        client_id: Optional[PydanticObjectId] = None,
        assigned_to_id: Optional[PydanticObjectId] = None,
        pm_id: Optional[PydanticObjectId] = None,
        current_user: Optional[User] = None
    ) -> List[Any]:
        try:
            q = Issue.find(Issue.is_deleted == False)
            
            if pm_id:
                # Manual join replacement: fetch clients managed by this PM
                raw_pm_clients = await Client.get_pymongo_collection().distinct("_id", {"pm_id": PydanticObjectId(pm_id)})
                pm_clients = [PydanticObjectId(rid) for rid in raw_pm_clients if rid]
                q = q.find(In(Issue.client_id, pm_clients))

            if current_user and current_user.role != UserRole.ADMIN:
                # Scoped logic for non-admins
                allowed_groups = ["GROUP_ALL"]
                role_val = current_user.role.value
                if role_val in ["SALES", "TELESALES"]: 
                    allowed_groups.extend(["GROUP_SALES", "GROUP_PM_SALES"])
                elif role_val == "PROJECT_MANAGER": 
                    allowed_groups.extend(["GROUP_PM", "GROUP_PM_SALES"])
                elif role_val == "PROJECT_MANAGER_AND_SALES": 
                    allowed_groups.extend(["GROUP_SALES", "GROUP_PM", "GROUP_PM_SALES"])
                
                # Fetch clients related to user for ownership cross-reference
                raw_user_client_ids = await Client.get_pymongo_collection().distinct("_id", {
                    "$or": [
                        {"owner_id": current_user.id},
                        {"pm_id": current_user.id},
                        {"referred_by_id": current_user.id}
                    ],
                    "is_deleted": False
                })
                user_client_ids = [PydanticObjectId(rid) for rid in raw_user_client_ids if rid]
                
                q = q.find(Or(
                    Issue.assigned_to_id == current_user.id,
                    Issue.reporter_id == current_user.id,
                    In(Issue.client_id, user_client_ids),
                    In(Issue.assigned_group, allowed_groups)
                ))

            # Applied filters
            if status:
                if ',' in status:
                    status_list = [s.strip() for s in status.split(',')]
                    q = q.find(In(Issue.status, status_list))
                else:
                    q = q.find(Issue.status == status)
            
            if severity: q = q.find(Issue.severity == severity)
            if client_id: q = q.find(Issue.client_id == client_id)
            if assigned_to_id: q = q.find(Issue.assigned_to_id == assigned_to_id)

            query = q.sort("-created_at").skip(skip)
            if limit is not None:
                query = query.limit(limit)
            issues = await query.to_list()
            
            # Enrich properties: one client fetch gives us client name + client's PM
            enriched_issues = []
            for issue in issues:
                # Convert to dict for enrichment
                item = issue.model_dump()
                item["id"] = str(issue.id)

                # Fetch the linked client to get name and PM
                client_obj = None
                try:
                    if issue.client_id:
                        client_obj = await Client.get(issue.client_id)
                except Exception:
                    pass

                if client_obj:
                    item["client_name"] = client_obj.name
                    item["project_name"] = client_obj.name  # backward compat
                    # PM = the client's assigned PM (auto-assigned on client create/edit)
                    try:
                        if client_obj.pm_id:
                            # Use cached pm_name on client first to avoid extra DB call
                            if client_obj.pm_name:
                                item["pm_name"] = client_obj.pm_name
                            else:
                                pm_user = await User.get(client_obj.pm_id)
                                item["pm_name"] = pm_user.name if pm_user else "Unassigned"
                        else:
                            item["pm_name"] = "Unassigned"
                    except Exception:
                        item["pm_name"] = "Unassigned"
                else:
                    item["client_name"] = "Unknown Client"
                    item["project_name"] = "Unknown Client"
                    item["pm_name"] = "Unassigned"

                # Resolve reporter name
                try:
                    if issue.reporter_id:
                        reporter = await User.get(issue.reporter_id)
                        item["reporter_name"] = reporter.name if reporter else "System"
                    else:
                        item["reporter_name"] = "System"
                except Exception:
                    item["reporter_name"] = "System"

                enriched_issues.append(item)

            return enriched_issues
        except Exception as e:
            print(f"Error fetching issues: {e}")
            return []

    async def create_issue(self, issue_in: IssueCreate, client_id: PydanticObjectId, current_user: User, background_tasks: BackgroundTasks = None):
        client = await Client.get(client_id)
        if not client: 
            raise HTTPException(status_code=404, detail="Client not found")

        issue_dict = issue_in.model_dump(exclude_none=True)
        assigned_to_id = issue_dict.get("assigned_to_id")
        assigned_group = issue_dict.get("assigned_group")
        
        # Priority: Requested handler -> Client's primary PM -> None
        target_handler_id = assigned_to_id or client.pm_id

        db_issue = Issue(
            **issue_dict,
            client_id=client_id,
            reporter_id=current_user.id,
            assigned_to_id=target_handler_id if not assigned_group else None,
            assigned_group=assigned_group
        )

        await db_issue.insert()

        # -- In-App Notifications --
        try:
            severity = db_issue.severity or "MEDIUM"
            is_critical = severity == "HIGH"
            notif_title = f"[{'Critical' if is_critical else 'Issue'}] {'⚠️ ' if is_critical else ''}New Issue Reported"
            notif_msg = f"A {severity} issue '{db_issue.title}' was reported for '{client.name}' by {current_user.name or current_user.email}."
            
            if assigned_group:
                await notify_group(assigned_group, notif_title, notif_msg, actor_id=current_user.id)
            elif target_handler_id:
                await create_notification(target_handler_id, notif_title, notif_msg, actor_id=current_user.id)
            
            await notify_admins(notif_title, notif_msg, actor_id=current_user.id)
        except Exception as e: 
            print(f"In-app notification failed: {e}")

        # -- Email Notification --
        if client.pm_id:
            pm = await User.get(client.pm_id)
            if pm and pm.email:
                svc = EmailService()
                if background_tasks:
                   background_tasks.add_task(svc.send_issue_notification, pm.email, pm.name, client.name, db_issue.title, db_issue.description, current_user.role)
                else:
                   await svc.send_issue_notification(pm.email, pm.name, client.name, db_issue.title, db_issue.description, current_user.role)

        return db_issue

    async def update_issue(self, issue_id: PydanticObjectId, issue_update: IssueUpdate, current_user: User):
        db_issue = await self.get_issue(issue_id)
        if not db_issue: 
            raise HTTPException(status_code=404, detail="Issue not found")

        update_data = issue_update.model_dump(exclude_unset=True)
        # Remarks mandatory for status change
        if "status" in update_data and not update_data.get("remarks"):
            raise HTTPException(status_code=400, detail="Remarks are compulsory when updating an issue status")

        for key, value in update_data.items():
            setattr(db_issue, key, value)
        
        await db_issue.save()
        
        # Notify reporter on status change
        if "status" in update_data and db_issue.reporter_id:
             await create_notification(db_issue.reporter_id, "[Issue] 🔄 Issue Status Updated", f"Issue '{db_issue.title}' status changed to '{db_issue.status}' by {current_user.name or current_user.email}.", actor_id=current_user.id)
        
        return db_issue

    async def delete_issue(self, issue_id: PydanticObjectId, current_user: User):
        db_issue = await Issue.get(issue_id)
        if not db_issue: 
            raise HTTPException(status_code=404, detail="Issue not found")
        
        db_issue.is_deleted = True
        await db_issue.save()
        return {"detail": "Issue successfully deleted"}

    async def get_all_issues_for_user(
        self,
        current_user: User,
        skip: int = 0,
        limit: Optional[int] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        client_id: Optional[PydanticObjectId] = None,
        assigned_to_id: Optional[PydanticObjectId] = None,
        **kwargs
    ) -> List[Issue]:
        """Returns issues assigned to or created by the user, with optional filters."""
        try:
            q = Issue.find(
                And(
                    Issue.is_deleted == False,
                    Or(
                        Issue.assigned_to_id == current_user.id,
                        Issue.reporter_id == current_user.id
                    )
                )
            )
            
            # Apply optional filters passed by router
            if status: q = q.find(Issue.status == status)
            if severity: q = q.find(Issue.severity == severity)
            if client_id: q = q.find(Issue.client_id == client_id)
            if assigned_to_id: q = q.find(Issue.assigned_to_id == assigned_to_id)
            
            query = q.sort("-created_at").skip(skip)
            if limit is not None:
                query = query.limit(limit)
            return await query.to_list()
        except Exception as e:
            print(f"Error fetching user issues: {e}")
            return []
