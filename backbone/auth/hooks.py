"""Auth-related signal hooks."""

from __future__ import annotations

import logging
from typing import Any

from ..core.models import User
from ..core.settings import settings
from ..hooks import register_create_hook

logger = logging.getLogger("backbone.auth.hooks")


def _build_login_url(request: Any = None) -> str:
    if request is not None:
        try:
            return str(request.base_url).rstrip("/") + "/login"
        except Exception:
            pass

    origins = getattr(settings, "cors_origins_list", []) or []
    if origins:
        return origins[0].rstrip("/") + "/login"
    return "http://localhost:3000/login"


async def send_registration_email_on_user_create(instance: Any, request: Any = None, **kwargs) -> None:
    if not isinstance(instance, User):
        return
    if getattr(instance, "is_deleted", False):
        return

    email = (getattr(instance, "email", "") or "").strip()
    if not email:
        return

    full_name = (getattr(instance, "full_name", "") or email.split("@")[0]).strip()
    login_url = _build_login_url(request)

    try:
        from ..email_sender import email_sender

        await email_sender.queue_registration_emails(
            to_email=email,
            full_name=full_name,
            login_url=login_url,
        )
    except Exception:
        logger.exception("Failed to queue registration emails for user=%s", email)


def register_auth_hooks() -> None:
    register_create_hook(User, send_registration_email_on_user_create)
