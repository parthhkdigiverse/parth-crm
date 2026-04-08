import asyncio
from fastapi.testclient import TestClient
import motor.motor_asyncio
import dns.resolver

try:
    dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
    dns.resolver.default_resolver.nameservers = ['8.8.8.8']
except: pass

from app.main import app
from app.core.dependencies import get_current_active_user
from app.modules.users.models import User, UserRole
from beanie import init_beanie
from app.main import DOCUMENT_MODELS

# Override the auth dependency to mock a logged-in admin
async def mock_get_current_active_user():
    # We will get a user from DB manually to pass validation
    client = motor.motor_asyncio.AsyncIOMotorClient('mongodb+srv://HK_Digiverse:HK%40Digiverse%40123@cluster0.lcbyqbq.mongodb.net/aisetu_srm?retryWrites=true&w=majority&appName=Cluster0')
    await init_beanie(database=client['aisetu_srm'], document_models=DOCUMENT_MODELS)
    user = await User.find_one(User.role == UserRole.ADMIN)
    return user

async def run_tests():
    # Initialize DB for the script
    client = motor.motor_asyncio.AsyncIOMotorClient('mongodb+srv://HK_Digiverse:HK%40Digiverse%40123@cluster0.lcbyqbq.mongodb.net/aisetu_srm?retryWrites=true&w=majority&appName=Cluster0')
    await init_beanie(database=client['aisetu_srm'], document_models=DOCUMENT_MODELS)
    admin_user = await User.find_one(User.role == UserRole.ADMIN)
    
    app.dependency_overrides[get_current_active_user] = lambda: admin_user

    # Initialize TestClient
    with TestClient(app) as client:
        print("\n--- Testing Activity Logs ---")
        response = client.get("/api/activity-logs/?limit=10")
        print(f"Status: {response.status_code}")
        if response.status_code != 200:
            print(f"Error: {response.json()}")
        else:
            print(f"Returned Logs: {len(response.json())}")

        print("\n--- Testing Attendance Summary ---")
        response = client.get("/api/attendance/summary?start_date=2024-03-01&end_date=2024-03-31")
        print(f"Status: {response.status_code}")
        if response.status_code != 200:
            print(f"Error: {response.json()}")
        else:
            print(f"Summary total hours: {response.json().get('total_hours')}")

        print("\n--- Testing Projects ---")
        response = client.get("/api/projects/")
        print(f"Status: {response.status_code}")
        if response.status_code != 200:
            print(f"Error: {response.json()}")

        print("\n--- Testing Employees ---")
        response = client.get("/api/users/")
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            names = [u.get("name") for u in data[:5]]
            print(f"Sample Names: {names}")
        else:
            print(f"Error: {response.json()}")

if __name__ == "__main__":
    asyncio.run(run_tests())
