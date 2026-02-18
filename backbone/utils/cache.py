import json
import logging
import hashlib
import asyncio
from functools import wraps
from typing import Any, Optional, Callable, TypeVar, Union
import redis.asyncio as redis
from pydantic import BaseModel
from ..core.settings import settings

logger = logging.getLogger("backbone.cache")

T = TypeVar("T")

from datetime import datetime
from bson import ObjectId
from beanie import PydanticObjectId

class CacheEncoder(json.JSONEncoder):
    """Custom JSON encoder for Pydantic models, datetimes, and ObjectIds."""
    def default(self, obj):
        if isinstance(obj, BaseModel):
            return obj.model_dump()
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, (ObjectId, PydanticObjectId)):
            return str(obj)
        return super().default(obj)

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
                return await asyncio.to_thread(json.loads, data)
        except Exception as e:
            logger.error(f"Cache Get Error: {e}")
        return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        if not self.enabled:
            return False
        try:
            serialized_data = await asyncio.to_thread(json.dumps, value, cls=CacheEncoder)
            await self.redis.set(key, serialized_data, ex=ttl)
            return True
        except Exception as e:
            logger.error(f"Cache Set Error: {e}")
        return False

    async def get_or_set(self, key: str, ttl: int, func: Callable[..., Any], *args, **kwargs) -> Any:
        """
        Get value from cache, or execute func and set value in cache.
        """
        if not self.enabled:
            return await func(*args, **kwargs)
        
        cached = await self.get(key)
        if cached is not None:
            return cached
        
        value = await func(*args, **kwargs)
        await self.set(key, value, ttl=ttl)
        return value

    async def delete(self, key: str) -> bool:
        if not self.enabled:
            return False
        try:
            await self.redis.delete(key)
            return True
        except Exception as e:
            logger.error(f"Cache Delete Error: {e}")
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
            logger.error(f"Cache Pattern Delete Error: {e}")
        return False

def cache(expire: Optional[int] = None, key_prefix: str = "cache", include_ip: bool = False, include_body: bool = True):
    """
    Advanced Caching Decorator for FastAPI endpoints and async functions.
    
    Supports:
    - Custom TTL (defaults to settings.CACHE_TTL)
    - IP-based caching (for idempotency)
    - POST request body hashing
    - Automatic CacheService discovery
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            from fastapi import Request
            
            # Try to find CacheService
            cache_service: Optional[CacheService] = None
            request: Optional[Request] = kwargs.get("request")
            
            # 1. Try from 'self' or 'cls' (for methods)
            if args:
                if hasattr(args[0], "cache_service"):
                    cache_service = args[0].cache_service
                elif hasattr(args[0], "app") and hasattr(args[0].app, "state"):
                    config = getattr(args[0].app.state, "backbone_config", None)
                    cache_service = getattr(config, "cache_service", None)
            
            # 2. Try from 'request' object in kwargs or args
            if not cache_service:
                if not request:
                    for arg in args:
                        if isinstance(arg, Request):
                            request = arg
                            break
                
                if request:
                    config = getattr(request.app.state, "backbone_config", None)
                    cache_service = getattr(config, "cache_service", None)

            # If cache service is not enabled or not found, just execute function
            if not cache_service or not cache_service.enabled:
                return await func(*args, **kwargs)

            # Generate unique cache key
            key_parts = [key_prefix, func.__name__]
            
            # Add IP if requested
            if include_ip and request:
                ip = request.client.host if request.client else "unknown"
                key_parts.append(ip)

            # Hash args and kwargs
            arg_data = {"args": str(args), "kwargs": {k: v for k, v in kwargs.items() if k != "request"}}
            
            # Special handling for POST/PUT body if 'data' is in kwargs
            if include_body and request and request.method in ["POST", "PUT", "PATCH"]:
                try:
                    # If the data is already in kwargs (FASTAPI validates it), use it
                    # Usually 'data' or the model name
                    body_data = {k: v for k, v in kwargs.items() if isinstance(v, (dict, BaseModel, list))}
                    if body_data:
                        arg_data["body"] = str(body_data)
                except Exception:
                    pass

            arg_str = await asyncio.to_thread(json.dumps, arg_data, sort_keys=True, cls=CacheEncoder)
            arg_hash = hashlib.md5(arg_str.encode()).hexdigest()
            key_parts.append(arg_hash)
            
            cache_key = ":".join(key_parts)
            ttl = expire if expire is not None else settings.CACHE_TTL

            return await cache_service.get_or_set(cache_key, ttl, func, *args, **kwargs)
        return wrapper
    return decorator
