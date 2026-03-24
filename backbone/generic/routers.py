"""
backbone.generic.routers
~~~~~~~~~~~~~~~~~~~~~~~~~

DRF-style router for Backbone views.

Supports both the new ``as_router()`` pattern and the legacy
constructor-based pattern.

Usage (new pattern)::

    backbone_router = BackboneRouter(prefix="/api/v1")
    backbone_router.register_view("/blogs", BlogView)
    app.include_router(backbone_router.get_router())

Usage (legacy pattern)::

    backbone_router = BackboneRouter(prefix="/api/v1")
    backbone_router.register("/blogs", BlogCrud)
    app.include_router(backbone_router.get_router())
"""

from __future__ import annotations

from typing import Any, Type

from fastapi import APIRouter


class BackboneRouter:
    """
    A DRF-style router for Backbone FastAPI.

    Aggregates multiple view routers into a single ``APIRouter``.

    Args:
        prefix: Global URL prefix for all registered views.
        tags: Default OpenAPI tags.
        **kwargs: Additional kwargs for the root ``APIRouter``.
    """

    def __init__(
        self,
        prefix: str = "",
        tags: list | None = None,
        **kwargs: Any,
    ) -> None:
        self.router = APIRouter(prefix=prefix, tags=tags, **kwargs)
        self.registry: list = []

    def register_view(
        self,
        prefix: str,
        view_class: Type[Any],
        tags: list | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Register a new-style view class (uses ``as_router()``).

        Args:
            prefix: URL prefix for this view.
            view_class: A ``GenericCrudView`` or similar class with
                an ``as_router()`` classmethod.
            tags: Optional OpenAPI tags.
            **kwargs: Additional kwargs passed to ``as_router()``.
        """
        if not prefix.startswith("/"):
            prefix = "/" + prefix

        view_router = view_class.as_router(prefix, tags=tags, **kwargs)
        self.router.include_router(view_router)
        self.registry.append(view_class)

    def register(
        self,
        prefix: str,
        viewset: Type[Any],
        basename: str | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Register a legacy constructor-based viewset.

        For backward compatibility with existing code.

        Args:
            prefix: URL prefix for this viewset.
            viewset: A legacy ``GenericCrud`` or similar class.
            basename: Optional name (unused, kept for compat).
            **kwargs: Additional kwargs for the viewset constructor.
        """
        if not prefix.startswith("/"):
            prefix = "/" + prefix

        instance = viewset(prefix=prefix, **kwargs)

        if hasattr(instance, "router"):
            self.router.include_router(instance.router)
        self.registry.append(instance)

    def get_router(self) -> APIRouter:
        """Return the aggregated ``APIRouter``."""
        return self.router
