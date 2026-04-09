# backend/app/modules/payments/router.py
from typing import List, Any
from fastapi import APIRouter, Depends, HTTPException, status
from beanie import PydanticObjectId
from app.core.dependencies import RoleChecker
from app.modules.users.models import User, UserRole
from app.modules.payments.schemas import PaymentCreate, PaymentRead, InvoiceSendResponse
from app.modules.payments.service import PaymentService

router = APIRouter()

admin_checker = RoleChecker([UserRole.ADMIN])
sales_checker = RoleChecker([UserRole.SALES, UserRole.TELESALES, UserRole.ADMIN])

@router.post("/clients/{client_id}/payments/generate-qr", response_model=PaymentRead, status_code=status.HTTP_201_CREATED)
async def generate_qr(
    client_id: PydanticObjectId,
    payment_in: PaymentCreate,
    current_user: User = Depends(sales_checker)
) -> Any:
    """
    Generate a QR code payment request for a specific client.
    Only Sales, Telesales, and Admin can run this.
    """
    service = PaymentService()
    return await service.generate_payment_qr(payment_in, current_user, client_id=client_id)

@router.post("/shops/{shop_id}/payments/generate-qr", response_model=PaymentRead, status_code=status.HTTP_201_CREATED)
async def generate_qr_from_shop(
    shop_id: PydanticObjectId,
    payment_in: PaymentCreate,
    current_user: User = Depends(sales_checker)
) -> Any:
    """
    Generate a QR code payment request directly from a Shop.
    This will automatically convert the Shop to a Client.
    Only Sales, Telesales, and Admin can run this.
    """
    service = PaymentService()
    return await service.generate_payment_qr(payment_in, current_user, shop_id=shop_id)

@router.patch("/payments/{payment_id}/verify", response_model=PaymentRead)
async def verify_payment(
    payment_id: PydanticObjectId,
    current_user: User = Depends(admin_checker) # Admin only
) -> Any:
    """
    Verify payment. Must be idempotent and transactional.
    Automatically assigns PM and creates invoice.
    """
    service = PaymentService()
    return await service.verify_payment(payment_id, current_user)

@router.post("/payments/{payment_id}/send-invoice-whatsapp", response_model=InvoiceSendResponse)
async def send_invoice_whatsapp(
    payment_id: PydanticObjectId,
    current_user: User = Depends(admin_checker) # Admin only
) -> Any:
    """
    Send the invoice to the client's verified WhatsApp number.
    """
    service = PaymentService()
    return await service.send_invoice_whatsapp(payment_id, current_user)
