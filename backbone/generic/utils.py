"""
backbone.generic.utils
~~~~~~~~~~~~~~~~~~~~~~
Internal helper functions for generic views.
"""

from typing import Any, Callable, Dict, List, Optional
import inspect
from fastapi import APIRouter

def _parse_sort(sort_string: Optional[str]) -> Optional[list]:
    """Parse a sort query parameter into MongoDB sort specification."""
    if not sort_string:
        return None
    parsed = []
    for field in sort_string.split(","):
        field = field.strip()
        if field.startswith("-"):
            parsed.append((field[1:], -1))
        else:
            parsed.append((field, 1))
    return parsed

def _register_actions(view: Any, router: APIRouter) -> None:
    """Scan a view instance for methods decorated with @action and register them."""
    for name, method in inspect.getmembers(view, inspect.ismethod):
        config = getattr(method, "__action_config__", None)
        if not config:
            continue
        detail = config.get("detail", False)
        methods = config.get("methods", ["GET"])
        kwargs = config.get("kwargs", {})
        path = kwargs.pop("path", f"/{{pk}}/{name}/" if detail else f"/{name}/")
        router.add_api_route(
            path=path,
            endpoint=method,
            methods=[m.upper() for m in methods],
            **kwargs,
        )

async def _extract_create_data(view: Any, data: Any) -> dict:
    """Extract and process create data, handling Link fields."""
    populate = view._get_populate_fields()
    extracted_links = {}
    for field_name in populate:
        if hasattr(data, field_name):
            val = getattr(data, field_name)
            if val is not None:
                extracted_links[field_name] = val

    validated = data.model_dump(by_alias=True, exclude={"id"}) if hasattr(data, "model_dump") else data
    validated.update(extracted_links)
    return await view._process_link_fields(validated)

async def _extract_update_data(view: Any, data: Any) -> dict:
    """Extract update data, stripping dangerous and unknown fields."""
    raw = data.model_dump(exclude_unset=True) if hasattr(data, "model_dump") else dict(data)
    from ..core.mixins import DANGEROUS_FIELDS
    for field in DANGEROUS_FIELDS:
        raw.pop(field, None)
    return await view._process_link_fields(raw)
