
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def wipe_carts():
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27017")
    db = client["EShop"]
    
    print("Wiping corrupted cart data from 'EShop' database...")
    
    # 1. Clear explicitly named collections
    res1 = await db["carts"].delete_many({})
    res2 = await db["cart_items"].delete_many({})
    
    # 2. Clear corrupted records in BackboneDocument (where they went when unregistered)
    res3 = await db["BackboneDocument"].delete_many({"session_id": {"$exists": True}})
    
    print(f"  Deleted {res1.deleted_count} carts.")
    print(f"  Deleted {res2.deleted_count} cart_items.")
    print(f"  Deleted {res3.deleted_count} corrupted BackboneDocument carts.")
    
    print("\nCleanup complete. The system will now use the correct 'carts' collection.")

if __name__ == "__main__":
    asyncio.run(wipe_carts())
