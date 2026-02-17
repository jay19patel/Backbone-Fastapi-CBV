import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from main import config

async def clean():
    print(f"Connecting to {config.MONGODB_URL}...")
    client = AsyncIOMotorClient(config.MONGODB_URL)
    db = client[config.DATABASE_NAME]
    
    collections = await db.list_collection_names()
    print(f"Collections: {collections}")
    
    if "AuditDocument" in collections:
        print("Dropping AuditDocument collection...")
        await db["AuditDocument"].drop()
        print("Dropped.")
    else:
        print("AuditDocument collection not found.")
    
    # Also check indices on users just in case
    # await db["users"].drop_index("email_1") 
    
    client.close()

if __name__ == "__main__":
    asyncio.run(clean())
