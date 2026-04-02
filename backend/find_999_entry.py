
import asyncio
import motor.motor_asyncio
from beanie import init_beanie
from app.modules.billing.models import Bill
from app.modules.settings.models import AppSetting
from app.modules.users.models import User
from app.core.config import settings
import datetime

async def test():
    # 1. Initialize Beanie
    client = motor.motor_asyncio.AsyncIOMotorClient(settings.MONGODB_URI)
    client.append_metadata = lambda *args, **kwargs: None
    await init_beanie(database=client["aisetu_db"], document_models=[Bill, AppSetting, User])
    
    # 2. Check website_payment
    website_coll = Bill.get_pymongo_collection().database["website_payment"]
    prefix = "Inv"
    year = 2026
    regex = f"^{prefix}/{year}/"
    
    possible_fields = ["invoice_number", "invoice_no", "invoice_string"]
    or_filters = [{f: {"$regex": regex}} for f in possible_fields]
    
    # Find the document that matches and has the highest value
    cursor = website_coll.find(
        {"$and": [{"status": {"$in": ["succeeded", "SUCCESS", "PAID"]}}, {"$or": or_filters}]}
    ).sort([("_id", -1)])
    
    print(f"Searching for invoices in website_payment for {year}...")
    found_any = False
    async for doc in cursor:
        found_any = True
        for f in possible_fields:
            val = doc.get(f)
            if val and isinstance(val, str) and "/" in val:
                try:
                    parts = val.split("/")
                    if len(parts) == 3:
                        seq = int(parts[2])
                        if seq >= 900: # Show high ones
                            print(f"Document ID: {doc['_id']}")
                            print(f"Status: {doc.get('status')}")
                            print(f"Field '{f}': {val}")
                            print("-" * 20)
                except (ValueError, IndexError):
                    continue

    if not found_any:
        print("No matching documents found in website_payment.")

if __name__ == "__main__":
    asyncio.run(test())
