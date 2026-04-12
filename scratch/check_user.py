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

async def check():
    # Initialize Beanie
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    await init_database(
        client=client,
        database_name=settings.DATABASE_NAME,
        document_models=[User, Attachment]
    )
    
    # Check user
    uid = "69da7380bc261d710a1f6234"
    u = await User.find_one({"_id": ObjectId(uid)})
    
    if not u:
        print(f"User {uid} not found.")
        return

    print(f"User: {u.email}")
    print(f"Full Name: {u.full_name}")
    print(f"Profile Image Field Value: {u.profile_image}")
    
    if u.profile_image:
        print(f"Profile Image Type: {type(u.profile_image)}")
        # Check if it's a Link
        from beanie import Link
        if isinstance(u.profile_image, Link):
            print(f"Is Beanie Link: Yes")
            print(f"Link ID: {u.profile_image.ref.id}")
            # Try to fetch
            att = await u.profile_image.fetch()
            if att:
                print(f"Fetched Attachment: {att.filename} ({att.file_path})")
            else:
                print("Failed to fetch attachment link!")
        else:
             print(f"Is Beanie Link: No")

if __name__ == "__main__":
    asyncio.run(check())
