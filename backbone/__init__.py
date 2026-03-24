"""
backbone
~~~~~~~~

Reusable open-source FastAPI framework — like Django REST Framework
but for FastAPI + MongoDB (Beanie).

Public API — import everything from here::

    from backbone import GenericCrudView, IsAuthenticated, BeanieRepository

Two patterns are supported:

**New pattern (recommended):**

.. code-block:: python

    class BlogView(GenericCrudView):
        schema = Blog
    router.include_router(BlogView.as_router("/blogs"))

**Legacy pattern (backward compatible):**

.. code-block:: python

    blog_crud = GenericCrud(schema=Blog, prefix="/blogs")
    router.include_router(blog_crud.router)
"""

# ── Configuration ────────────────────────────────────────────────────────
from .core.config import BackboneConfig
from .core.settings import Settings, settings

# ── Core Models ──────────────────────────────────────────────────────────
from .core.models import EventDocument, LogEntry, Session, TaskLog, User

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

# ── Generic Views — New Pattern (as_router) ──────────────────────────────
from .generic.views import (
    GenericCreateView,
    GenericCrudView,
    GenericCustomApiView,
    GenericDeleteView,
    GenericListView,
    GenericRetrieveView,
    GenericStatsView,
    GenericSubResourceView,
    GenericUpdateView,
)

# ── Generic Views — Legacy Pattern (constructor) ─────────────────────────
from .generic.views import (
    BaseGenericView,
    GenericCreate,
    GenericCrud,
    GenericCustomApi,
    GenericDelete,
    GenericList,
    GenericRetrieve,
    GenericStats,
    GenericSubResource,
    GenericUpdate,
)

# ── Router Aggregation ───────────────────────────────────────────────────
from .generic.routers import BackboneRouter

# ── Schemas ──────────────────────────────────────────────────────────────
from .schemas import PaginatedResponse, TokenResponse, UserOut

# ── Auth ─────────────────────────────────────────────────────────────────
from .auth.router import AuthRouter

# ── Utilities ────────────────────────────────────────────────────────────
from .utils import PasswordManager, TokenManager
from .utils.cache import CacheService
from .utils.tasks import background_task

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
    # New Views (as_router pattern)
    "GenericListView",
    "GenericCreateView",
    "GenericRetrieveView",
    "GenericUpdateView",
    "GenericDeleteView",
    "GenericCrudView",
    "GenericStatsView",
    "GenericSubResourceView",
    "GenericCustomApiView",
    # Legacy Views (constructor pattern)
    "BaseGenericView",
    "GenericList",
    "GenericCreate",
    "GenericRetrieve",
    "GenericUpdate",
    "GenericDelete",
    "GenericCrud",
    "GenericStats",
    "GenericSubResource",
    "GenericCustomApi",
    # Router
    "BackboneRouter",
    # Schemas
    "UserOut",
    "PaginatedResponse",
    "TokenResponse",
    # Auth
    "AuthRouter",
    # Utilities
    "PasswordManager",
    "TokenManager",
    "CacheService",
    "background_task",
    # Admin
    "admin_site",
]
