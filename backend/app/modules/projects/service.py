# backend/app/modules/projects/service.py
from typing import Optional, List
from beanie import PydanticObjectId
from beanie.operators import In, Or, And
from fastapi import HTTPException, status, Request
from app.modules.projects.models import Project
from app.core.enums import GlobalTaskStatus
from app.modules.projects.schemas import ProjectCreate, ProjectUpdate
from app.modules.users.models import User, UserRole
from app.modules.activity_logs.models import ActionType, EntityType
from app.modules.notifications.models import Notification
from datetime import datetime, UTC

class ProjectService:
    def __init__(self):
        # No db session needed in Beanie!
        pass

    async def _populate_project_metadata(self, project: Project):
        """Asynchronously calculates project progress and fetches metadata sequentially."""
        from app.modules.issues.models import Issue
        from app.modules.clients.models import Client
        
        # Calculate progress via sequential async counts
        project.total_issues = await Issue.find(Issue.client_id == project.client_id, Issue.is_deleted == False).count()
        project.resolved_issues = await Issue.find(Issue.client_id == project.client_id, Issue.status == GlobalTaskStatus.RESOLVED, Issue.is_deleted == False).count()
        project.progress_percentage = (project.resolved_issues / project.total_issues * 100) if project.total_issues > 0 else 0.0
        
        # Populate names and contact info (Manual replacement for SQL Joins)
        if project.client_id:
            client = await Client.get(project.client_id)
            if client:
                project.client_name = client.name
                project.contact_person = client.name
                project.phone = client.phone
                project.email = client.email
                project.project_type = client.project_type
                
                # --- Silent Self-Healing: Sync Project PM with Client PM ---
                if client.pm_id and project.pm_id != client.pm_id:
                    project.pm_id = client.pm_id
                    await project.save()

        if project.pm_id:
            pm = await User.get(project.pm_id)
            if pm:
                project.pm_name = pm.name or pm.email
        
        return project

    async def get_projects(self, skip: int = 0, limit: Optional[int] = None, pm_id: Optional[PydanticObjectId] = None) -> List[Project]:
        """Fetches a list of projects with enrichment."""
        q = Project.find(Project.is_deleted == False)
        if pm_id:
            q = q.find(Project.pm_id == pm_id)
        
        # Build query — only apply limit when explicitly provided
        query = q.sort("-created_at").skip(skip)
        if limit is not None:
            query = query.limit(limit)
        projects = await query.to_list()
        for p in projects:
            await self._populate_project_metadata(p)
        return projects

    async def get_project(self, project_id: PydanticObjectId) -> Optional[Project]:
        """Fetches a single project by ID with enrichment."""
        project = await Project.find_one(Project.id == project_id, Project.is_deleted == False)
        if project:
            await self._populate_project_metadata(project)
        return project

    async def get_least_busy_pm(self) -> Optional[PydanticObjectId]:
        """Finds the Project Manager with the lowest active project workload."""
        pm_users = await User.find(
            In(User.role, [UserRole.PROJECT_MANAGER, UserRole.PROJECT_MANAGER_AND_SALES]),
            User.is_active == True,
            User.is_deleted == False
        ).to_list()

        if not pm_users:
            return None

        pm_workloads = []
        for pm in pm_users:
            # Count projects in OPEN or IN_PROGRESS state
            workload = await Project.find(
                Project.pm_id == pm.id,
                In(Project.status, [GlobalTaskStatus.OPEN, GlobalTaskStatus.IN_PROGRESS])
            ).count()
            pm_workloads.append((pm.id, workload))

        # Return ID of PM with least projects
        pm_workloads.sort(key=lambda x: x[1])
        return pm_workloads[0][0] if pm_workloads else None

    async def create_project(self, project_in: ProjectCreate, current_user: User, request: Request):
        """Creates a new project and handles auto PM assignment."""
        project_dict = project_in.model_dump()
        
        # Automatic PM assignment if not provided
        if not project_dict.get("pm_id"):
            pm_id = await self.get_least_busy_pm()
            if pm_id:
                project_dict["pm_id"] = pm_id
            else:
                # Absolute fallback to first admin
                fallback_pm = await User.find_one(User.role == UserRole.ADMIN, User.is_active == True)
                if fallback_pm:
                    project_dict["pm_id"] = fallback_pm.id
                else:
                    raise HTTPException(status_code=400, detail="No available staff found for project assignment.")

        db_project = Project(**project_dict)
        await db_project.insert()

        # Create localized notification for the assigned PM
        if db_project.pm_id:
            try:
                await Notification(
                    user_id=db_project.pm_id,
                    title=f"[Project] New Project Assigned: {db_project.name}",
                    message=f"You have been assigned as the Project Manager for project '{db_project.name}'."
                ).insert()
            except Exception as e:
                print(f"Error creating project assignment notification: {e}")

        return db_project

    async def update_project(self, project_id: PydanticObjectId, project_in: ProjectUpdate, current_user: User, request: Request):
        """Updates project details and logs the activity."""
        project = await Project.get(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        update_data = project_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(project, field, value)

        await project.save()
        return project

    async def delete_project(self, project_id: PydanticObjectId, current_user: User, request: Request):
        """Soft deletes a project from the system."""
        project = await Project.get(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        project.is_deleted = True
        await project.save()
        return {"detail": "Project successfully deleted"}
