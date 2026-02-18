import json
from typing import Any, Optional
import redis.asyncio as redis

class CacheService:
    """
    Service for handling Redis caching.
    """
    def __init__(self, redis_client: Optional[redis.Redis], enabled: bool = True):
        self.redis = redis_client
        self.enabled = enabled and redis_client is not None

    async def get(self, key: str) -> Optional[Any]:
        if not self.enabled:
            return None
        try:
            data = await self.redis.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            print(f"Cache Get Error: {e}")
        return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        if not self.enabled:
            return False
        try:
            await self.redis.set(key, json.dumps(value), ex=ttl)
            return True
        except Exception as e:
            print(f"Cache Set Error: {e}")
        return False

    async def delete(self, key: str) -> bool:
        if not self.enabled:
            return False
        try:
            await self.redis.delete(key)
            return True
        except Exception as e:
            print(f"Cache Delete Error: {e}")
        return False

    async def delete_pattern(self, pattern: str) -> bool:
        if not self.enabled:
            return False
        try:
            keys = await self.redis.keys(pattern)
            if keys:
                await self.redis.delete(*keys)
            return True
        except Exception as e:
            print(f"Cache Pattern Delete Error: {e}")
        return False
