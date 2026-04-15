# backend/app/modules/feedback/router.py
from typing import List, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from beanie import PydanticObjectId
from app.core.dependencies import RoleChecker, get_current_user
from app.modules.users.models import User, UserRole
from app.modules.feedback.schemas import FeedbackCreate, FeedbackRead
from app.modules.feedback.service import FeedbackService

router = APIRouter()

@router.get("/", response_model=List[FeedbackRead])
@router.get("", response_model=List[FeedbackRead], include_in_schema=False)
async def read_feedbacks(
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: User = Depends(get_current_user)
) -> Any:
    """List feedbacks. Role-based filtering happens in the service layer."""
    service = FeedbackService()
    return await service.get_feedbacks(current_user, skip, limit)

@router.get("/all", response_model=List[FeedbackRead])
async def get_all_feedbacks(
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: User = Depends(get_current_user)
):
    """List all feedbacks for dashboard. Global access."""
    service = FeedbackService()
    return await service.get_all_client_feedbacks(skip=skip, limit=limit)

@router.post("/public/submit", status_code=status.HTTP_201_CREATED)
async def submit_public_feedback(
    feedback_in: FeedbackCreate
) -> Any:
    """Public endpoint for clients to submit feedback via QR code."""
    service = FeedbackService()
    return await service.create_client_feedback(feedback_in)

# Role checkers
staff_access = RoleChecker([
    UserRole.ADMIN,
    UserRole.SALES,
    UserRole.TELESALES,
    UserRole.PROJECT_MANAGER,
    UserRole.PROJECT_MANAGER_AND_SALES
])

admin_access = RoleChecker([UserRole.ADMIN])

@router.post("/", response_model=FeedbackRead, status_code=status.HTTP_201_CREATED)
async def create_feedback(
    request: Request,
    feedback_in: FeedbackCreate,
    current_user: User = Depends(staff_access)
) -> Any:
    """Create a new feedback entry. Available to all staff."""
    service = FeedbackService()
    return await service.create_client_feedback(feedback_in)

@router.get("/{feedback_id}", response_model=FeedbackRead)
async def read_feedback(
    feedback_id: PydanticObjectId,
    current_user: User = Depends(staff_access)
) -> Any:
    service = FeedbackService()
    feedback = await service.get_feedback(feedback_id, current_user)
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return feedback

@router.delete("/{feedback_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feedback(
    feedback_id: PydanticObjectId,
    current_user: User = Depends(admin_access)
):
    """Delete a single feedback record. Admin only."""
    service = FeedbackService()
    await service.delete_feedback(feedback_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post("/batch-delete")
async def batch_delete_feedbacks(
    payload: dict,
    current_user: User = Depends(admin_access)
):
    """Delete multiple feedback records. Admin only."""
    ids = [PydanticObjectId(i) for i in payload.get("ids", []) if i]
    service = FeedbackService()
    await service.batch_delete_feedbacks(ids)
    return {"message": f"Successfully deleted {len(ids)} records"}
