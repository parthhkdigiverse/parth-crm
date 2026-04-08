import asyncio
import motor.motor_asyncio
import dns.resolver

try:
    dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
    dns.resolver.default_resolver.nameservers = ['8.8.8.8']
except: pass

async def f():
    client = motor.motor_asyncio.AsyncIOMotorClient('mongodb+srv://HK_Digiverse:HK%40Digiverse%40123@cluster0.lcbyqbq.mongodb.net/aisetu_srm?retryWrites=true&w=majority&appName=Cluster0')
    db = client['aisetu_srm']
    
    # 1. Fix user names
    coll = db['users']
    async for u in coll.find({"name": {"$in": [None, ""]}}):
        new_name = u.get("email", "Employee").split("@")[0].capitalize()
        await coll.update_one({"_id": u["_id"]}, {"$set": {"name": new_name}})
        print(f"Fixed user name for {u.get('email')}")

    # 2. Fix ActivityLog user_id 0
    # Actually, we relaxed the model/schema to Any, but let's nullify them just in case
    res = await db["activity_logs"].update_many({"user_id": 0}, {"$set": {"user_id": None}})
    print(f"Nullified {res.modified_count} invalid user IDs in activity_logs")

if __name__ == "__main__":
    asyncio.run(f())
