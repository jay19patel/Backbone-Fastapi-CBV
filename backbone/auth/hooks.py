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
        from .service import AuthService
        auth_service = AuthService(request)
        
        # Determine verification URL
        from ..core.config import BackboneConfig
        backbone_config = BackboneConfig.get_instance()
        frontend_verify_url = getattr(backbone_config.config, "FRONTEND_VERIFY_URL", "http://localhost:3000/verify-email")
        
        # Generate token and full verification link
        token = await auth_service.create_verification_request(instance)
        verification_url = f"{frontend_verify_url}?token={token}"
        
        # Send Welcome Email (now includes verification link)
        await auth_service.send_welcome_email(instance, verification_url=verification_url)
    except Exception:
        logger.exception("Failed to send welcome email for user=%s", email)




def register_auth_hooks() -> None:
    register_create_hook(User, send_registration_email_on_user_create)
