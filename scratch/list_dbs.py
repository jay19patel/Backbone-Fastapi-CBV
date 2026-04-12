
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def list_all():
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27017")
    dbs = await client.list_database_names()
    target_id = "69da769f68dfa158e7003a3a"
    
    for db_name in dbs:
        if db_name in ["admin", "local", "config"]: continue
        db = client[db_name]
        cols = await db.list_collection_names()
        print(f"\nDB: {db_name}")
        for col in cols:
            count = await db[col].count_documents({})
            print(f"  - {col}: {count} docs")
            # Check for the specific ID
            found = await db[col].find_one({"_id": target_id})
            if not found:
                # Try as ObjectId
                from beanie import PydanticObjectId
                try:
                    found = await db[col].find_one({"_id": PydanticObjectId(target_id)})
                except: pass
            
            if found:
                print(f"    *** FOUND TARGET ID in {col} ***")
                print(f"    Data: {found}")

if __name__ == "__main__":
    asyncio.run(list_all())
