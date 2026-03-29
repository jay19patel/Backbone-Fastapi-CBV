"""Model hook helpers for create/update/delete/field-change events."""

from __future__ import annotations

import inspect
from typing import Any, Callable, Iterable, Set, Type

from .core.signals import signals


def _as_field_set(fields: Iterable[str] | str) -> Set[str]:
    if isinstance(fields, str):
        value = fields.strip()
        return {value} if value else set()
    return {str(item).strip() for item in fields if str(item).strip()}


def _connect_unique(signal_obj: Any, model_class: Type, handler: Callable) -> None:
    # Keep import-time registration idempotent by handler name.
    existing = signal_obj._handlers.get(model_class, [])
    signal_obj._handlers[model_class] = [
        item for item in existing
        if getattr(item, "__name__", "") != getattr(handler, "__name__", "")
    ]
    signal_obj.connect(model_class, handler)


def register_create_hook(model_class: Type, handler: Callable) -> Callable:
    _connect_unique(signals.post_create, model_class, handler)
    return handler


def register_update_hook(model_class: Type, handler: Callable) -> Callable:
    _connect_unique(signals.post_update, model_class, handler)
    return handler


def register_delete_hook(model_class: Type, handler: Callable) -> Callable:
    _connect_unique(signals.post_delete, model_class, handler)
    return handler


def register_field_change_hook(
    model_class: Type,
    fields: Iterable[str] | str,
    handler: Callable,
    *,
    require_all: bool = False,
) -> Callable:
    target_fields = _as_field_set(fields)
    if not target_fields:
        raise ValueError("At least one field is required for register_field_change_hook().")

    async def _wrapped(instance: Any, **kwargs) -> None:
        payload = dict(kwargs)
        changed_fields = payload.pop("changed_fields", {}) or {}
        if not isinstance(changed_fields, dict):
            return

        changed = set(changed_fields.keys())
        matched = target_fields.issubset(changed) if require_all else bool(target_fields & changed)
        if not matched:
            return

        payload["changed_fields"] = changed_fields
        payload["matched_fields"] = sorted(target_fields & changed)

        if inspect.iscoroutinefunction(handler):
            await handler(instance, **payload)
        else:
            handler(instance, **payload)

    _wrapped.__name__ = f"{handler.__name__}__field_change"
    _connect_unique(signals.on_field_change, model_class, _wrapped)
    return _wrapped


def on_create(model_class: Type) -> Callable:
    def decorator(handler: Callable) -> Callable:
        register_create_hook(model_class, handler)
        return handler

    return decorator


def on_update(model_class: Type) -> Callable:
    def decorator(handler: Callable) -> Callable:
        register_update_hook(model_class, handler)
        return handler

    return decorator


def on_delete(model_class: Type) -> Callable:
    def decorator(handler: Callable) -> Callable:
        register_delete_hook(model_class, handler)
        return handler

    return decorator


def on_field_change(
    model_class: Type,
    fields: Iterable[str] | str,
    *,
    require_all: bool = False,
) -> Callable:
    def decorator(handler: Callable) -> Callable:
        register_field_change_hook(
            model_class,
            fields,
            handler,
            require_all=require_all,
        )
        return handler

    return decorator

