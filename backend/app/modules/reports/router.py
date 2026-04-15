# backend/app/modules/reports/router.py
from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from datetime import datetime
from typing import List, Optional, Any
from beanie import PydanticObjectId
import io

from app.modules.users.models import User, UserRole
from app.core.dependencies import RoleChecker, get_current_user
from app.modules.reports.schemas import (
    DashboardStats, EmployeePerformance, BusinessSummary, 
    ProjectPortfolio, EmployeeActivity, PerformanceNoteCreate, PerformanceNoteResponse
)
from app.modules.reports.service import ReportService

router = APIRouter()

# Allow admins, PMs and Sales staff to view dashboard/reports
dashboard_viewer = RoleChecker([
    UserRole.ADMIN,
    UserRole.SALES,
    UserRole.TELESALES,
    UserRole.PROJECT_MANAGER,
    UserRole.PROJECT_MANAGER_AND_SALES
])

@router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard_stats(
    area_id: Optional[PydanticObjectId] = Query(None),
    user_id: Optional[PydanticObjectId] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: User = Depends(dashboard_viewer)
) -> Any:
    """Get high-level dashboard statistics."""
    # Enforce own data for non-admins
    effective_user_id = user_id
    if current_user.role != UserRole.ADMIN:
        effective_user_id = current_user.id
        
    service = ReportService()
    return await service.get_dashboard_stats(
        requesting_user=current_user,
        area_id=area_id, 
        user_id=effective_user_id, 
        start_date=start_date, 
        end_date=end_date
    )

@router.get("/employees", response_model=List[EmployeePerformance])
async def get_employee_performance(
    month: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    current_user: User = Depends(dashboard_viewer)
) -> Any:
    """Get performance metrics for employees."""
    service = ReportService()
    return await service.get_employee_performance(
        requesting_user=current_user,
        month=month, 
        start_date=start_date, 
        end_date=end_date, 
        user_id=user_id
    )

@router.get("/present-employees")
async def get_present_employees(
    limit: int = Query(10),
    current_user: User = Depends(dashboard_viewer)
) -> Any:
    """Get list of employees currently marked as present/active."""
    service = ReportService()
    return await service.get_present_employees(limit)

@router.get("/final", response_model=BusinessSummary)
async def get_business_summary(
    month: Optional[str] = Query(None),
    current_user: User = Depends(dashboard_viewer)
) -> Any:
    """Get detailed business performance summary."""
    service = ReportService()
    return await service.get_business_summary(month)

@router.get("/projects", response_model=List[ProjectPortfolio])
async def get_project_portfolio(
    client_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    duration: Optional[str] = Query(None),
    current_user: User = Depends(dashboard_viewer)
) -> Any:
    """Get portfolio details for clients/projects."""
    service = ReportService()
    return await service.get_project_portfolio(
        requesting_user=current_user,
        client_id=client_id, 
        status=status, 
        duration=duration
    )

@router.get("/employees/{user_id}/activities", response_model=List[EmployeeActivity])
async def get_employee_activities(
    user_id: PydanticObjectId,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: User = Depends(dashboard_viewer)
) -> Any:
    """Get activity logs for a specific employee."""
    # RBAC: Non-admins can only see their own activities
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Not authorized to view activities for other users")

    service = ReportService()
    return await service.get_employee_activities(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date
    )

@router.get("/export")
async def export_report(
    type: str = Query(..., pattern="^(employees|final|projects|intelligence)$"),
    month: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    client_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    duration: Optional[str] = Query(None),
    current_user: User = Depends(dashboard_viewer)
) -> Response:
    """Export reports as CSV."""
    service = ReportService()
    data = []
    filename = f"report_{datetime.now().strftime('%Y%m%d%H%M')}.csv"

    if type == "employees":
        results = await service.get_employee_performance(
            requesting_user=current_user, month=month, start_date=start_date, end_date=end_date, user_id=user_id
        )
        for r in results:
            row = r if isinstance(r, dict) else (r.model_dump() if hasattr(r, 'model_dump') else r.__dict__)
            target = row.get('target', 0) or 0
            sales = row.get('total_revenue', 0) or 0
            pct = round((sales / target) * 100) if target > 0 else 0
            data.append({
                "Name": row.get('name', ''),
                "Role": row.get('role', ''),
                "Visits": row.get('total_visits', 0),
                "Leads": row.get('total_leads', 0),
                "Success Rate": f"{row.get('success_rate', 0)}%",
                "Target Achieved": f"₹{sales:,.0f}",
                "Incentive": f"₹{row.get('total_incentive', 0):,.0f}"
            })
        filename = f"employee_report_{datetime.now().strftime('%Y%m%d')}.csv"
        
    elif type == "projects":
        results = await service.get_project_portfolio(
            requesting_user=current_user, client_id=client_id, status=status, duration=duration
        )
        for r in results:
            row = r if isinstance(r, dict) else (r.model_dump() if hasattr(r, 'model_dump') else r.__dict__)
            data.append({
                "Project": row.get('title', ''),
                "Client": row.get('client_name', ''),
                "Status": row.get('status', ''),
                "Assigned PM": row.get('pm_name', ''),
                "Start Date": row.get('start_date', ''),
                "Collection Rate": f"{row.get('collection_rate', 0)}%"
            })
        filename = f"client_portfolio_{datetime.now().strftime('%Y%m%d')}.csv"
        
    elif type == "final":
        results = await service.get_business_summary(month)
        row = results if isinstance(results, dict) else (results.model_dump() if hasattr(results, 'model_dump') else results.__dict__)
        data.append(row)
        filename = f"business_summary_{datetime.now().strftime('%Y%m%d')}.csv"
    
    elif type == "intelligence":
        # New Intelligence Report (Modernized)
        results = await service.get_client_intelligence_report(month)
        for r in results:
            row = r if isinstance(r, dict) else (r.model_dump() if hasattr(r, 'model_dump') else r.__dict__)
            data.append({
                "Business Name": row.get('business_display_name', ''),
                "Client": row.get('client_name', ''),
                "Health Status": row.get('health_score', ''),
                "Total Issues": row.get('issue_count', 0),
                "Meetings Held": row.get('meeting_count', 0),
                "Current Stage": row.get('pipeline_stage', '')
            })
        filename = f"client_intelligence_{datetime.now().strftime('%Y%m%d')}.csv"

    csv_content = await service.generate_csv_response(data)
    
    # Add BOM for Excel compatibility
    bom = "\uFEFF"
    full_content = bom + csv_content
    
    return Response(
        content=full_content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
            "Pragma": "no-cache"
        }
    )

@router.post("/employees/{user_id}/notes", response_model=PerformanceNoteResponse)
async def save_performance_note(
    user_id: PydanticObjectId,
    note: PerformanceNoteCreate,
    current_user: User = Depends(dashboard_viewer)
) -> Any:
    """Save a new performance note for an employee (Admin only)."""
    if current_user.role != UserRole.ADMIN:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Only admins can save performance notes")
        
    service = ReportService()
    return await service.save_performance_note(user_id, current_user, note.content)

@router.get("/employees/{user_id}/notes", response_model=List[PerformanceNoteResponse])
async def get_performance_notes(
    user_id: PydanticObjectId,
    current_user: User = Depends(dashboard_viewer)
) -> Any:
    """Get history of performance notes for an employee."""
    # RBAC: Employees can only see their own notes
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Not authorized to view notes for other users")
        
    service = ReportService()
    return await service.get_performance_notes(str(user_id))

@router.delete("/employees/notes/{id}")
async def delete_performance_note(
    id: PydanticObjectId,
    current_user: User = Depends(dashboard_viewer)
) -> Any:
    """Delete a performance note (Admin only)."""
    if current_user.role != UserRole.ADMIN:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Only admins can delete notes")
        
    service = ReportService()
    success = await service.delete_performance_note(str(id))
    if not success:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Note not found")
        
    return {"message": "Note deleted successfully"}
