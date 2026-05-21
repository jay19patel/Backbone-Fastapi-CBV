"""Shared Jinja globals and filters for admin and template pages."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from ..common.services import CacheEncoder
from .site import admin_site


def nice_title(value: str) -> str:
    if not value:
        return ""
    return value.replace("_", " ").title()


def filesize(value: Any) -> str:
    try:
        size = float(value)
    except (TypeError, ValueError):
        return str(value) if value else "—"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(size) < 1024.0:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def custom_tojson(value: Any, indent: int | None = None) -> str:
    return json.dumps(value, cls=CacheEncoder, indent=indent)


def datetime_local_value(value: Any) -> str:
    """
    Format a datetime value for use in an <input type='datetime-local'> field.

    Accepts Python datetime objects or ISO-8601 strings and returns the
    'YYYY-MM-DDTHH:MM' format required by the browser widget.
    """
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%dT%H:%M")
    # ? FOR STRING VALUES EXTRACT THE FIRST 16 CHARS OF AN ISO TIMESTAMP
    s = str(value)
    if len(s) >= 16 and "T" in s:
        return s[:16]
    # ? FALLBACK: REPLACE SPACE SEPARATOR USED BY SOME MONGO REPRESENTATIONS
    if len(s) >= 16 and " " in s:
        return s[:16].replace(" ", "T")
    return s


def register_admin_jinja_env(env: Any) -> None:
    env.globals["admin_site"] = admin_site
    env.filters["nice_title"] = nice_title
    env.filters["filesize"] = filesize
    env.filters["tojson"] = custom_tojson
    env.filters["datetime_local"] = datetime_local_value
