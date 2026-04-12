import asyncio
import os
import sys

# Add current directory to path
sys.path.append(os.getcwd())

from backbone.core.database import init_database
from backbone.core.models import User, Attachment
from motor.motor_asyncio import AsyncIOMotorClient
from backbone.core.settings import settings

async def find_google_users():
    # Initialize Beanie
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    await init_database(
        client=client,
        database_name=settings.DATABASE_NAME,
        document_models=[User, Attachment]
    )
    
    users = await User.find({"is_google_account": True}).to_list()
    print(f"Found {len(users)} Google users:")
    for u in users:
        print(f"  ID: {u.id}, Email: {u.email}, Image: {u.profile_image}")

if __name__ == "__main__":
    asyncio.run(find_google_users())
