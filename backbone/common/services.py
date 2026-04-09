import json
import asyncio
import uuid
import hashlib
import logging
import importlib
import inspect
import time
import traceback
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar, Union

import redis.asyncio as redis
from beanie import PydanticObjectId, Link
from bson import ObjectId
from pydantic import BaseModel

from ..core.models import Task
from ..core.settings import settings

logger = logging.getLogger("backbone.services")

# ── Cache Encoder ────────────────────────────────────────────────────────────

class CacheEncoder(json.JSONEncoder):
    """Custom JSON encoder for Backbone cache serialisation."""
    def default(self, obj: Any) -> Any:
        if isinstance(obj, BaseModel):
            return obj.model_dump()
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, (ObjectId, PydanticObjectId)):
            return str(obj)
        if isinstance(obj, Link):
            if hasattr(obj, "ref"):
                return str(obj.ref.id)
            if hasattr(obj, "id"):
                return str(obj.id)
            return str(obj)
        return super().default(obj)

# ── Cache Service ───────────────────────────────────────────────────────────

class CacheService:
    """Service for handling Redis caching operations."""
    def __init__(self, redis_client: Optional[redis.Redis], enabled: bool = True) -> None:
        self.redis = redis_client
        self.enabled = enabled and redis_client is not None

    async def get(self, key: str) -> Optional[Any]:
        if not self.enabled: return None
        try:
            data = await self.redis.get(key)
            if data:
                return await asyncio.to_thread(json.loads, data)
        except Exception as exc:
            logger.error(f"Cache GET error for key '{key}': {exc}")
        return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        if not self.enabled: return False
        try:
            serialised = await asyncio.to_thread(json.dumps, value, cls=CacheEncoder)
            await self.redis.set(key, serialised, ex=ttl)
            return True
        except Exception as exc:
            logger.error(f"Cache SET error for key '{key}': {exc}")
        return False

    async def get_or_set(self, key: str, ttl: int, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        if not self.enabled: return await func(*args, **kwargs)
        cached = await self.get(key)
        if cached is not None: return cached
        value = await func(*args, **kwargs)
        await self.set(key, value, ttl=ttl)
        return value

    async def delete(self, key: str) -> bool:
        if not self.enabled: return False
        try:
            await self.redis.delete(key)
            return True
        except Exception as exc:
            logger.error(f"Cache DELETE error for key '{key}': {exc}")
        return False

    async def delete_pattern(self, pattern: str) -> bool:
        if not self.enabled: return False
        try:
            cursor: int = 0
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                if keys: await self.redis.delete(*keys)
                if cursor == 0: break
            return True
        except Exception as exc:
            logger.error(f"Cache PATTERN DELETE error for '{pattern}': {exc}")
        return False

    async def flush(self) -> bool:
        """Flush the configured Redis database."""
        if not self.enabled:
            return False
        try:
            await self.redis.flushdb()
            return True
        except Exception as exc:
            logger.error(f"Cache FLUSH error: {exc}")
        return False

    def __call__(self, expire: int = 300, include_ip: bool = False, key_prefix: str = "cache"):
        """FastAPI-compatible caching decorator."""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                if not self.enabled:
                    return await func(*args, **kwargs)

                # Find FastAPI request object in args/kwargs
                from fastapi import Request
                request = None
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break
                if not request:
                    for val in kwargs.values():
                        if isinstance(val, Request):
                            request = val
                            break

                # Build cache key
                key_parts = [key_prefix, func.__name__]
                if include_ip and request:
                    key_parts.append(request.client.host if request.client else "unknown_ip")
                
                # Hash arguments for a stable key
                params = str(args) + str(kwargs)
                key_parts.append(hashlib.md5(params.encode()).hexdigest())
                key = ":".join(key_parts)

                # Get or Set
                cached = await self.get(key)
                if cached is not None:
                    return cached
                
                result = await func(*args, **kwargs)
                await self.set(key, result, ttl=expire)
                return result
            return wrapper
        return decorator

# ── Global Cache Instance (Backward Compatibility) ───────────────────────────

cache = CacheService(None, enabled=False)

# ── Task Queue ──────────────────────────────────────────────────────────────

class TaskQueue:
    """Advanced Redis-backed Task Queue for Backbone."""
    def __init__(self, redis_client: Optional[redis.Redis], queue_name: str = "backbone_tasks"):
        self.redis = redis_client
        self.queue_name = queue_name
        self.enabled = redis_client is not None

    async def enqueue(self, func: Union[Callable, str], *args, no_log: bool = False, **kwargs) -> Optional[str]:
        if callable(func):
            func_path = f"{func.__module__}:{func.__name__}"
        else:
            func_path = func
        max_retries = int(kwargs.pop("max_retries", 3))

        if not self.enabled:
            logger.warning("TaskQueue disabled. Executing synchronously.")
            if callable(func):
                if inspect.iscoroutinefunction(func): await func(*args, **kwargs)
                else: func(*args, **kwargs)
            return None

        task_id = str(uuid.uuid4())
        task_log = None
        if not no_log:
            try:
                task_log = Task(
                    task_id="pending",
                    function_name=func_path,
                    status="queued",
                    metadata={
                        "queue_name": self.queue_name,
                        "max_retries": max_retries,
                    },
                )
                await task_log.insert()
                task_id = str(task_log.id)
                task_log.task_id = task_id
                await task_log.save()
            except Exception as e:
                logger.error(f"Failed to create Task entry: {e}")

        task_data = {
            "id": task_id,
            "func": func_path,
            "args": args,
            "kwargs": kwargs,
            "no_log": no_log,
            "retry_count": 0,
            "max_retries": max_retries,
            "queue_name": self.queue_name,
        }
        try:
            await self.redis.rpush(self.queue_name, json.dumps(task_data, default=str))
            return task_id
        except Exception as e:
            logger.error(f"Failed to enqueue task: {e}")
            if task_log:
                task_log.status = "failed"
                task_log.error_message = f"Redis Error: {e}"
                task_log.error_traceback = traceback.format_exc()
                await task_log.save()
            return None

    async def dequeue(self) -> Optional[Dict[str, Any]]:
        if not self.enabled: return None
        try:
            result = await self.redis.blpop(self.queue_name, timeout=5)
            if result: return json.loads(result[1])
        except Exception as exc:
            logger.error(f"Failed to dequeue task: {exc}")
        return None

class TaskWorker:
    """Worker that processes tasks from the TaskQueue."""
    def __init__(self, queue: TaskQueue, worker_name: str = "Worker"):
        self.queue = queue
        self.worker_name = worker_name
        self.running = False

    async def run(self):
        self.running = True
        logger.info(f"{self.worker_name} started.")
        while self.running:
            task_data = await self.queue.dequeue()
            if task_data: await self.process_task(task_data)
            await asyncio.sleep(0.1)

    async def process_task(self, task_data: Dict[str, Any]):
        task_id, func_path = task_data.get("id"), task_data.get("func")
        args, kwargs, no_log = task_data.get("args", []), task_data.get("kwargs", {}), task_data.get("no_log", False)
        
        task_log = None
        if not no_log:
            try:
                if ObjectId.is_valid(task_id):
                    task_log = await Task.get(task_id)
                    if task_log:
                        task_log.status = "processing"
                        task_log.started_at = datetime.now(timezone.utc)
                        task_log.metadata = {
                            **(task_log.metadata or {}),
                            "queue_name": task_data.get("queue_name", self.queue.queue_name),
                            "retry_count": task_data.get("retry_count", 0),
                            "max_retries": task_data.get("max_retries", 3),
                        }
                        await task_log.save()
            except Exception as exc:
                logger.warning(f"Failed to load task log {task_id}: {exc}")

        start_time = time.time()
        try:
            module_name, func_name = func_path.split(":")
            module = importlib.import_module(module_name)
            func = getattr(module, func_name)
            if inspect.iscoroutinefunction(func): await func(*args, **kwargs)
            else: await asyncio.to_thread(func, *args, **kwargs)
            if task_log:
                task_log.status = "completed"
                task_log.completed_at = datetime.now(timezone.utc)
                task_log.execution_time_s = round(time.time() - start_time, 2)
                task_log.error_message = None
                task_log.error_traceback = None
                await task_log.save()
        except Exception as e:
            logger.error(f"Task failed {task_id}: {e}")
            
            # Retry logic
            retry_count = task_data.get("retry_count", 0)
            max_retries = task_data.get("max_retries", 3)
            
            if retry_count < max_retries:
                retry_count += 1
                task_data["retry_count"] = retry_count
                backoff = 2 ** retry_count # Exponential backoff
                logger.info(f"Retrying task {task_id} in {backoff}s (Attempt {retry_count}/{max_retries})")
                
                # Re-enqueue after sleep
                await asyncio.sleep(backoff)
                try:
                    await self.queue.redis.rpush(self.queue.queue_name, json.dumps(task_data, default=str))
                    if task_log:
                        task_log.status = f"retrying ({retry_count})"
                        task_log.error_message = f"Attempt {retry_count-1} failed: {e}"
                        task_log.error_traceback = traceback.format_exc()
                        task_log.metadata = {
                            **(task_log.metadata or {}),
                            "retry_count": retry_count,
                            "max_retries": max_retries,
                            "queue_name": task_data.get("queue_name", self.queue.queue_name),
                        }
                        await task_log.save()
                    return
                except Exception as re:
                    logger.error(f"Failed to re-enqueue task {task_id}: {re}")

            if task_log:
                task_log.status = "failed"
                task_log.error_message = str(e)
                task_log.error_traceback = traceback.format_exc()
                task_log.execution_time_s = round(time.time() - start_time, 2)
                await task_log.save()

# ── Background Task Helper ──────────────────────────────────────────────────

async def background_task(func: Union[Callable, str], *args, **kwargs):
    """Simplified helper to enqueue a task."""
    try:
        from ..core.config import BackboneConfig
        return await BackboneConfig.get_instance().task_queue.enqueue(func, *args, **kwargs)
    except Exception as e:
        logger.error(f"Failed to enqueue task: {e}")
        return None


async def background_internal_task(func: Union[Callable, str], *args, **kwargs):
    """
    Enqueue internal framework tasks without creating Task entries.
    Uses the dedicated internal queue.
    """
    try:
        from ..core.config import BackboneConfig
        return await BackboneConfig.get_instance().internal_task_queue.enqueue(
            func,
            *args,
            no_log=True,
            **kwargs,
        )
    except Exception as e:
        logger.error(f"Failed to enqueue internal task: {e}")
        return None
