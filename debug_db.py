import asyncio
from main import config
from schema import BlogSchema
from backbone.core.database import init_database
from motor.motor_asyncio import AsyncIOMotorClient

async def debug_db():
    client = AsyncIOMotorClient(config.MONGODB_URL)
    await init_database(client, config.DATABASE_NAME, [BlogSchema])
    
    print("Checking BlogSchema collection...")
    count = await BlogSchema.count()
    print(f"Total Blogs: {count}")
    
    if count > 0:
        item = await BlogSchema.find_one({})
        print("First Blog Item:")
        print(item.model_dump())
        
        # Check raw pymongo
        print("\nRaw Pymongo Document:")
        raw = await BlogSchema.get_pymongo_collection().find_one({})
        print(raw)
        
        # Check is_deleted
        deleted_count = await BlogSchema.find({"is_deleted": False}).count()
        print(f"\nActive Blogs (is_deleted=False): {deleted_count}")

if __name__ == "__main__":
    asyncio.run(debug_db())
