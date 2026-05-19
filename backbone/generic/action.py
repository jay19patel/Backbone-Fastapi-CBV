from collections.abc import Callable


def action(detail: bool = False, methods: list[str] = None, **kwargs):
    if methods is None:
        methods = ["GET"]

    def decorator(func: Callable) -> Callable:
        func.__action_config__ = {"detail": detail, "methods": methods, "kwargs": kwargs}
        return func

    return decorator
