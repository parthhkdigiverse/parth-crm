"""Debug script: check slip user_id vs actual users in DB."""
import asyncio
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
import os, sys

# Load env
sys.path.insert(0, os.path.dirname(__file__))

SLIP_ID = "69cb65e25028f083590c1cf5"

async def main():
    from app.core.database import init_db
    from app.modules.salary.models import SalarySlip
    from app.modules.users.models import User
    import beanie

    # init motor client same way app does
    from app.core.config import settings
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.DB_NAME]
    await beanie.init_beanie(database=db, document_models=[SalarySlip, User])

    slip = await SalarySlip.get(ObjectId(SLIP_ID))
    if not slip:
        print("❌ Slip not found at all!")
        return

    print(f"✅ Slip found. user_id = {slip.user_id!r}  (type: {type(slip.user_id).__name__})")

    # Try raw pymongo lookup
    raw = await db["srm_users"].find_one({"_id": ObjectId(str(slip.user_id))})
    print(f"Raw pymongo lookup: {raw}")

    # List first 5 users
    print("\nFirst 5 users in srm_users:")
    async for u in db["srm_users"].find({}, {"_id": 1, "name": 1, "email": 1}).limit(5):
        print("  ", u)

asyncio.run(main())
