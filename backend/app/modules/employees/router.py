# backend/app/modules/employees/router.py
"""
Employees router — thin alias over /users/ for backward-compatibility.
The 'employees' concept was merged into 'users'; this router keeps the
/employees/* endpoints alive so the frontend doesn't 404.
"""
from datetime import date as dt_date
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status, Response
from beanie import PydanticObjectId

from app.core.dependencies import RoleChecker, get_current_active_user
from app.modules.users.models import User, UserRole
from app.modules.users.schemas import UserRead, UserCreate, EmployeeUpdate

router = APIRouter()

admin_checker = RoleChecker([UserRole.ADMIN])


@router.get("/", response_model=List[UserRead])
async def list_employees(
    limit: Optional[int] = Query(None),
    department: Optional[str] = Query(None),
    role: Optional[UserRole] = Query(None),
    is_active: Optional[bool] = Query(None),
    q: Optional[str] = Query(None),
    start_date: Optional[dt_date] = Query(None),
    end_date: Optional[dt_date] = Query(None),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """List employees with optional filters."""
    if current_user.role == UserRole.CLIENT:
        return []

    query_obj = User.find(User.is_deleted == False)
    
    if department:
        import re
        pattern = re.compile(f".*{re.escape(department)}.*", re.IGNORECASE)
        query_obj = query_obj.find({"department": pattern})
    if role:
        query_obj = query_obj.find(User.role == role)
    if is_active is not None:
        query_obj = query_obj.find(User.is_active == is_active)
    if q:
        import re
        pattern = re.compile(f".*{re.escape(q)}.*", re.IGNORECASE)
        query_obj = query_obj.find({
            "$or": [
                {"name": pattern},
                {"email": pattern},
                {"employee_code": pattern}
            ]
        })
    if start_date:
        query_obj = query_obj.find(User.joining_date >= start_date)
    if end_date:
        query_obj = query_obj.find(User.joining_date <= end_date)
        
    if limit:
        query_obj = query_obj.limit(limit)
    
    results = await query_obj.to_list()
    
    # If not admin, mask sensitive data for others
    if current_user.role != UserRole.ADMIN:
        for u in results:
            if u.id != current_user.id:
                u.base_salary = None
                u.target = None
                
    return results


@router.post("/", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_employee(
    employee_in: UserCreate,
    current_user: User = Depends(admin_checker),
) -> Any:
    """Create a new user/employee (Admin only)."""
    existing = await User.find_one(User.email == employee_in.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    from app.core.security import get_password_hash
    hashed = get_password_hash(employee_in.password)

    user = User(
        email=employee_in.email,
        hashed_password=hashed,
        name=employee_in.name,
        phone=employee_in.phone,
        role=employee_in.role,
        is_active=employee_in.is_active if employee_in.is_active is not None else True,
        employee_code=employee_in.employee_code,
        joining_date=employee_in.joining_date,
        base_salary=employee_in.base_salary,
        target=employee_in.target,
        department=employee_in.department,
    )
    await user.insert()
    return user


@router.patch("/{employee_id}", response_model=UserRead)
async def update_employee(
    employee_id: PydanticObjectId,
    update_in: EmployeeUpdate,
    current_user: User = Depends(admin_checker),
) -> Any:
    """Update a user/employee profile (Admin only)."""
    user = await User.find_one(User.id == employee_id, User.is_deleted == False)
    if not user:
        raise HTTPException(status_code=404, detail="Employee not found")

    update_data = update_in.model_dump(exclude_unset=True)
    if "password" in update_data and update_data["password"]:
        from app.core.security import get_password_hash
        update_data["hashed_password"] = get_password_hash(update_data.pop("password"))
        
        from app.modules.auth.models import PasswordResetRequest
        from datetime import datetime, UTC
        pending_reqs = await PasswordResetRequest.find(PasswordResetRequest.user_id == user.id, PasswordResetRequest.status == "PENDING").to_list()
        for req in pending_reqs:
            req.status = "RESOLVED"
            req.resolved_by = current_user.id
            req.resolved_at = datetime.now(UTC)
            await req.save()
    else:
        update_data.pop("password", None)

    for field, value in update_data.items():
        setattr(user, field, value)

    await user.save()
    return user


@router.delete("/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_employee(
    employee_id: PydanticObjectId,
    current_user: User = Depends(admin_checker),
):
    """Soft-delete a user/employee (Admin only)."""
    user = await User.find_one(User.id == employee_id, User.is_deleted == False)
    if not user:
        raise HTTPException(status_code=404, detail="Employee not found")

    user.is_deleted = True
    await user.save()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
