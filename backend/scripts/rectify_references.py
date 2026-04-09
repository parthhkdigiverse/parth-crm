
import asyncio
import motor.motor_asyncio
import dns.resolver
from bson import ObjectId
from datetime import datetime
import re

# DNS Fix for Atlas
try:
    dns.resolver.default_resolver = dns.resolver.Resolver(configure=True)
except Exception:
    dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
    dns.resolver.default_resolver.nameservers = ['8.8.8.8']

async def rectify_references():
    uri = "mongodb+srv://HK_Digiverse:HK%40Digiverse%40123@cluster0.lcbyqbq.mongodb.net/aisetu_srm?retryWrites=true&w=majority&appName=Cluster0"
    client = motor.motor_asyncio.AsyncIOMotorClient(uri)
    db = client.get_default_database()
    
    print(f"--- Starting Rectify References in DB: {db.name} ---")
    
    core_collections = ['users', 'areas', 'shops', 'clients', 'projects', 'issues', 'visits']
    id_map = {} # { collection_name: { legacy_int_id: new_object_id } }
    
    # 1. Build ID maps
    for coll in core_collections:
        id_map[coll] = {}
        async for doc in db[coll].find({}):
            legacy_id = doc.get("id") or doc.get("pg_id")
            if legacy_id is not None:
                id_map[coll][int(legacy_id)] = doc["_id"]
    
    print(f"Built ID maps for: {list(id_map.keys())}")
    
    # 2. Define Reference Fields and their Target Collection
    # Format: { field_name: target_collection }
    ref_fields = {
        "area_id": "areas",
        "pm_id": "users",
        "project_manager_id": "users",
        "owner_id": "users",
        "client_id": "clients",
        "user_id": "users",
        "shop_id": "shops",
        "project_id": "projects",
        "reporter_id": "users",
        "assigned_to_id": "users",
        "created_by_id": "users",
        "verified_by_id": "users",
        "archived_by_id": "users",
        "pm_assigned_by_id": "users",
        "generated_by_id": "users",
        "scheduled_by_id": "users",
        "referred_by_id": "users",
        "assigned_by_id": "users"
    }
    
    date_fields = [
        "created_at", "updated_at", "visit_date", "verified_at", 
        "start_date", "end_date", "due_date", "joined_at", 
        "demo_scheduled_at", "accepted_at", "assigned_at"
    ]
    
    colls = await db.list_collection_names()
    
    for coll_name in colls:
        if coll_name in ['admin', 'local', 'config', 'alembic_version']: continue
        print(f"Normalizing collection: {coll_name}...")
        
        count = 0
        async for doc in db[coll_name].find({}):
            updates = {}
            doc_id = doc["_id"]
            
            # --- Fix Ref IDs ---
            for key, val in doc.items():
                if key in ref_fields:
                    target_coll = ref_fields[key]
                    if val is not None and isinstance(val, (int, float)):
                        legacy_id = int(val)
                        new_oid = id_map.get(target_coll, {}).get(legacy_id)
                        if new_oid:
                            updates[key] = new_oid
                        else:
                            # Map 0 or non-existent to None to prevent 500 errors
                            updates[key] = None
                            print(f"  [WARN] Broken ref in {coll_name}.{key}: {val} -> None")
                    elif val is not None and isinstance(val, str) and len(val) == 24 and not isinstance(val, ObjectId):
                        # Some IDs might be strings of hex
                        try: updates[key] = ObjectId(val)
                        except: pass

                # --- Fix Dates ---
                if key in date_fields:
                    if val is not None and isinstance(val, str):
                        try:
                            # Use a more robust parsing approach
                            clean_val = val.strip()
                            if clean_val:
                                parsed_date = None
                                # Try fromisoformat (handles T or space, and timezones)
                                try:
                                    parsed_date = datetime.fromisoformat(clean_val.replace("Z", "+00:00"))
                                except:
                                    # Fallback for older formats
                                    for fmt in ["%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"]:
                                        try:
                                            parsed_date = datetime.strptime(clean_val, fmt)
                                            break
                                        except: continue
                                
                                if parsed_date:
                                    updates[key] = parsed_date
                        except Exception as e:
                            print(f"  [WARN] Failed to parse string date in {coll_name}.{key}: {val} | {e}")
                    
                    elif val is not None and isinstance(val, (int, float)):
                        try:
                            # Handle common Unix timestamps (seconds or milliseconds)
                            ts = float(val)
                            # Logic: If it's between year 2000 and 2100 in seconds
                            if 946684800 < ts < 4102444800:
                                updates[key] = datetime.fromtimestamp(ts)
                            elif ts > 1e12: # Milliseconds
                                updates[key] = datetime.fromtimestamp(ts / 1000.0)
                        except Exception as e:
                            print(f"  [WARN] Failed to parse numeric date in {coll_name}.{key}: {val} | {e}")
                
                # --- Handle List of IDs (M2M) ---
                if isinstance(val, list) and key in ["assigned_user_ids", "assigned_owner_ids", "attendee_ids"]:
                    new_list = []
                    changed = False
                    for item in val:
                        if isinstance(item, (int, float)):
                            target = "users"
                            new_oid = id_map.get(target, {}).get(int(item))
                            if new_oid: 
                                new_list.append(new_oid)
                                changed = True
                        elif isinstance(item, str) and len(item) == 24:
                            try: 
                                new_list.append(ObjectId(item))
                                changed = True
                            except: new_list.append(item)
                        else:
                            new_list.append(item)
                    if changed:
                        updates[key] = new_list
            
            # --- Self Healing for Notifications ---
            if coll_name == "notifications" and (doc.get("created_at") is None):
                updates["created_at"] = datetime.now()

            # --- Self Healing for Visits ---
            if coll_name == "visits":
                if doc.get("duration_seconds") is None:
                    updates["duration_seconds"] = 0
                if doc.get("visit_date") is None:
                    updates["visit_date"] = doc.get("created_at") or datetime.now()
                
                # Critical check for shop_id
                s_id = doc.get("shop_id")
                if s_id is None or (isinstance(s_id, (int, float)) and int(s_id) == 0):
                    # We might have to link it to a 'dummy' shop or just nullify it safely
                    # For now, if it's 0 or None, we set it to None to avoid PydanticObjectId crash
                    updates["shop_id"] = None
                    print(f"  [WARN] Null/Zero shop_id in visit {doc_id} -> None")

            # --- Self Healing for Meeting Summaries ---
            if coll_name == "meeting_summaries":
                # Normalize enum values
                mtype = doc.get("meeting_type")
                if mtype == "GOOGLE_MEET": updates["meeting_type"] = "Google Meet"
                elif mtype == "VIRTUAL": updates["meeting_type"] = "Virtual"
                
                # Fix host_id and todo_id (if they are ints)
                for key in ["host_id", "todo_id"]:
                    val = doc.get(key)
                    if isinstance(val, (int, float)):
                        target = "users" if key == "host_id" else "todos"
                        new_oid = id_map.get(target, {}).get(int(val))
                        if new_oid: updates[key] = new_oid
                        else: updates[key] = None

            # --- Self Healing for Clients ---
            if coll_name == "clients":
                if doc.get("created_at") is None:
                    updates["created_at"] = datetime.now()
                # Fix pm_id and owner_id if they are ints
                for k in ["pm_id", "owner_id"]:
                    val = doc.get(k)
                    if isinstance(val, (int, float)):
                        new_oid = id_map.get("users", {}).get(int(val))
                        if new_oid: updates[k] = new_oid
                        else: updates[k] = None

            # --- Self Healing for Shops ---
            if coll_name == "shops":
                for k in ["owner_id", "project_manager_id", "created_by_id", "assigned_by_id"]:
                    val = doc.get(k)
                    if isinstance(val, (int, float)):
                        new_oid = id_map.get("users", {}).get(int(val))
                        if new_oid: updates[k] = new_oid
                        else: updates[k] = None

            # --- Bonus: Fixed Redundant IDs from JSON DUMP ---
            # If the doc has a field literally named 'id' that is an int, it might conflict in Pydantic V2
            # because populate_by_name uses '_id' (PydanticObjectId) and some code might accidentally map legacy 'id'.
            # However, Beanie uses 'id' attribute for '_id'. 
            # I will keep the field for now to avoid breaking existing data migration scripts, 
            # but I will remove legacy 'pg_id'.
            if "pg_id" in doc:
                # Use $unset to remove it
                await db[coll_name].update_one({"_id": doc_id}, {"$unset": {"pg_id": ""}})

            # --- Global Boolean Defaults ---
            for bool_field in ["is_deleted", "is_active", "is_archived"]:
                if bool_field in doc and doc.get(bool_field) is None:
                    updates[bool_field] = (bool_field == "is_active") # Default active=True, deleted=False
                elif bool_field not in doc:
                    # Critical fields for Beanie .find() queries
                    if bool_field in ["is_deleted", "is_active"]:
                        updates[bool_field] = (bool_field == "is_active")

            # --- Ensure Date for Sorting ---
            if "created_at" in doc and not isinstance(doc.get("created_at"), datetime):
                # Attempt to parse if it's already a field but not a datetime object
                pass # Already handled by the universal date loop above
            elif "created_at" not in doc and coll_name != "app_settings":
                updates["created_at"] = datetime.now()

            if updates:
                await db[coll_name].update_one({"_id": doc_id}, {"$set": updates})
                count += 1
                
        if count > 0:
            print(f"  [SUCCESS] {coll_name}: Normalized {count} documents.")

    print("--- Normalization Complete ---")

if __name__ == "__main__":
    asyncio.run(rectify_references())
