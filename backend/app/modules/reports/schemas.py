import datetime
from typing import Optional
from pydantic import BaseModel
from app.core.base_schema import MongoBaseSchema

class DashboardStats(MongoBaseSchema):
    total_visits: int
    active_clients: int
    ongoing_projects: int
    revenue_mtd: float
    
    visits_mom_pct: float
    clients_mom_pct: float
    projects_mom_pct: float
    revenue_mom_pct: float
    
    open_issues: int
    employees_present: int
    presence_mom_pct: float
    
    # New Role-Specific Fields
    total_incentive: float = 0.0
    pending_todos: int = 0
    meetings_today: int = 0
    
    visits_chart_title: str
    visits_chart_data: dict
    revenue_by_month: dict
    visit_status_breakdown: dict
    issue_severity_breakdown: dict
    visit_outcomes_breakdown: dict
    project_status_breakdown: dict # Added new field


class EmployeePerformance(BaseModel):
    user_id: str
    id: str # For alignment with frontend usage
    name: Optional[str]
    email: str
    role: str
    total_visits: int
    total_leads: int
    success_rate: float
    total_sales: float
    total_revenue: float
    total_incentive: float
    total_projects: int
    total_open_issues: int
    target: Optional[int] = 0

class BusinessSummary(MongoBaseSchema):
    month: str
    total_revenue: float
    total_salaries: float
    total_incentives: float
    total_expenses: float
    net_profit: float
    new_clients: int
    total_visits: int
    total_issues_raised: int

class ProjectPortfolio(BaseModel):
    id: str
    fullName: Optional[str]
    name: str # Client name
    org: Optional[str] # Organization
    project: str # Project name
    priority: str
    totalAmount: float
    paidAmount: float
    outstanding: float
    lastMeeting: Optional[str]
    interactionDate: datetime.datetime
    status: str

class EmployeeActivity(BaseModel):
    date: datetime.datetime
    client: str
    type: str # Map from visit status or remarks
    status: str
