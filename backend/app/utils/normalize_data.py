import asyncio
import motor.motor_asyncio
import dns.resolver
from bson import ObjectId
from datetime import datetime

# ── Fix for dnspython/pymongo in restricted environments ───────────────────
try:
    dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
    dns.resolver.default_resolver.nameservers = ['8.8.8.8']
except: pass

MONGODB_URI = "mongodb+srv://HK_Digiverse:HK%40Digiverse%40123@cluster0.lcbyqbq.mongodb.net/aisetu_srm?retryWrites=true&w=majority&appName=Cluster0"
DB_NAME = "aisetu_db"

async def normalize():
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
    db = client[DB_NAME]
    
    print("Forcing types on all collections...")

    # Force entity_id to string in activity_logs
    res = await db["activity_logs"].update_many(
        {"entity_id": {"$exists": True}},
        [{"$set": {"entity_id": {"$toString": "$entity_id"}}}]
    )
    print(f"  activity_logs.entity_id strings: {res.modified_count}")

    # Force applied_slab to string in incentive_slips
    res = await db["incentive_slips"].update_many(
        {"applied_slab": {"$exists": True, "$ne": None}},
        [{"$set": {"applied_slab": {"$toString": "$applied_slab"}}}]
    )
    print(f"  incentive_slips.applied_slab strings: {res.modified_count}")

    # Ensure confirmed_by is ObjectId or NULL in salary_slips
    # First convert strings to ObjectIds
    async for doc in db["salary_slips"].find({"confirmed_by": {"$type": "string", "$regex": "^[0-9a-fA-F]{24}$"}}):
        await db["salary_slips"].update_one({"_id": doc["_id"]}, {"$set": {"confirmed_by": ObjectId(doc["confirmed_by"])}})
    
    # Nullify others that are not ObjectId (excluding null/missing)
    res = await db["salary_slips"].update_many(
        {"confirmed_by": {"$exists": True, "$ne": None, "$not": {"$type": "objectId"}}},
        {"$set": {"confirmed_by": None}}
    )
    print(f"  salary_slips.confirmed_by cleaned: {res.modified_count}")

    # Ensure user_id/approved_by are ObjectIds in leave_records
    async for doc in db["leave_records"].find({"approved_by": {"$type": "string", "$regex": "^[0-9a-fA-F]{24}$"}}):
        await db["leave_records"].update_one({"_id": doc["_id"]}, {"$set": {"approved_by": ObjectId(doc["approved_by"])}})
    res = await db["leave_records"].update_many(
        {"approved_by": {"$exists": True, "$ne": None, "$not": {"$type": "objectId"}}},
        {"$set": {"approved_by": None}}
    )
    print(f"  leave_records.approved_by cleaned: {res.modified_count}")

    print("Final normalization complete.")

if __name__ == "__main__":
    asyncio.run(normalize())
