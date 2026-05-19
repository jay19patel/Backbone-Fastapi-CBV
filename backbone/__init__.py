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
from datetime import UTC, datetime

# ── Admin ────────────────────────────────────────────────────────────────
from .admin import admin_site

# ── Auth ─────────────────────────────────────────────────────────────────
from .auth.router import AuthRouter
from .common.exceptions import (
    AuthenticationException,
    BackboneException,
    NotFoundException,
    PermissionException,
    ServiceException,
    ValidationException,
)

# ── Common Services & Utils ──────────────────────────────────────────────
from .common.services import CacheService, background_internal_task, background_task
from .common.utils import PasswordManager, TokenManager, logger

# ── Configuration ────────────────────────────────────────────────────────
from .core.config import BackboneConfig

# ── Mixins (Layer 2 — for power users) ──────────────────────────────────
from .core.mixins import (
    CreateMixin,
    DeleteMixin,
    ListMixin,
    RetrieveMixin,
    UpdateMixin,
    ViewContext,
)

# ── Core Models ──────────────────────────────────────────────────────────
from .core.models import (
    BackboneStore,  # Backward-compatible alias
    Email,
    EmailDeliveryLog,  # Backward-compatible alias
    EventDocument,
    LogEntry,
    Session,
    Store,
    Task,
    TaskLog,  # Backward-compatible alias
    User,
)

# ── Permissions ──────────────────────────────────────────────────────────
from .core.permissions import (
    AllowAny,
    BasePermission,
    IsAdminUser,
    IsAuthenticated,
    IsOwner,
    PermissionDependency,
)

# ── Repository ───────────────────────────────────────────────────────────
from .core.repository import BeanieRepository
from .core.settings import Settings, settings

# ── Signals ──────────────────────────────────────────────────────────────
from .core.signals import Signal, signals
from .db import BackboneDB, db
from .email_sender import EmailSender, email_sender

# ── Router Aggregation ───────────────────────────────────────────────────
from .generic.routers import BackboneRouter

# ── Generic Views (as_router) ───────────────────────────────────────────
from .generic.views import (
    GenericCreateView,
    GenericCrudView,
    GenericCustomApiView,
    GenericDeleteView,
    GenericFormView,
    GenericListView,
    GenericRetrieveView,
    GenericStatsView,
    GenericSubResourceView,
    GenericTemplateView,
    GenericUpdateView,
)
from .hooks import (
    on_create,
    on_delete,
    on_field_change,
    on_update,
    register_create_hook,
    register_delete_hook,
    register_field_change_hook,
    register_update_hook,
)

# ── Schemas ──────────────────────────────────────────────────────────────
from .schemas import PaginatedResponse, TokenResponse, UserOut

# Convenient alias for explicit store usage patterns:
#   await backbone.db_store.get("my_key")
db_store = db


async def _insert_log_entry(
    level: str, message: str, module: str, function: str, line: int, extra: dict
):
    try:
        await LogEntry(
            level=level.upper(),
            message=message,
            module=module,
            function=function,
            line=line,
            extra=extra or None,
            created_at=datetime.now(UTC),
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
    "TaskLog",
    "Email",
    "EmailDeliveryLog",
    "Store",
    "BackboneStore",
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
