import asyncio
import os
import sys

# Add current directory to path
sys.path.append(os.getcwd())

from backbone.core.database import init_database
from backbone.core.models import User, Attachment
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from backbone.core.settings import settings
from datetime import datetime, timezone

async def test_update():
    # Initialize Beanie
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    await init_database(
        client=client,
        database_name=settings.DATABASE_NAME,
        document_models=[User, Attachment]
    )
    
    # User ID from prompt
    uid = "69da7380bc261d710a1f6234"
    u = await User.find_one({"_id": ObjectId(uid)})
    
    if not u:
        print(f"User {uid} not found.")
        return

    print(f"Original User: {u.email}, Google: {u.is_google_account}, Image: {u.profile_image}")
    
    # Simulate an update similar to Admin Panel
    update_data = {
        "full_name": u.full_name + " (Updated)",
        "updated_at": datetime.now(timezone.utc)
    }
    
    # Try to update
    try:
        print("Attempting update...")
        await u.set(update_data)
        print("Update SUCCESSFUL in Beanie.")
    except Exception as e:
        print(f"Update FAILED in Beanie: {e}")
        import traceback
        traceback.print_exc()
        return

    # Fetch again
    u2 = await User.find_one({"_id": ObjectId(uid)})
    print(f"New Name: {u2.full_name}")

if __name__ == "__main__":
    asyncio.run(test_update())
