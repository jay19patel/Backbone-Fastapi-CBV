import inspect
from typing import List, Callable, Any, Dict

def action(detail: bool = False, methods: List[str] = None, **kwargs):
    if methods is None:
        methods = ["GET"]
    def decorator(func: Callable) -> Callable:
        func.__action_config__ = {
            "detail": detail,
            "methods": methods,
            "kwargs": kwargs
        }
        return func
    return decorator
