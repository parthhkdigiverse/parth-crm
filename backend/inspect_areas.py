import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from app.core.config import settings
from app.modules.areas.models import Area
from app.modules.shops.models import Shop
from app.modules.users.models import User
from app.modules.areas.service import AreaService

async def inspect():
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    await init_beanie(database=client.aisetu_srm, document_models=[Area, Shop, User])
    
    admin_user = await User.find_one(User.role == "ADMIN")
    
    find_query = Area.find(Area.is_archived != True)
    admin_areas = await find_query.to_list()
    print("find_query raw length using != True:", len(admin_areas))
    
    # Check shop counts for an area
    if admin_areas:
        area = admin_areas[0]
        shops_count = await Shop.find(Shop.area_id == area.id, Shop.is_deleted != True, Shop.is_archived != True).count()
        print("shops_count using != True:", shops_count)

if __name__ == "__main__":
    asyncio.run(inspect())
