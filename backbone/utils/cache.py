"""
backbone.utils.cache
~~~~~~~~~~~~~~~~~~~~

Redis-backed caching layer for Backbone.

Provides:
    • ``CacheService`` — get / set / delete / pattern-delete operations
    • ``cache()`` decorator — automatic caching for FastAPI endpoints
    • ``CacheEncoder`` — JSON encoding for Pydantic models, datetimes,
      ObjectIds, and Beanie Links

Design decisions:
    • ``delete_pattern()`` uses ``SCAN`` with a cursor — never ``KEYS``.
      The ``KEYS`` command is O(N) and blocks the entire Redis server.
    • All cache errors are **logged, never swallowed silently**.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

import redis.asyncio as redis
from beanie import PydanticObjectId
from bson import ObjectId
from pydantic import BaseModel

from ..core.settings import settings

logger = logging.getLogger("backbone.cache")

T = TypeVar("T")

# Maximum keys to process per SCAN iteration
SCAN_BATCH_SIZE = 100


# ── JSON Encoder ────────────────────────────────────────────────────────────

class CacheEncoder(json.JSONEncoder):
    """
    Custom JSON encoder for Backbone cache serialisation.

    Handles:
        • Pydantic ``BaseModel`` instances
        • ``datetime`` objects → ISO 8601 strings
        • ``ObjectId`` / ``PydanticObjectId`` → strings
        • Beanie ``Link`` objects → string ID references
    """

    def default(self, obj: Any) -> Any:
        """Encode non-standard types to JSON-safe representations."""
        if isinstance(obj, BaseModel):
            return obj.model_dump()
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, (ObjectId, PydanticObjectId)):
            return str(obj)

        from beanie import Link

        if isinstance(obj, Link):
            if hasattr(obj, "ref"):
                return str(obj.ref.id)
            if hasattr(obj, "id"):
                return str(obj.id)
            return str(obj)

        return super().default(obj)


# ── Cache Service ───────────────────────────────────────────────────────────

class CacheService:
    """
    Service for handling Redis caching operations.

    All methods are safe to call even when Redis is disabled — they
    gracefully return ``None`` / ``False`` without raising.

    Args:
        redis_client: An ``aioredis`` Redis client, or ``None``.
        enabled: Whether caching is active.  Automatically ``False``
            if ``redis_client`` is ``None``.

    Example::

        cache_svc = CacheService(redis_client, enabled=True)
        await cache_svc.set("key", {"foo": "bar"}, ttl=60)
        data = await cache_svc.get("key")
    """

    def __init__(
        self,
        redis_client: Optional[redis.Redis],
        enabled: bool = True,
    ) -> None:
        self.redis = redis_client
        self.enabled = enabled and redis_client is not None

    async def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a cached value by key.

        Args:
            key: The cache key.

        Returns:
            The deserialised value, or ``None`` if not found or disabled.
        """
        if not self.enabled:
            return None
        try:
            data = await self.redis.get(key)
            if data:
                return await asyncio.to_thread(json.loads, data)
        except Exception as exc:
            logger.error("Cache GET error for key '%s': %s", key, exc)
        return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """
        Store a value in the cache.

        Args:
            key: The cache key.
            value: The value to cache (must be JSON-serialisable).
            ttl: Time-to-live in seconds (default: 300).

        Returns:
            ``True`` if the value was stored, ``False`` on error or disabled.
        """
        if not self.enabled:
            return False
        try:
            serialised = await asyncio.to_thread(
                json.dumps, value, cls=CacheEncoder,
            )
            await self.redis.set(key, serialised, ex=ttl)
            return True
        except Exception as exc:
            logger.error("Cache SET error for key '%s': %s", key, exc)
        return False

    async def get_or_set(
        self,
        key: str,
        ttl: int,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Return cached value if available; otherwise execute ``func``,
        cache its result, and return it.

        Args:
            key: The cache key.
            ttl: Time-to-live in seconds.
            func: Async callable to produce the value on cache miss.

        Returns:
            The cached or freshly-computed value.
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
        """
        Delete a single cached value.

        Args:
            key: The cache key to delete.

        Returns:
            ``True`` if the key was deleted, ``False`` on error or disabled.
        """
        if not self.enabled:
            return False
        try:
            await self.redis.delete(key)
            return True
        except Exception as exc:
            logger.error("Cache DELETE error for key '%s': %s", key, exc)
        return False

    async def delete_pattern(self, pattern: str) -> bool:
        """
        Delete all keys matching a glob pattern using ``SCAN``.

        Uses cursor-based iteration (never ``KEYS``) to avoid blocking
        the Redis server on large keyspaces.

        Args:
            pattern: A Redis glob pattern (e.g., ``"backbone:*blogs*"``).

        Returns:
            ``True`` if the operation completed, ``False`` on error.
        """
        if not self.enabled:
            return False
        try:
            cursor: int = 0
            while True:
                cursor, keys = await self.redis.scan(
                    cursor, match=pattern, count=SCAN_BATCH_SIZE,
                )
                if keys:
                    await self.redis.delete(*keys)
                if cursor == 0:
                    break
            return True
        except Exception as exc:
            logger.error("Cache PATTERN DELETE error for '%s': %s", pattern, exc)
        return False


# ── Cache Decorator ─────────────────────────────────────────────────────────

def cache(
    expire: Optional[int] = None,
    key_prefix: str = "cache",
    include_ip: bool = False,
    include_body: bool = True,
) -> Callable:
    """
    Decorator for caching FastAPI endpoint responses in Redis.

    Supports:
        • Custom TTL (defaults to ``settings.CACHE_TTL``)
        • IP-based cache keys (for idempotency on POST)
        • POST request body hashing
        • Automatic ``CacheService`` discovery from app state

    Args:
        expire: TTL in seconds.  ``None`` = use ``settings.CACHE_TTL``.
        key_prefix: Prefix for the cache key.
        include_ip: Include client IP in the cache key.
        include_body: Include request body hash for write endpoints.

    Example::

        @router.get("/items")
        @cache(expire=60, key_prefix="items:list")
        async def list_items(request: Request):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache_service = _discover_cache_service(args, kwargs)

            if not cache_service or not cache_service.enabled:
                return await func(*args, **kwargs)

            cache_key = _build_cache_key(
                key_prefix, func.__name__,
                args, kwargs,
                include_ip=include_ip,
                include_body=include_body,
            )
            ttl = expire if expire is not None else settings.CACHE_TTL

            return await cache_service.get_or_set(
                cache_key, ttl, func, *args, **kwargs,
            )

        return wrapper
    return decorator


def _discover_cache_service(
    args: tuple,
    kwargs: dict,
) -> Optional[CacheService]:
    """Attempt to find the CacheService from request or view context."""
    from fastapi import Request

    # Try from 'self' or first arg
    if args:
        first = args[0]
        if hasattr(first, "cache_service"):
            return first.cache_service
        if hasattr(first, "app") and hasattr(first.app, "state"):
            config = getattr(first.app.state, "backbone_config", None)
            if config:
                return getattr(config, "cache_service", None)

    # Try from 'request' in kwargs or args
    request = kwargs.get("request")
    if not request:
        for arg in args:
            if isinstance(arg, Request):
                request = arg
                break

    if request:
        config = getattr(request.app.state, "backbone_config", None)
        if config:
            return getattr(config, "cache_service", None)

    return None


def _build_cache_key(
    prefix: str,
    func_name: str,
    args: tuple,
    kwargs: dict,
    *,
    include_ip: bool,
    include_body: bool,
) -> str:
    """Build a deterministic cache key from request context."""
    from fastapi import Request

    key_parts = [prefix, func_name]

    request: Optional[Any] = kwargs.get("request")
    if not request:
        for arg in args:
            if isinstance(arg, Request):
                request = arg
                break

    # Add client IP
    if include_ip and request:
        ip = request.client.host if request.client else "unknown"
        key_parts.append(ip)

    # Hash arguments
    arg_data: dict = {
        "args": str(args),
        "kwargs": {k: v for k, v in kwargs.items() if k != "request"},
    }

    if request:
        arg_data["query_params"] = dict(request.query_params)

    # Include body for write methods
    if include_body and request and request.method in ("POST", "PUT", "PATCH"):
        body_data = {
            k: v
            for k, v in kwargs.items()
            if isinstance(v, (dict, BaseModel, list))
        }
        if body_data:
            arg_data["body"] = str(body_data)

    arg_str = json.dumps(arg_data, sort_keys=True, cls=CacheEncoder)
    arg_hash = hashlib.md5(arg_str.encode()).hexdigest()
    key_parts.append(arg_hash)

    return ":".join(key_parts)
