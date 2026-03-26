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

# ── Configuration ────────────────────────────────────────────────────────
from .core.config import BackboneConfig
from .core.settings import Settings, settings

# ── Core Models ──────────────────────────────────────────────────────────
from .core.models import EventDocument, LogEntry, PasswordResetToken, Session, TaskLog, User

# ── Signals ──────────────────────────────────────────────────────────────
from .core.signals import Signal, signals

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
from .common.services import CacheService, background_task
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
    "TaskLog",
    "PasswordResetToken",
    # Signals
    "signals",
    "Signal",
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
    "background_task",
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
