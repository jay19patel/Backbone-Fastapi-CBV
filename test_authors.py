import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from backbone.core.models import User, Attachment
from backbone.core.config import BackboneConfig

async def test():
    await init_beanie(database=AsyncIOMotorClient("mongodb://localhost:27017")["blogermenia"], document_models=[User, Attachment])
    try:
        users_docs = await User.find({"is_active": True}, fetch_links=True).limit(5).to_list()
        users = [user.model_dump(by_alias=True) for user in users_docs]
        print(f"Success! Found {len(users)} users.")
        for u in users: print(type(u["profile_image"]))
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
