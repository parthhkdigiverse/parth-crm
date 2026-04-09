# backend/app/modules/payments/service.py
from beanie import PydanticObjectId
from beanie.operators import In
from fastapi import HTTPException, status
from datetime import datetime, UTC
from typing import Optional
import uuid
import re

from app.modules.payments.models import Payment, PaymentStatus
from app.modules.payments.schemas import PaymentCreate
from app.modules.clients.models import Client, ClientPMHistory
from app.modules.users.models import User, UserRole

class PaymentService:
    def __init__(self):
        # No db session needed in Beanie!
        pass

    async def generate_payment_qr(self, payment_in: PaymentCreate, current_user: User, client_id: Optional[PydanticObjectId] = None, shop_id: Optional[PydanticObjectId] = None):
        """Generates a QR code for UPI payment and auto-registers a Client if a Shop ID is provided."""
        if not client_id and not shop_id:
            raise HTTPException(status_code=400, detail="Must provide client_id or shop_id")
            
        client = None
        if client_id:
            client = await Client.get(client_id)
            if not client:
                raise HTTPException(status_code=404, detail="Client not found")
        elif shop_id:
            from app.modules.shops.models import Shop
            shop = await Shop.get(shop_id)
            if not shop:
                raise HTTPException(status_code=404, detail="Shop not found")
            
            # Auto-create Client from Shop details (Manual Sequential Creation)
            phone_val = shop.phone or "0000000000"
            digits = re.sub(r"\D", "", phone_val).zfill(10)
                
            email_val = shop.email if shop.email else f"shop_{str(shop_id)}_{uuid.uuid4().hex[:6]}@srm.demo"
            
            client = Client(
                name=shop.name,
                email=email_val,
                phone=digits,
                organization=shop.name,
                owner_id=current_user.id,
                status="ACTIVE"
            )
            await client.insert()
        
        # Static QR Generation Mock (using standard UPI intent format)
        payment_ref = str(uuid.uuid4())
        qr_data = f"upi://pay?pa=business@upi&pn=SRM&am={payment_in.amount}&tr={payment_ref}"
        
        payment = Payment(
            client_id=client.id,
            amount=payment_in.amount,
            qr_code_data=qr_data,
            generated_by_id=current_user.id,
            transaction_ref=payment_ref
        )
        await payment.insert()
        return payment

    # TODO: Implement MongoDB transactions for financial safety
    async def verify_payment(self, payment_id: PydanticObjectId, current_user: User):
        """Verifies a payment, updates client status, and performs load-balanced PM assignment."""
        payment = await Payment.get(payment_id)
        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")
            
        # 1. Idempotency Check
        if payment.status == PaymentStatus.VERIFIED:
            return payment
            
        # 2. Update Payment State
        payment.status = PaymentStatus.VERIFIED
        payment.verified_by_id = current_user.id
        payment.verified_at = datetime.now(UTC)

        # 3. Handle Client Side Effects
        client = await Client.get(payment.client_id)
        if not client:
            raise HTTPException(status_code=500, detail="Associated Client not found")
        
        # Auto-assign PM if missing
        if not client.pm_id:
            # Manual load balancing logic (Beanie find + sequential lookups)
            active_pms = await User.find(
                In(User.role, [UserRole.PROJECT_MANAGER, UserRole.PROJECT_MANAGER_AND_SALES]), 
                User.is_active == True,
                User.is_deleted == False
            ).to_list()
            
            min_load = float('inf')
            best_pm = None
            for pm in active_pms:
                # Count current active clients for this PM
                cnt = await Client.find(Client.pm_id == pm.id, Client.is_active == True).count()
                if cnt < min_load:
                    min_load = cnt
                    best_pm = pm
            
            if best_pm:
                client.pm_id = best_pm.id
                # Record in embedded PM history list
                if not client.pm_history: client.pm_history = []
                client.pm_history.append(ClientPMHistory(pm_id=best_pm.id, assigned_at=datetime.now(UTC)))
        
        # Save both documents (sequential awaits, TODO: wrap in transaction)
        await payment.save()
        await client.save()
        
        return payment

    async def send_invoice_whatsapp(self, payment_id: PydanticObjectId, current_user: User):
        """Placeholder for WhatsApp API integration for invoice dispatch."""
        payment = await Payment.get(payment_id)
        if not payment or payment.status != PaymentStatus.VERIFIED:
            raise HTTPException(status_code=400, detail="Cannot send invoice for unverified payment")
            
        client = await Client.get(payment.client_id)
        if not client:
             raise HTTPException(status_code=404, detail="Client missing")
        
        # Mock WhatsApp API dispatch logic
        print(f"Sending invoice to WhatsApp for {client.name} ({client.phone}) for amount {payment.amount}")
        
        return {
            "success": True,
            "message": f"Invoice successfully triggered to WhatsApp for {client.name}."
        }
