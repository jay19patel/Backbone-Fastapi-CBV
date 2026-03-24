"""
backbone.generic.views
~~~~~~~~~~~~~~~~~~~~~~

Generic view classes that combine mixins with route registration.

Route registration **only** happens here via the ``as_router()``
classmethod.  Mixins (in ``backbone.core.mixins``) contain zero routing
code.

Architecture:
    ``GenericListView``      — ListMixin + GET /
    ``GenericCreateView``    — CreateMixin + POST /
    ``GenericRetrieveView``  — RetrieveMixin + GET /{pk}
    ``GenericUpdateView``    — UpdateMixin + PATCH /{pk}
    ``GenericDeleteView``    — DeleteMixin + DELETE /{pk}
    ``GenericCrudView``      — all five combined
    ``GenericStatsView``     — aggregate stats endpoint
    ``GenericSubResourceView`` — array add/remove operations
    ``GenericCustomApiView`` — custom GET/POST endpoints

Usage::

    class BlogView(GenericCrudView):
        schema = Blog
        search_fields = ["title"]

    router.include_router(BlogView.as_router("/blogs"))
"""

from __future__ import annotations

import inspect
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Type

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from ..core.mixins import (
    CreateMixin,
    DeleteMixin,
    ListMixin,
    RetrieveMixin,
    UpdateMixin,
    ViewContext,
)
from ..core.permissions import AllowAny, BasePermission, PermissionDependency
from ..core.repository import BeanieRepository
from ..schemas import PaginatedResponse, UserOut
from ..utils.cache import CacheService, cache

logger = logging.getLogger("backbone.views")


# ── Helper Functions ────────────────────────────────────────────────────────

def _parse_sort(sort_string: Optional[str]) -> Optional[list]:
    """
    Parse a sort query parameter into MongoDB sort specification.

    Args:
        sort_string: Comma-separated field names. Prefix with ``-`` for
            descending. Example: ``"-created_at,title"``

    Returns:
        List of ``(field, direction)`` tuples, or ``None``.
    """
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
    """
    Scan a view instance for methods decorated with ``@action``
    and register them on the router.

    Args:
        view: The view instance to scan.
        router: The APIRouter to register actions on.
    """
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


# ── GenericListView ─────────────────────────────────────────────────────────

class GenericListView(ListMixin):
    """
    Ready-to-use list endpoint.  Extend and configure.

    Creates: ``GET /``

    Usage::

        class BlogListView(GenericListView):
            schema = Blog
            search_fields = ["title"]

        router.include_router(
            BlogListView.as_router("/blogs", tags=["Blogs"])
        )
    """

    @classmethod
    def as_router(
        cls,
        prefix: str,
        tags: Optional[List[str]] = None,
        **router_kwargs: Any,
    ) -> APIRouter:
        """
        Build and return a configured APIRouter with the list endpoint.

        Args:
            prefix: URL prefix (e.g., ``"/blogs"``).
            tags: OpenAPI tags.
            **router_kwargs: Additional kwargs for APIRouter.

        Returns:
            A configured ``APIRouter``.
        """
        view = cls()
        router = APIRouter(
            prefix=prefix,
            tags=tags or [prefix.strip("/")],
            **router_kwargs,
        )
        perm_dep = view.get_permission_dependency()

        cls._register_list_route(router, view, perm_dep)
        _register_actions(view, router)

        return router

    @staticmethod
    def _register_list_route(
        router: APIRouter,
        view: ListMixin,
        perm_dep: Callable,
    ) -> None:
        """Register the GET / list endpoint."""

        @router.get(
            "/",
            summary=f"List {view.schema.__name__} records",
        )
        async def list_view(
            request: Request,
            user: Any = Depends(perm_dep),
            page: int = Query(1, ge=1, description="Page number"),
            page_size: int = Query(10, ge=1, le=100, description="Items per page"),
            search: Optional[str] = Query(None, description="Search term"),
            sort: Optional[str] = Query(None, description="Sort field, prefix - for desc"),
        ) -> dict:
            await view.resolve_context(request)
            query = await view.get_queryset(request, user)
            query = await view.filter_queryset(query, request)
            results, total = await view.perform_list(
                query,
                page=page,
                page_size=page_size,
                sort=_parse_sort(sort),
            )
            return await view.format_list(results, total, page, page_size)


# ── GenericCreateView ───────────────────────────────────────────────────────

class GenericCreateView(CreateMixin):
    """
    Ready-to-use create endpoint.  Extend and configure.

    Creates: ``POST /``

    Usage::

        class BlogCreateView(GenericCreateView):
            schema = Blog

        router.include_router(
            BlogCreateView.as_router("/blogs", tags=["Blogs"])
        )
    """

    @classmethod
    def as_router(
        cls,
        prefix: str,
        tags: Optional[List[str]] = None,
        **router_kwargs: Any,
    ) -> APIRouter:
        """Build and return a configured APIRouter with the create endpoint."""
        view = cls()
        router = APIRouter(
            prefix=prefix,
            tags=tags or [prefix.strip("/")],
            **router_kwargs,
        )
        perm_dep = view.get_permission_dependency()

        cls._register_create_route(router, view, perm_dep)
        _register_actions(view, router)

        return router

    @staticmethod
    def _register_create_route(
        router: APIRouter,
        view: CreateMixin,
        perm_dep: Callable,
    ) -> None:
        """Register the POST / create endpoint."""
        create_schema = view.create_schema or view.schema
        response_schema = view.response_schema or view.schema

        async def create_view(
            request: Request,
            data: Any = Body(...),
            user: Any = Depends(perm_dep),
        ) -> Any:
            await view.resolve_context(request)

            # Extract and process link fields
            validated_data = _extract_create_data(view, data)

            # Prepare audit fields
            validated_data.update({
                "created_at": datetime.now(timezone.utc),
                "is_deleted": False,
            })
            if user:
                validated_data["created_by"] = str(user.id)

            # Execute hook chain: before → perform → after
            validated_data = await view.before_create(validated_data, user)
            instance = await view.perform_create(validated_data)
            instance = await view.after_create(instance, user)
            await view._invalidate_cache()

            return instance

        create_view.__annotations__["data"] = create_schema
        router.add_api_route(
            "/",
            create_view,
            methods=["POST"],
            response_model=response_schema,
            status_code=201,
            summary=f"Create {view.schema.__name__}",
        )


def _extract_create_data(view: ViewContext, data: Any) -> dict:
    """Extract and process create data, handling Link fields."""
    populate = view._get_populate_fields()

    # Preserve raw string IDs before model_dump converts them
    extracted_links = {}
    for field_name in populate:
        if hasattr(data, field_name):
            val = getattr(data, field_name)
            if val is not None:
                extracted_links[field_name] = val

    # Dump to dict
    validated = (
        data.model_dump(by_alias=True, exclude={"id"})
        if hasattr(data, "model_dump")
        else data
    )

    # Restore extracted links
    validated.update(extracted_links)

    # Convert string IDs to DBRefs
    return view._process_link_fields(validated)


# ── GenericRetrieveView ─────────────────────────────────────────────────────

class GenericRetrieveView(RetrieveMixin):
    """
    Ready-to-use retrieve endpoint.  Extend and configure.

    Creates: ``GET /{pk}``
    """

    @classmethod
    def as_router(
        cls,
        prefix: str,
        tags: Optional[List[str]] = None,
        **router_kwargs: Any,
    ) -> APIRouter:
        """Build and return a configured APIRouter with the retrieve endpoint."""
        view = cls()
        router = APIRouter(
            prefix=prefix,
            tags=tags or [prefix.strip("/")],
            **router_kwargs,
        )
        perm_dep = view.get_permission_dependency()

        cls._register_retrieve_route(router, view, perm_dep)
        _register_actions(view, router)

        return router

    @staticmethod
    def _register_retrieve_route(
        router: APIRouter,
        view: RetrieveMixin,
        perm_dep: Callable,
    ) -> None:
        """Register the GET /{pk} retrieve endpoint."""

        @router.get(
            "/{pk}",
            summary=f"Retrieve {view.schema.__name__}",
        )
        async def retrieve_view(
            request: Request,
            pk: str,
            user: Any = Depends(perm_dep),
        ) -> Any:
            await view.resolve_context(request)
            await view.before_retrieve(pk, request, user)
            instance = await view.perform_retrieve(pk, request, user)
            instance = await view.after_retrieve(instance, request, user)
            return instance


# ── GenericUpdateView ───────────────────────────────────────────────────────

class GenericUpdateView(UpdateMixin):
    """
    Ready-to-use update endpoint.  Extend and configure.

    Creates: ``PATCH /{pk}``
    """

    @classmethod
    def as_router(
        cls,
        prefix: str,
        tags: Optional[List[str]] = None,
        **router_kwargs: Any,
    ) -> APIRouter:
        """Build and return a configured APIRouter with the update endpoint."""
        view = cls()
        router = APIRouter(
            prefix=prefix,
            tags=tags or [prefix.strip("/")],
            **router_kwargs,
        )
        perm_dep = view.get_permission_dependency()

        cls._register_update_route(router, view, perm_dep)
        _register_actions(view, router)

        return router

    @staticmethod
    def _register_update_route(
        router: APIRouter,
        view: UpdateMixin,
        perm_dep: Callable,
    ) -> None:
        """Register the PATCH /{pk} update endpoint."""
        update_schema = view.update_schema or Dict[str, Any]

        async def update_view(
            request: Request,
            pk: str,
            data: Any = Body(...),
            user: Any = Depends(perm_dep),
        ) -> Any:
            await view.resolve_context(request)

            # Fetch the existing object + permission check
            instance = await view.get_object(pk, request, user)

            # Extract update data, strip dangerous fields
            update_data = _extract_update_data(view, data)

            # Add audit fields
            update_data["updated_at"] = datetime.now(timezone.utc)
            if user:
                update_data["updated_by"] = str(user.id)

            # Execute hook chain: before → perform → after
            update_data = await view.before_update(instance, update_data, user)
            result = await view.perform_update(instance, update_data)
            result = await view.after_update(result, user)
            await view._invalidate_cache()

            return result

        update_view.__annotations__["data"] = update_schema
        router.add_api_route(
            "/{pk}",
            update_view,
            methods=["PATCH"],
            response_model=view.response_schema,
            summary=f"Update {view.schema.__name__}",
        )


def _extract_update_data(view: ViewContext, data: Any) -> dict:
    """Extract update data, stripping dangerous and unknown fields."""
    raw = (
        data.model_dump(exclude_unset=True)
        if hasattr(data, "model_dump")
        else dict(data)
    )

    # Strip dangerous fields
    from ..core.mixins import DANGEROUS_FIELDS

    for field in DANGEROUS_FIELDS:
        raw.pop(field, None)

    # Process link fields
    return view._process_link_fields(raw)


# ── GenericDeleteView ───────────────────────────────────────────────────────

class GenericDeleteView(DeleteMixin):
    """
    Ready-to-use delete endpoint.  Extend and configure.

    Creates: ``DELETE /{pk}``
    """

    @classmethod
    def as_router(
        cls,
        prefix: str,
        tags: Optional[List[str]] = None,
        **router_kwargs: Any,
    ) -> APIRouter:
        """Build and return a configured APIRouter with the delete endpoint."""
        view = cls()
        router = APIRouter(
            prefix=prefix,
            tags=tags or [prefix.strip("/")],
            **router_kwargs,
        )
        perm_dep = view.get_permission_dependency()

        cls._register_delete_route(router, view, perm_dep)
        _register_actions(view, router)

        return router

    @staticmethod
    def _register_delete_route(
        router: APIRouter,
        view: DeleteMixin,
        perm_dep: Callable,
    ) -> None:
        """Register the DELETE /{pk} delete endpoint."""

        @router.delete(
            "/{pk}",
            status_code=204,
            summary=f"Delete {view.schema.__name__}",
        )
        async def delete_view(
            request: Request,
            pk: str,
            user: Any = Depends(perm_dep),
        ) -> None:
            await view.resolve_context(request)

            instance = await view.get_object(pk, request, user)

            should_proceed = await view.before_delete(instance, user)
            if not should_proceed:
                return None

            await view.perform_delete(instance)
            await view.after_delete(instance, user)
            await view._invalidate_cache()

            return None


# ── GenericCrudView (All Five Combined) ─────────────────────────────────────

class GenericCrudView(
    ListMixin,
    CreateMixin,
    RetrieveMixin,
    UpdateMixin,
    DeleteMixin,
):
    """
    Full CRUD view — provides all 5 standard endpoints.

    Endpoints created by ``as_router()``:
        ``GET    /``           → list
        ``POST   /``           → create
        ``GET    /{pk}``       → retrieve
        ``PATCH  /{pk}``       → update
        ``DELETE /{pk}``       → delete

    Minimal usage::

        class BlogView(GenericCrudView):
            schema = Blog

        router.include_router(BlogView.as_router("/blogs"))

    Full customisation::

        class BlogView(GenericCrudView):
            schema = Blog
            response_schema = BlogOut
            permission_classes = [IsAuthenticated]
            search_fields = ["title", "excerpt"]
            filter_fields = ["category.$id", "featured"]
            lookup_field = "slug"

            async def get_queryset(self, request, user):
                base = await super().get_queryset(request, user)
                return {**base, "isPublished": True}

            async def before_create(self, data, user):
                data["author"] = str(user.id)
                return data
    """

    @classmethod
    def as_router(
        cls,
        prefix: str,
        tags: Optional[List[str]] = None,
        **router_kwargs: Any,
    ) -> APIRouter:
        """
        Register all 5 CRUD routes on a single ``APIRouter``.

        Route registration happens here — never in ``__init__``.
        This means you can create the class anywhere and register
        it wherever you want, multiple times if needed.

        Args:
            prefix: URL prefix (e.g., ``"/blogs"``).
            tags: OpenAPI tags.
            **router_kwargs: Additional kwargs for APIRouter.

        Returns:
            A configured ``APIRouter`` with all CRUD endpoints.
        """
        view = cls()
        router = APIRouter(
            prefix=prefix,
            tags=tags or [prefix.strip("/")],
            **router_kwargs,
        )
        perm_dep = view.get_permission_dependency()

        # Register each route via private static methods
        GenericListView._register_list_route(router, view, perm_dep)
        GenericCreateView._register_create_route(router, view, perm_dep)
        GenericRetrieveView._register_retrieve_route(router, view, perm_dep)
        GenericUpdateView._register_update_route(router, view, perm_dep)
        GenericDeleteView._register_delete_route(router, view, perm_dep)

        # Register @action decorated methods
        _register_actions(view, router)

        return router


# ── GenericStatsView ────────────────────────────────────────────────────────

class GenericStatsView(ViewContext):
    """
    Generic view to fetch counts, sums, etc. for multiple models.

    Configuration via ``stats_config`` class attribute — a list of dicts::

        class DashboardStats(GenericStatsView):
            schema = Blog  # Required but only used for router setup
            stats_config = [
                {"name": "total_posts", "model": Blog, "type": "count",
                 "filters": {"is_deleted": False}},
                {"name": "total_views", "model": Blog, "type": "sum",
                 "field": "views", "filters": {"is_deleted": False}},
            ]

        router.include_router(
            DashboardStats.as_router("/stats", tags=["Dashboard"])
        )
    """

    stats_config: List[Dict[str, Any]] = []
    permission_classes = [AllowAny]

    @classmethod
    def as_router(
        cls,
        prefix: str,
        tags: Optional[List[str]] = None,
        **router_kwargs: Any,
    ) -> APIRouter:
        """Build and return a configured APIRouter with the stats endpoint."""
        view = cls()
        router = APIRouter(
            prefix=prefix,
            tags=tags or [prefix.strip("/")],
            **router_kwargs,
        )
        perm_dep = view.get_permission_dependency()

        @router.get("/", summary="Get aggregated statistics")
        async def stats_view(request: Request, user: Any = Depends(perm_dep)) -> dict:
            await view.resolve_context(request)
            return await view._compute_stats()

        return router

    async def _compute_stats(self) -> dict:
        """Compute all configured statistics."""
        results: dict = {}

        for config in self.stats_config:
            model = config["model"]
            stat_type = config.get("type", "count")
            filters = config.get("filters", {})
            name = config["name"]

            repo = BeanieRepository(self._repository.db if self._repository else None)
            repo.initialize(model)

            if stat_type == "count":
                results[name] = await repo.count(filters)
            elif stat_type == "sum":
                results[name] = await self._compute_sum(
                    model, config.get("field", ""), filters,
                )

        return results

    @staticmethod
    async def _compute_sum(
        model: type,
        field: str,
        filters: dict,
    ) -> int:
        """Compute a SUM aggregation for a field."""
        collection = model.get_pymongo_collection()
        pipeline = [
            {"$match": filters},
            {"$group": {"_id": None, "total": {"$sum": f"${field}"}}},
        ]
        agg_results = await collection.aggregate(pipeline).to_list(length=1)
        return (agg_results[0].get("total") or 0) if agg_results else 0


# ── GenericSubResourceView ──────────────────────────────────────────────────

class GenericSubResourceView(ViewContext):
    """
    Generic view for adding / removing items from an array field.

    Example::

        class PlaylistItemsView(GenericSubResourceView):
            schema = Playlist
            array_field = "blog_ids"
            target_id_param = "id"
            permission_classes = [IsAuthenticated]

        router.include_router(
            PlaylistItemsView.as_router("/playlists", tags=["Playlists"])
        )
    """

    array_field: str = ""
    target_id_param: str = "id"

    @classmethod
    def as_router(
        cls,
        prefix: str,
        tags: Optional[List[str]] = None,
        **router_kwargs: Any,
    ) -> APIRouter:
        """Build and return a configured APIRouter with add/remove endpoints."""
        view = cls()
        router = APIRouter(
            prefix=prefix,
            tags=tags or [prefix.strip("/")],
            **router_kwargs,
        )
        perm_dep = view.get_permission_dependency()

        cls._register_add_route(router, view, perm_dep)
        cls._register_remove_route(router, view, perm_dep)

        return router

    @staticmethod
    def _register_add_route(
        router: APIRouter,
        view: GenericSubResourceView,
        perm_dep: Callable,
    ) -> None:
        """Register the POST /{pk}/{array_field}/ add endpoint."""

        @router.post(
            "/{pk}/" + view.array_field + "/",
            status_code=200,
            summary=f"Add item to {view.array_field}",
        )
        async def add_item(
            request: Request,
            pk: str,
            data: Dict[str, Any] = Body(...),
            user: Any = Depends(perm_dep),
        ) -> dict:
            await view.resolve_context(request)
            instance = await view.get_object(pk, request, user)

            target_id = data.get(view.target_id_param)
            if not target_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing '{view.target_id_param}' in request body.",
                )

            from beanie import PydanticObjectId

            query = {"_id": PydanticObjectId(instance.get("id", instance.get("_id")))}
            await view._repository.update(
                query,
                {"$addToSet": {view.array_field: PydanticObjectId(target_id)}},
            )
            await view._invalidate_cache()
            return {"status": "success", "message": f"Added to {view.array_field}"}

    @staticmethod
    def _register_remove_route(
        router: APIRouter,
        view: GenericSubResourceView,
        perm_dep: Callable,
    ) -> None:
        """Register the DELETE /{pk}/{array_field}/{target_id}/ remove endpoint."""

        @router.delete(
            "/{pk}/" + view.array_field + "/{target_id}/",
            status_code=200,
            summary=f"Remove item from {view.array_field}",
        )
        async def remove_item(
            request: Request,
            pk: str,
            target_id: str,
            user: Any = Depends(perm_dep),
        ) -> dict:
            await view.resolve_context(request)
            instance = await view.get_object(pk, request, user)

            from beanie import PydanticObjectId

            query = {"_id": PydanticObjectId(instance.get("id", instance.get("_id")))}
            await view._repository.update(
                query,
                {"$pull": {view.array_field: PydanticObjectId(target_id)}},
            )
            await view._invalidate_cache()
            return {"status": "success", "message": f"Removed from {view.array_field}"}


# ── GenericCustomApiView ────────────────────────────────────────────────────

class GenericCustomApiView(ViewContext):
    """
    Generic view for building custom endpoints using Backbone permissions.

    Subclasses should override ``get()`` or ``post()``.

    Example::

        class SearchApiView(GenericCustomApiView):
            schema = Blog
            endpoint = "/search"
            permission_classes = [AllowAny]

            async def get(self, request, user):
                q = request.query_params.get("q", "")
                # ... custom logic
                return {"results": [...]}

        router.include_router(
            SearchApiView.as_router("/api", tags=["Search"])
        )
    """

    endpoint: str = ""

    @classmethod
    def as_router(
        cls,
        prefix: str,
        tags: Optional[List[str]] = None,
        **router_kwargs: Any,
    ) -> APIRouter:
        """Build and return a configured APIRouter with custom endpoints."""
        view = cls()
        router = APIRouter(
            prefix=prefix,
            tags=tags or [prefix.strip("/")],
            **router_kwargs,
        )
        perm_dep = view.get_permission_dependency()

        # Register GET if overridden
        if cls.get is not GenericCustomApiView.get:
            @router.get(view.endpoint)
            async def custom_get(
                request: Request,
                user: Any = Depends(perm_dep),
            ) -> Any:
                await view.resolve_context(request)
                return await view.get(request, user)

        # Register POST if overridden
        if cls.post is not GenericCustomApiView.post:
            @router.post(view.endpoint)
            async def custom_post(
                request: Request,
                data: Dict[str, Any] = Body(...),
                user: Any = Depends(perm_dep),
            ) -> Any:
                await view.resolve_context(request)
                return await view.post(request, data, user)

        return router

    async def get(self, request: Request, user: Any) -> Any:
        """Override in subclass to handle GET requests."""
        raise NotImplementedError("GET method not implemented")

    async def post(
        self,
        request: Request,
        data: Dict[str, Any],
        user: Any,
    ) -> Any:
        """Override in subclass to handle POST requests."""
        raise NotImplementedError("POST method not implemented")


# ── Backward Compatibility Aliases ──────────────────────────────────────────
# These allow existing code to import old names while transitioning

# Legacy constructor-based view classes
class BaseGenericView(ViewContext):
    """
    Legacy base class — use ``GenericCrudView`` with ``as_router()`` instead.

    Supports the old constructor-based API for backward compatibility.
    This allows existing code like ``GenericCrud(schema=Blog, prefix="/blogs")``
    to continue working during migration to the new ``as_router()`` pattern.
    """

    def __init__(
        self,
        schema: Optional[Type[BaseModel]] = None,
        prefix: str = "",
        tags: Optional[List[str]] = None,
        repository: Optional[BeanieRepository] = None,
        permission_classes: Any = None,
        list_fields: Optional[List[str]] = None,
        search_fields: Optional[List[str]] = None,
        filter_fields: Optional[List[str]] = None,
        ordering_fields: Optional[List[str]] = None,
        database: Optional[Any] = None,
        cache_ttl: int = 300,
        populate_fields: Optional[Dict[str, str]] = None,
        fetch_links: bool = False,
        rate_limit: Optional[Any] = None,
        lookup_field: str = "id",
        create_schema: Optional[Type[BaseModel]] = None,
        update_schema: Optional[Type[BaseModel]] = None,
        response_schema: Optional[Type[BaseModel]] = None,
        **kwargs: Any,
    ) -> None:
        from ..core.rate_limit import RateLimit

        self.prefix = prefix or getattr(self, "prefix", "")
        router_kwargs: dict = {
            "prefix": self.prefix,
            "tags": tags or [self.prefix.strip("/") if self.prefix else "default"],
        }

        if rate_limit is True:
            router_kwargs["dependencies"] = [Depends(RateLimit())]
        elif rate_limit:
            if isinstance(rate_limit, list):
                router_kwargs["dependencies"] = rate_limit
            else:
                router_kwargs["dependencies"] = [rate_limit]

        self.router = APIRouter(**router_kwargs)

        self.schema = schema or getattr(self.__class__, "schema", None)
        if not self.schema:
            raise ValueError("A schema must be provided or set as a class attribute.")

        self.create_schema = create_schema or getattr(self.__class__, "create_schema", None) or self.schema
        self.update_schema = update_schema or getattr(self.__class__, "update_schema", None) or Dict[str, Any]
        self.response_schema = response_schema or getattr(self.__class__, "response_schema", None) or self.schema
        self.cache_ttl = cache_ttl
        self.lookup_field = lookup_field

        self._repository = repository or BeanieRepository(database)
        self._repository.initialize(self.schema)

        self.search_fields = search_fields or getattr(self.__class__, "search_fields", [])
        self.filter_fields = filter_fields or getattr(self.__class__, "filter_fields", [])
        self.list_fields = list_fields or getattr(self.__class__, "list_fields", None)

        if permission_classes is not None:
            if not isinstance(permission_classes, (list, tuple)):
                self.permission_classes = [permission_classes]
            else:
                self.permission_classes = list(permission_classes)

        perm_dep = self.get_permission_dependency()
        self.perm_dep = perm_dep
        self._cache = None
        self.cache_service = None
        self.fetch_links = fetch_links
        self.populate_fields = populate_fields or {}

        if self.fetch_links:
            self.populate_fields.update(
                BeanieRepository.detect_populate_fields(self.schema),
            )

        self._register_actions()

    def _register_actions(self) -> None:
        """Scan for @action decorated methods and register them."""
        _register_actions(self, self.router)

    async def _resolve_context(self, request: Request) -> None:
        """Legacy method name — delegates to resolve_context."""
        await self.resolve_context(request)

    async def resolve_context(self, request: Request) -> None:
        """Ensure repository and cache are initialised."""
        config = request.app.state.backbone_config
        if self._repository.db is None:
            self._repository.db = config.database
        if not self._cache:
            self._cache = getattr(config, "cache_service", None)
            self.cache_service = self._cache


# Legacy view classes that use the constructor-based API
class GenericList(BaseGenericView, ListMixin):
    """Legacy list view — use ``GenericListView`` with ``as_router()`` instead."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._register_list_endpoint()

    def _register_list_endpoint(self) -> None:
        """Register the list route on self.router."""
        view = self

        list_response_model = PaginatedResponse[Any] if self.list_fields else PaginatedResponse[self.response_schema]

        @self.router.get("/", response_model=list_response_model)
        async def list_endpoint(
            request: Request,
            user: Optional[UserOut] = Depends(self.perm_dep),
            page: int = Query(1, ge=1),
            page_size: int = Query(10, ge=1, le=100),
            search: Optional[str] = None,
            sort: Optional[str] = None,
        ) -> dict:
            await view._resolve_context(request)
            query = await view.get_queryset(request, user)
            query = await view.filter_queryset(query, request)
            results, total = await view.perform_list(
                query,
                page=page,
                page_size=page_size,
                sort=_parse_sort(sort),
            )
            return await view.format_list(results, total, page, page_size)


class GenericCreate(BaseGenericView, CreateMixin):
    """Legacy create view — use ``GenericCreateView`` with ``as_router()`` instead."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._register_create_endpoint()

    def _register_create_endpoint(self) -> None:
        """Register the create route on self.router."""
        view = self
        create_schema = self.create_schema

        async def create_endpoint(
            request: Request,
            data: Any = Body(...),
            user: Optional[UserOut] = Depends(self.perm_dep),
        ) -> Any:
            await view._resolve_context(request)
            validated_data = _extract_create_data(view, data)
            validated_data.update({
                "created_at": datetime.now(timezone.utc),
                "is_deleted": False,
            })
            if user:
                validated_data["created_by"] = str(user.id)
            validated_data = await view.before_create(validated_data, user)
            instance = await view.perform_create(validated_data)
            instance = await view.after_create(instance, user)
            await view._invalidate_cache()
            return instance

        create_endpoint.__annotations__["data"] = create_schema
        cached_endpoint = cache(expire=30, include_ip=True, key_prefix=f"backbone:{self.prefix}:create")(create_endpoint)
        self.router.add_api_route("/", cached_endpoint, methods=["POST"], response_model=self.response_schema, status_code=201)


class GenericRetrieve(BaseGenericView, RetrieveMixin):
    """Legacy retrieve view — use ``GenericRetrieveView`` with ``as_router()`` instead."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._register_retrieve_endpoint()

    def _register_retrieve_endpoint(self) -> None:
        """Register the retrieve route on self.router."""
        view = self

        @self.router.get("/{pk}", response_model=self.response_schema)
        async def retrieve_endpoint(
            request: Request,
            pk: str,
            user: Optional[UserOut] = Depends(self.perm_dep),
        ) -> Any:
            await view._resolve_context(request)
            await view.before_retrieve(pk, request, user)
            instance = await view.perform_retrieve(pk, request, user)
            instance = await view.after_retrieve(instance, request, user)
            return instance


class GenericUpdate(BaseGenericView, UpdateMixin):
    """Legacy update view — use ``GenericUpdateView`` with ``as_router()`` instead."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._register_update_endpoint()

    def _register_update_endpoint(self) -> None:
        """Register the update route on self.router."""
        view = self
        update_schema = self.update_schema

        async def update_endpoint(
            request: Request,
            pk: str,
            data: Any = Body(...),
            user: UserOut = Depends(self.perm_dep),
        ) -> Any:
            await view._resolve_context(request)
            instance = await view.get_object(pk, request, user)
            update_data = _extract_update_data(view, data)
            update_data["updated_at"] = datetime.now(timezone.utc)
            if user:
                update_data["updated_by"] = str(user.id)
            update_data = await view.before_update(instance, update_data, user)
            result = await view.perform_update(instance, update_data)
            result = await view.after_update(result, user)
            await view._invalidate_cache()
            return result

        update_endpoint.__annotations__["data"] = update_schema
        self.router.add_api_route("/{pk}", update_endpoint, methods=["PATCH"], response_model=self.response_schema)


class GenericDelete(BaseGenericView, DeleteMixin):
    """Legacy delete view — use ``GenericDeleteView`` with ``as_router()`` instead."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._register_delete_endpoint()

    def _register_delete_endpoint(self) -> None:
        """Register the delete route on self.router."""
        view = self

        @self.router.delete("/{pk}", status_code=204)
        async def delete_endpoint(
            request: Request,
            pk: str,
            user: UserOut = Depends(self.perm_dep),
        ) -> None:
            await view._resolve_context(request)
            instance = await view.get_object(pk, request, user)
            should_proceed = await view.before_delete(instance, user)
            if not should_proceed:
                return None
            await view.perform_delete(instance)
            await view.after_delete(instance, user)
            await view._invalidate_cache()
            return None


class GenericCrud(GenericList, GenericCreate, GenericRetrieve, GenericUpdate, GenericDelete):
    """
    Legacy combined CRUD view — use ``GenericCrudView`` with ``as_router()`` instead.

    Maintains backward compatibility with the constructor-based API.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        BaseGenericView.__init__(self, *args, **kwargs)
        self._register_list_endpoint()
        self._register_create_endpoint()
        self._register_retrieve_endpoint()
        self._register_update_endpoint()
        self._register_delete_endpoint()


class GenericStats(BaseGenericView):
    """
    Legacy stats view — use ``GenericStatsView`` with ``as_router()`` instead.

    Fixed: NameError on ``agg_results`` — now properly defines local variable.
    """

    def __init__(
        self,
        stats_config: List[Dict[str, Any]],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("permission_classes", [AllowAny])
        super().__init__(*args, **kwargs)
        self.stats_config = stats_config
        self._register_stats_route()

    def _register_stats_route(self) -> None:
        """Register the stats endpoint."""
        view = self

        @self.router.get("/", tags=self.router.tags)
        async def get_stats(request: Request) -> dict:
            await view._resolve_context(request)
            results: dict = {}

            for config in view.stats_config:
                model = config["model"]
                stat_type = config.get("type", "count")
                filters = config.get("filters", {})
                name = config["name"]

                repo = BeanieRepository(view._repository.db)
                repo.initialize(model)

                if stat_type == "count":
                    results[name] = await repo.count(filters)
                elif stat_type == "sum":
                    field = config.get("field")
                    collection = model.get_pymongo_collection()
                    pipeline = [
                        {"$match": filters},
                        {"$group": {"_id": None, "total": {"$sum": f"${field}"}}},
                    ]
                    agg_results = await collection.aggregate(pipeline).to_list(length=1)
                    results[name] = (agg_results[0].get("total") or 0) if agg_results else 0

            return results

        return get_stats


class GenericSubResource(BaseGenericView):
    """Legacy sub-resource view — use ``GenericSubResourceView`` with ``as_router()`` instead."""

    def __init__(
        self,
        array_field: str,
        target_id_param: str = "id",
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.array_field = array_field
        self.target_id_param = target_id_param
        self._register_array_routes()

    def _register_array_routes(self) -> None:
        """Register add/remove array routes."""
        from beanie import PydanticObjectId

        view = self

        @self.router.post("/{pk}/" + self.array_field + "/", status_code=200)
        async def add_item(
            request: Request,
            pk: str,
            data: Dict[str, Any] = Body(...),
            user: Optional[UserOut] = Depends(self.perm_dep),
        ) -> dict:
            await view._resolve_context(request)
            item = await view.get_object(pk, request, user)

            target_id = data.get(view.target_id_param)
            if not target_id:
                raise HTTPException(status_code=400, detail=f"Missing {view.target_id_param}")

            item_id = item.get("id") or item.get("_id")
            query = {"_id": PydanticObjectId(item_id)}
            await view._repository.update(
                query,
                {"$addToSet": {view.array_field: PydanticObjectId(target_id)}},
            )
            await view._invalidate_cache()
            return {"status": "success", "message": f"Added to {view.array_field}"}

        @self.router.delete("/{pk}/" + self.array_field + "/{target_id}/", status_code=200)
        async def remove_item(
            request: Request,
            pk: str,
            target_id: str,
            user: Optional[UserOut] = Depends(self.perm_dep),
        ) -> dict:
            await view._resolve_context(request)
            item = await view.get_object(pk, request, user)

            item_id = item.get("id") or item.get("_id")
            query = {"_id": PydanticObjectId(item_id)}
            await view._repository.update(
                query,
                {"$pull": {view.array_field: PydanticObjectId(target_id)}},
            )
            await view._invalidate_cache()
            return {"status": "success", "message": f"Removed from {view.array_field}"}


class GenericCustomApi(BaseGenericView):
    """Legacy custom API view — use ``GenericCustomApiView`` with ``as_router()`` instead."""

    def __init__(
        self,
        endpoint: str = "",
        *args: Any,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("permission_classes", [AllowAny])
        super().__init__(*args, **kwargs)
        self.endpoint = endpoint
        self._register_custom_routes()

    def _register_custom_routes(self) -> None:
        """Register custom GET/POST routes."""
        view = self

        if type(self).get != GenericCustomApi.get:
            @self.router.get(self.endpoint, tags=self.router.tags)
            async def custom_get(
                request: Request,
                user: Optional[UserOut] = Depends(self.perm_dep),
            ) -> Any:
                await view._resolve_context(request)
                return await view.get(request, user)

        if type(self).post != GenericCustomApi.post:
            @self.router.post(self.endpoint, tags=self.router.tags)
            async def custom_post(
                request: Request,
                data: Dict[str, Any] = Body(...),
                user: Optional[UserOut] = Depends(self.perm_dep),
            ) -> Any:
                await view._resolve_context(request)
                return await view.post(request, data, user)

    async def get(self, request: Request, user: Optional[UserOut]) -> Any:
        """Override in subclass."""
        raise NotImplementedError("GET method not implemented")

    async def post(
        self,
        request: Request,
        data: Dict[str, Any],
        user: Optional[UserOut],
    ) -> Any:
        """Override in subclass."""
        raise NotImplementedError("POST method not implemented")
