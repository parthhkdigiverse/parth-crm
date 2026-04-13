import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

async def test_billing_logic():
    from app.modules.billing.service import BillingService
    from app.modules.billing.models import Bill
    from app.modules.shops.models import Shop
    from app.modules.users.models import User, UserRole
    from app.core.enums import MasterPipelineStage
    from beanie import init_beanie
    from motor.motor_asyncio import AsyncIOMotorClient
    from app.core.config import settings

    # Init DB
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    await init_beanie(database=client.get_database(), document_models=[Bill, Shop, User])

    # 1. Setup mock shop
    shop = Shop(name="Test Shop", pipeline_stage=MasterPipelineStage.DELIVERY)
    await shop.insert()
    print(f"Created Shop: {shop.id}, Stage: {shop.pipeline_stage}")

    # 2. Setup mock user
    user = await User.find_one(User.role == UserRole.ADMIN)
    if not user:
        user = User(name="Admin", email="admin@test.com", role=UserRole.ADMIN, hashed_password="...")
        await user.insert()

    # 3. Test stage advancement in create_invoice
    service = BillingService()
    from app.modules.billing.schemas import BillCreate
    bill_in = BillCreate(
        shop_id=shop.id,
        invoice_client_name="Test Client",
        invoice_client_phone="1234567890",
        amount=5000,
        payment_type="CASH",
        gst_type="WITHOUT_GST",
        service_description="Test Service",
        billing_month="April 2026"
    )
    
    bill = await service.create_invoice(bill_in, user)
    print(f"Created Bill: {bill.id}, Status: {bill.invoice_status}")
    
    # Reload shop
    shop = await Shop.get(shop.id)
    print(f"Shop stage after invoice: {shop.pipeline_stage}")
    assert shop.pipeline_stage == MasterPipelineStage.MAINTENANCE
    
    # 4. Test Archiving
    await service.archive_invoice(bill.id, user)
    shop = await Shop.get(shop.id)
    print(f"Shop archived after bill archive: {shop.is_archived}")
    assert shop.is_archived is True
    
    # 5. Test Refund
    # Unarchive first
    shop.is_archived = False
    await shop.save()
    
    await service.refund_invoice(bill.id, user)
    shop = await Shop.get(shop.id)
    print(f"Shop archived after refund: {shop.is_archived}")
    assert shop.is_archived is True

    # Cleanup
    await bill.delete()
    await shop.delete()
    print("Test passed!")

if __name__ == "__main__":
    asyncio.run(test_billing_logic())
