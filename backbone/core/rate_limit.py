import time
from typing import Optional, Tuple
from fastapi import Request, HTTPException, status, Depends, Response
from .settings import settings
import redis.asyncio as redis
import logging

logger = logging.getLogger("backbone.rate_limit")

# Lua script for atomic sliding window rate limiting
# KEYS[1] = rate limit key (e.g., "rate_limit:user123:api_path")
# ARGV[1] = current timestamp (ms)
# ARGV[2] = window size in milliseconds
# ARGV[3] = max requests allowed in the window
SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])

-- Remove elements outside the window
local clearBefore = now - window
redis.call('ZREMRANGEBYSCORE', key, 0, clearBefore)

-- Count elements in the window
local reqCount = redis.call('ZCARD', key)

if reqCount < limit then
    -- Add the current request
    redis.call('ZADD', key, now, now)
    -- Set the expiration on the key so it cleans up when idle
    redis.call('PEXPIRE', key, window)
    return { 1, limit - reqCount - 1 }
else
    -- Determine when we can try again
    -- Smallest score in the sorted set + window = time when it expires
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local reset_time_ms = 0
    if oldest and oldest[2] then
        reset_time_ms = tonumber(oldest[2]) + window
    end
    -- Still extend expiration to hold state, technically optional here 
    redis.call('PEXPIRE', key, window)
    return { 0, reset_time_ms }
end
"""

class RateLimiter:
    """
    Sliding window rate limiter using Redis sorted sets.
    """
    def __init__(self, calls: int = None, window: int = None):
        """
        :param calls: Maximum number of calls allowed in the window.
        :param window: Window size in seconds.
        """
        self.calls = calls if calls is not None else settings.RATE_LIMIT_DEFAULT_CALLS
        self.window = window if window is not None else settings.RATE_LIMIT_DEFAULT_WINDOW
        # Lazily loaded script hash and redis client
        self._sha = None

    async def _get_redis(self, request: Request) -> Optional[redis.Redis]:
        """Fetch the Redis client from BackboneConfig attached to the app state."""
        config = getattr(request.app.state, "backbone_config", None)
        if config and config.redis_client:
             return config.redis_client
        return None

    async def _load_script(self, redis_client: redis.Redis):
        if not self._sha:
            self._sha = await redis_client.script_load(SLIDING_WINDOW_SCRIPT)
        return self._sha

    async def check(self, redis_client: redis.Redis, key: str) -> Tuple[bool, int]:
        """
        Checks if the request is allowed.
        :returns: (is_allowed: bool, remaining_or_reset_time: int)
        """
        sha = await self._load_script(redis_client)
        now_ms = int(time.time() * 1000)
        window_ms = self.window * 1000
        
        result = await redis_client.evalsha(
            sha,
            1,
            key,
            now_ms,
            window_ms,
            self.calls
        )
        
        allowed = bool(result[0])
        info = int(result[1])
        return allowed, info

class RateLimit:
    """
    FastAPI Dependency to apply rate limiting based on User JWT (sub) or IP fallback.
    Usage:
        @app.get("/api")
        async def my_endpoint(rate_limit=Depends(RateLimit(calls=50, window=60))):
            pass
    """
    def __init__(self, calls: int = None, window: int = None):
        self.limiter = RateLimiter(calls=calls, window=window)

    async def __call__(self, request: Request, response: Response):
        app_config = getattr(request.app.state, "backbone_config", None)
        rate_limit_enabled = settings.RATE_LIMIT_ENABLED
        if app_config and hasattr(app_config.config, "RATE_LIMIT_ENABLED"):
            rate_limit_enabled = app_config.config.RATE_LIMIT_ENABLED

        if not rate_limit_enabled:
            return True

        redis_client = await self.limiter._get_redis(request)
        if not redis_client:
            # If rate limiter is enabled but strictly requires Redis and it's not present,
            logger.warning("Rate limiting is enabled but Cache/Redis service is not running. Passing request.")
            return True

        # Extract identifier:
        identifier = "anonymous"
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            from ..common.utils import TokenManager
            payload = TokenManager.decode_token(token)
            if payload and "sub" in payload:
                identifier = f"user:{payload['sub']}"
        else:
            client_ip = request.client.host if request.client else "unknown_ip"
            identifier = f"ip:{client_ip}"

        route_path = request.url.path
        
        # Redis key e.g.: rate_limit:user:123:/api/v1/auth/me
        key = f"rate_limit:{identifier}:{route_path}"
        
        allowed, info = await self.limiter.check(redis_client, key)

        if not allowed:
            reset_time_ms = info
            reset_in_sec = max(int((reset_time_ms - time.time() * 1000) / 1000), 1)
            
            headers = {
                "Retry-After": str(reset_in_sec),
                "X-RateLimit-Limit": str(self.limiter.calls),
                "X-RateLimit-Reset": str(int(reset_time_ms / 1000))
            }
            
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too Many Requests. Please try again later.",
                headers=headers
            )

        # If allowed, inject headers into the successful response!
        # `info` contains the remaining requests
        response.headers["X-RateLimit-Limit"] = str(self.limiter.calls)
        response.headers["X-RateLimit-Remaining"] = str(info)
        
        return True
