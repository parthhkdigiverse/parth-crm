# backend/scripts/reset_admin.py
import asyncio
import sys
import os

# Ensure project root and backend are in path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, ".."))
root_dir = os.path.dirname(backend_dir)

# backend_dir must come BEFORE root_dir so 'app' resolves to the package, not app.py
if root_dir not in sys.path:
    sys.path.append(root_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import motor.motor_asyncio
import dns.resolver
from beanie import init_beanie
from app.core.config import settings
from app.modules.users.models import User, UserRole
from app.core.security import get_password_hash

# DNS Fix for Atlas
try:
    dns.resolver.default_resolver = dns.resolver.Resolver(configure=True)
except Exception:
    dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
    dns.resolver.default_resolver.nameservers = ['8.8.8.8', '8.8.4.4', '1.1.1.1']

async def reset_admin():
    print("Connecting to MongoDB for Admin Reset...")
    
    # 1. Initialize MongoDB Client
    mongo_client = motor.motor_asyncio.AsyncIOMotorClient(settings.MONGODB_URI)
    
    # 2. Extract/Force DB Name (consistent with main.py)
    db_name = "aisetu_srm"
    print(f"Using Database: {db_name}")
    
    # 3. Initialize Beanie
    try:
        await init_beanie(
            database=mongo_client[db_name],
            document_models=[User],
        )
        print("Beanie initialized successfully.")
    except Exception as e:
        print(f"FAILED TO INITIALIZE BEANIE: {e}")
        return

    try:
        email = "admin@example.com"
        password = "password123"
        print(f"Target Account: {email}")
        
        # Check if user exists
        user = await User.find_one({"email": email})
        
        if user:
            print(f"User found (ID: {user.id}). Updating password and ensuring active status...")
            user.hashed_password = get_password_hash(password)
            user.role = UserRole.ADMIN
            user.is_active = True
            await user.save()
        else:
            print(f"User not found. Creating new admin account...")
            user = User(
                email=email,
                hashed_password=get_password_hash(password),
                role=UserRole.ADMIN,
                is_active=True,
                name="Tisha Admin",
                preferences={}
            )
            await user.insert()
        
        print("Success: Admin account is ready in MongoDB.")
        print(f"Username: {email}")
        print(f"Password: {password}")
        
    except Exception as e:
        print(f"ERROR DURING RESET: {e}")

if __name__ == "__main__":
    asyncio.run(reset_admin())
