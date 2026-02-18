import logging
import asyncio
from typing import Callable, Any, Union
from ..core.config import BackboneConfig

logger = logging.getLogger("backbone.tasks")

async def background_task(func: Union[Callable, str], *args, **kwargs):
    """
    Simplified helper to enqueue a task.
    Supports both sync and async functions.
    Syntax: await background_task(my_func, arg1, arg2)
    """
    try:
        config = BackboneConfig.get_instance()
        return await config.task_queue.enqueue(func, *args, **kwargs)
    except Exception as e:
        logger.error(f"Failed to enqueue background task: {e}")
        return None
