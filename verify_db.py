import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import redis.asyncio as redis
import sys

async def check_mongo(url, db_name):
    print(f"Checking MongoDB connection at {url}...")
    try:
        client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
        await client[db_name].command("ping")
        print("✅ MongoDB is UP and responding!")
        return True
    except Exception as e:
        print(f"❌ MongoDB connection FAILED: {e}")
        return False

async def check_redis(url):
    print(f"Checking Redis connection at {url}...")
    try:
        client = redis.from_url(url, socket_timeout=2)
        pong = await client.ping()
        if pong:
            print("✅ Redis is UP and responding!")
            return True
    except Exception as e:
        print(f"❌ Redis connection FAILED: {e}")
        return False

async def main():
    mongo_url = "mongodb://localhost:27017"
    db_name = "backbone_app"
    redis_url = "redis://localhost:6380/0"
    
    mongo_ok = await check_mongo(mongo_url, db_name)
    redis_ok = await check_redis(redis_url)
    
    if mongo_ok and redis_ok:
        print("\n🚀 All database systems are running correctly!")
    else:
        print("\n⚠️ Some systems are NOT reachable.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
