"""
backbone
~~~~~~~~

Reusable open-source FastAPI framework — like Django REST Framework
but for FastAPI + MongoDB (Beanie).

Public API — import everything from here::

    from backbone import GenericCrudView, IsAuthenticated, BeanieRepository

Usage:

.. code-block:: python

    class BlogView(GenericCrudView):
        schema = Blog
    router.include_router(BlogView.as_router("/blogs"))
"""

import asyncio
import inspect
from datetime import datetime, timezone

# ── Configuration ────────────────────────────────────────────────────────
from .core.config import BackboneConfig
from .core.settings import Settings, settings

# ── Core Models ──────────────────────────────────────────────────────────
from .core.models import (
    EventDocument,
    LogEntry,
    Session,
    Task,
    User,
    Email,
    Store,
    TaskLog,          # Backward-compatible alias
    EmailDeliveryLog, # Backward-compatible alias
    BackboneStore,    # Backward-compatible alias
)

# ── Signals ──────────────────────────────────────────────────────────────
from .core.signals import Signal, signals
from .hooks import (
    on_create,
    on_update,
    on_delete,
    on_field_change,
    register_create_hook,
    register_update_hook,
    register_delete_hook,
    register_field_change_hook,
)

# ── Repository ───────────────────────────────────────────────────────────
from .core.repository import BeanieRepository

# ── Permissions ──────────────────────────────────────────────────────────
from .core.permissions import (
    AllowAny,
    BasePermission,
    IsAdminUser,
    IsAuthenticated,
    IsOwner,
    PermissionDependency,
)

# ── Mixins (Layer 2 — for power users) ──────────────────────────────────
from .core.mixins import (
    CreateMixin,
    DeleteMixin,
    ListMixin,
    RetrieveMixin,
    UpdateMixin,
    ViewContext,
)

# ── Generic Views (as_router) ───────────────────────────────────────────
from .generic.views import (
    GenericCreateView,
    GenericCrudView,
    GenericCustomApiView,
    GenericDeleteView,
    GenericListView,
    GenericFormView,
    GenericRetrieveView,
    GenericStatsView,
    GenericSubResourceView,
    GenericTemplateView,
    GenericUpdateView,
)

# ── Router Aggregation ───────────────────────────────────────────────────
from .generic.routers import BackboneRouter

# ── Schemas ──────────────────────────────────────────────────────────────
from .schemas import PaginatedResponse, TokenResponse, UserOut

# ── Auth ─────────────────────────────────────────────────────────────────
from .auth.router import AuthRouter

# ── Common Services & Utils ──────────────────────────────────────────────
from .common.services import CacheService, background_task, background_internal_task
from .common.utils import PasswordManager, TokenManager, logger
from .common.exceptions import (
    BackboneException,
    NotFoundException,
    ValidationException,
    AuthenticationException,
    PermissionException,
    ServiceException
)

# ── Admin ────────────────────────────────────────────────────────────────
from .admin import admin_site
from .email_sender import email_sender, EmailSender
from .db import db, BackboneDB

# Convenient alias for explicit store usage patterns:
#   await backbone.db_store.get("my_key")
db_store = db


async def _insert_log_entry(level: str, message: str, module: str, function: str, line: int, extra: dict):
    try:
        await LogEntry(
            level=level.upper(),
            message=message,
            module=module,
            function=function,
            line=line,
            extra=extra or None,
            created_at=datetime.now(timezone.utc),
        ).insert()
    except Exception:
        pass


def log(message: str, level: str = "info", **extra):
    """
    Public DB log helper.
    Inserts a LogEntry document directly (with `extra` payload).
    """
    frame = inspect.currentframe()
    caller = frame.f_back if frame else None
    module = caller.f_globals.get("__name__", "backbone.log") if caller else "backbone.log"
    function = caller.f_code.co_name if caller else "unknown"
    line = caller.f_lineno if caller else 0
    payload = str(message)
    extra_payload = dict(extra) if extra else {}

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_insert_log_entry(level, payload, module, function, line, extra_payload))
    except RuntimeError:
        try:
            asyncio.run(_insert_log_entry(level, payload, module, function, line, extra_payload))
        except Exception:
            pass

__all__ = [
    # Configuration
    "BackboneConfig",
    "settings",
    "Settings",
    # Models
    "User",
    "Session",
    "LogEntry",
    "EventDocument",
    "Task",
    "Email",
    "Store",
    # Signals
    "signals",
    "Signal",
    "on_create",
    "on_update",
    "on_delete",
    "on_field_change",
    "register_create_hook",
    "register_update_hook",
    "register_delete_hook",
    "register_field_change_hook",
    # Repository
    "BeanieRepository",
    # Permissions
    "BasePermission",
    "AllowAny",
    "IsAuthenticated",
    "IsAdminUser",
    "IsOwner",
    "PermissionDependency",
    # Mixins
    "ViewContext",
    "ListMixin",
    "CreateMixin",
    "RetrieveMixin",
    "UpdateMixin",
    "DeleteMixin",
    # Generic Views
    "GenericListView",
    "GenericCreateView",
    "GenericRetrieveView",
    "GenericUpdateView",
    "GenericDeleteView",
    "GenericCrudView",
    "GenericStatsView",
    "GenericSubResourceView",
    "GenericCustomApiView",
    "GenericTemplateView",
    "GenericFormView",
    # Router
    "BackboneRouter",
    # Schemas
    "UserOut",
    "PaginatedResponse",
    "TokenResponse",
    # Auth
    "AuthRouter",
    # Common
    "PasswordManager",
    "TokenManager",
    "CacheService",
    "log",
    "background_task",
    "background_internal_task",
    "email_sender",
    "EmailSender",
    "db",
    "db_store",
    "BackboneDB",
    "logger",
    "BackboneException",
    "NotFoundException",
    "ValidationException",
    "AuthenticationException",
    "PermissionException",
    "ServiceException",
    # Admin
    "admin_site",
]
