"""
blogging/services/blog_hooks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Signal/event hook implementations for the Blogging platform.
Connects handlers to Backbone global model signals to implement analytics tracking.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from bson import ObjectId
from fastapi import Request

from backbone.core.models import User
from backbone.core.signals import signals
from blogging.schemas.blog import Blog, BlogView

logger = logging.getLogger("blogging.blog_hooks")

# Simple in-memory cache to deduplicate rapid successive hits from same IP/User
# Format: { "blog_id:user_or_ip": timestamp }
_recent_views_cache: dict[str, float] = {}


def _get_clean_id(val: Any) -> str | None:
    """Safely extract string ID representation from direct string, Link or dict."""
    if not val:
        return None
    if isinstance(val, dict):
        return str(val.get("id") or val.get("_id") or "")
    if hasattr(val, "id"):
        return str(val.id)
    if hasattr(val, "ref") and getattr(val, "ref", None):
        return str(val.ref.id)
    return str(val)


async def handle_blog_view(instance: Any, **kwargs: Any) -> None:
    """
    Deduplicated blog view event listener.
    Increments view counter on Blog, registers new BlogView record.
    Author views are strictly skipped.
    """
    try:
        blog_id = _get_clean_id(instance)
        if not blog_id:
            return

        # Extract author
        author = None
        if isinstance(instance, dict):
            author = instance.get("author")
        else:
            author = getattr(instance, "author", None)

        author_id = _get_clean_id(author)

        # Extract user & request context
        user: User | None = kwargs.get("user")
        request: Request | None = kwargs.get("request")

        current_user_id = str(user.id) if user else None

        # Exclude author from view metrics
        if current_user_id and author_id and current_user_id == author_id:
            return

        # Capture IP address
        ip_address = None
        if request and hasattr(request, "client") and request.client:
            ip_address = request.client.host
        if not ip_address:
            ip_address = "unknown"

        # 15-minutes memory caching check
        now_ts = time.time()
        cache_key = f"{blog_id}:{current_user_id or ip_address}"

        # Clean cache memory regularly (loose threshold)
        if len(_recent_views_cache) > 10000:
            _recent_views_cache.clear()

        last_view_time = _recent_views_cache.get(cache_key)
        if last_view_time and (now_ts - last_view_time) < (15 * 60):
            return

        _recent_views_cache[cache_key] = now_ts

        # 15-minutes database check (cross-worker consistency)
        time_threshold = datetime.now(UTC) - timedelta(minutes=15)
        db_query: dict[str, Any] = {
            "blog.$id": ObjectId(blog_id),
            "created_at": {"$gte": time_threshold},
        }

        if current_user_id:
            db_query["user.$id"] = ObjectId(current_user_id)
        else:
            db_query["ip_address"] = ip_address

        # Check DB
        recent_view = await BlogView.get_pymongo_collection().find_one(db_query)
        if recent_view:
            return

        # Capture View record
        blog_ref = await Blog.get(blog_id)
        if not blog_ref:
            return

        new_view = BlogView(
            user=user,
            blog=blog_ref,
            ip_address=ip_address if ip_address != "unknown" else None,
        )
        await new_view.insert()

        # Atomically increment Blog views count
        await Blog.get_pymongo_collection().update_one(
            {"_id": ObjectId(blog_id)},
            {"$inc": {"views": 1}},
        )

    except Exception as exc:
        logger.exception("Failed to record blog view for %s: %s", getattr(instance, "id", "?"), exc)


def register_blog_hooks() -> None:
    """
    Registers all blogging signal listeners securely.
    Ensures safe hook reload by cleaning up identical older connectors.
    """
    # Safe cleanup to avoid double-firing during hot-reloads
    signals.on_view._handlers[Blog] = [
        h
        for h in signals.on_view._handlers.get(Blog, [])
        if getattr(h, "__name__", "") != "handle_blog_view"
    ]

    # Connect
    signals.on_view.connect(Blog, handle_blog_view)
    logger.info("Blogging signal hooks successfully registered.")
