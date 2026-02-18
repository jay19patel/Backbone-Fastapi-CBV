import json
import asyncio
import uuid
import logging
import importlib
import inspect
from typing import Any, Callable, Dict, Optional, Union
import redis.asyncio as redis

logger = logging.getLogger("backbone.queue")

class TaskQueue:
    """
    Advanced Redis-backed Task Queue for Backbone.
    Supports asynchronous task enqueueing and processing.
    """
    def __init__(self, redis_client: Optional[redis.Redis], queue_name: str = "backbone_tasks"):
        self.redis = redis_client
        self.queue_name = queue_name
        self.enabled = redis_client is not None

    async def enqueue(self, func: Union[Callable, str], *args, **kwargs) -> Optional[str]:
        """
        Enqueue a task to be processed in the background.
        """
        if not self.enabled:
            logger.warning("TaskQueue is disabled. Executing task synchronously.")
            if callable(func):
                await func(*args, **kwargs)
            return None

        task_id = str(uuid.uuid4())
        
        # Resolve function path
        if callable(func):
            module_name = func.__module__
            func_name = func.__name__
            # If function is in the main script, we might need to handle it specially
            # for the worker to find it. Standard practice is to use its full path.
            func_path = f"{module_name}:{func_name}"
        else:
            func_path = func

        task_data = {
            "id": task_id,
            "func": func_path,
            "args": args,
            "kwargs": kwargs,
        }

        try:
            await self.redis.rpush(self.queue_name, json.dumps(task_data))
            logger.info(f"Task enqueued: {func_path} (ID: {task_id})")
            return task_id
        except Exception as e:
            logger.error(f"Failed to enqueue task: {e}")
            return None

    async def dequeue(self) -> Optional[Dict[str, Any]]:
        """
        Pop a task from the queue.
        """
        if not self.enabled:
            return None
        
        try:
            # blpop blocks until a task is available
            _, data = await self.redis.blpop(self.queue_name, timeout=5)
            if data:
                return json.loads(data)
        except Exception:
            pass
        return None

class TaskWorker:
    """
    Worker that processes tasks from the TaskQueue.
    """
    def __init__(self, queue: TaskQueue, worker_name: str = "Worker"):
        self.queue = queue
        self.worker_name = worker_name
        self.running = False

    async def run(self):
        """
        Main worker loop.
        """
        self.running = True
        logger.info(f"{self.worker_name} started. Listening for tasks...")
        
        while self.running:
            task_data = await self.queue.dequeue()
            if task_data:
                await self.process_task(task_data)
            await asyncio.sleep(0.1) # Small sleep to be loop-friendly

    async def process_task(self, task_data: Dict[str, Any]):
        """
        Execute the task.
        """
        task_id = task_data.get("id")
        func_path = task_data.get("func")
        args = task_data.get("args", [])
        kwargs = task_data.get("kwargs", {})

        logger.info(f"[{self.worker_name}] Processing task: {func_path} (ID: {task_id})")

        try:
            # Resolve function
            module_name, func_name = func_path.split(":")
            
            if module_name == "__main__":
                # Special case: Tasks defined in the main entry point
                import __main__
                func = getattr(__main__, func_name)
            else:
                module = importlib.import_module(module_name)
                func = getattr(module, func_name)

            # Execute
            if inspect.iscoroutinefunction(func):
                await func(*args, **kwargs)
            else:
                # Wrap sync call to avoid blocking the worker's loop
                await asyncio.to_thread(func, *args, **kwargs)
            
            logger.info(f"[{self.worker_name}] Task completed successfully: (ID: {task_id})")
        except Exception as e:
            logger.error(f"[{self.worker_name}] Task failed: (ID: {task_id}) - Error: {e}")

    def stop(self):
        self.running = False
