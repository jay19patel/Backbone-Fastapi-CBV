"""
backbone.core.mixins
~~~~~~~~~~~~~~~~~~~~

Pure-behaviour mixins for Backbone views.

This module contains the view context and all CRUD mixins.  **No routing
code lives here** — route registration is the responsibility of the
generic view classes in ``backbone.generic.views``.

Architecture:
    ``ViewContext`` → shared state (schema, repo, cache, perms)
    ``ListMixin``   → paginated list with search & filter hooks
    ``CreateMixin`` → object creation with before/perform/after hooks
    ``RetrieveMixin`` → single-object retrieval
    ``UpdateMixin``   → partial update with allowed-fields guard
    ``DeleteMixin``   → soft-delete with cancellation support

Every write operation follows the **before → perform → after** pattern,
making it easy to extend behaviour via method overrides without touching
the core flow.

Design decisions:
    • Search input is **always escaped** with ``re.escape()`` to prevent
      ReDoS attacks.
    • ``ViewContext.get_permission_dependency()`` auto-derives auth needs
      from ``permission_classes`` — no ``use_auth`` flag.
    • ``filter_queryset()`` supports ``__ne``, ``__in``, ``__gt``, etc.
      Django-style lookups via query parameters.
"""

from __future__ import annotations

import logging
import hashlib
import json
import re
from datetime import datetime, timezone
from math import ceil
from typing import Any, Callable, ClassVar, Dict, List, Optional, Type
from urllib.parse import unquote

from beanie import Document, PydanticObjectId
from fastapi import HTTPException, Request
from pydantic import BaseModel

from ..schemas import UserOut
from ..common.services import CacheService
from .permissions import (
    AllowAny,
    BasePermission,
    PermissionDependency,
)
from .repository import BeanieRepository

logger = logging.getLogger("backbone.mixins")

# ── Constants ───────────────────────────────────────────────────────────────

# Query parameter names reserved by the framework
RESERVED_QUERY_PARAMS = frozenset({
    "page", "page_size", "search", "sort", "skip", "limit",
})

# Fields that must never be accepted from user input
DANGEROUS_FIELDS = frozenset({
    "is_superuser", "is_staff", "is_active",
    "hashed_password", "password",
})

# Fields managed internally — excluded from user-facing updates
AUDIT_FIELDS = frozenset({
    "created_at", "updated_at", "deleted_at",
    "created_by", "updated_by", "deleted_by",
    "is_deleted",
})


# ── ViewContext (Shared State) ──────────────────────────────────────────────

class ViewContext:
    """
    Shared configuration and utilities for all view mixins.

    This class holds configuration (schema, permissions, etc.) and provides
    helper methods used across all mixins.  It does **NOT** register any
    routes — that is ``GenericView``'s job.

    Class Attributes (set on your subclass):
        schema:             Beanie Document class (**required**)
        response_schema:    Pydantic model for output shaping (optional)
        repository_class:   Repository implementation (default: BeanieRepository)
        permission_classes: List of permission classes (default: [AllowAny])
        lookup_field:       Field for single-object lookup (default: ``"id"``)
        search_fields:      Fields searched via ``?search=`` param
        filter_fields:      Fields allowed in ``?field=value`` query params
        list_fields:        Fields to project in list responses (optional)
        fetch_links:        Auto-populate Beanie Link fields (default: False)
        cache_ttl:          Cache TTL in seconds (default: 300)

    Example::

        class BlogView(GenericCrudView):
            schema = Blog
            permission_classes = [IsAuthenticated]
            search_fields = ["title", "excerpt"]
    """

    # ── Required ─────────────────────────────────────────────────────────
    schema: ClassVar[Type[Document]]

    # ── Optional overrides ───────────────────────────────────────────────
    response_schema: ClassVar[Optional[Type[BaseModel]]] = None
    create_schema: ClassVar[Optional[Type[BaseModel]]] = None
    update_schema: ClassVar[Optional[Type[BaseModel]]] = None
    repository_class: ClassVar[type] = BeanieRepository
    permission_classes: ClassVar[list] = [AllowAny]
    lookup_field: ClassVar[str] = "id"
    search_fields: ClassVar[List[str]] = []
    filter_fields: ClassVar[List[str]] = []
    list_fields: ClassVar[Optional[List[str]]] = None
    fetch_links: ClassVar[bool] = False
    # If True, the document will be re-fetched with links populated before being returned in a Create/Update response.
    # WARNING: This may cause ResponseValidationError if the response_model expects strings for these links.
    populate_links_on_save: ClassVar[bool] = False
    
    cache_ttl: ClassVar[int] = 300
    populate_fields: ClassVar[Optional[Dict[str, Any]]] = None

    # ── Internal — do not override ───────────────────────────────────────
    _repository: Optional[BeanieRepository] = None
    _cache: Optional[CacheService] = None

    # ── Context Resolution ───────────────────────────────────────────────

    async def resolve_context(self, request: Request) -> None:
        """
        Lazily initialise repository and cache from app state.

        Called automatically before every request — do not call manually.
        This ensures the repository has the correct database reference and
        the cache service is available.

        Args:
            request: The incoming FastAPI Request.
        """
        config = request.app.state.backbone_config

        if self._repository is None:
            self._repository = self.repository_class()
            self._repository.initialize(self.schema)

        if self._repository.db is None:
            self._repository.db = config.database

        if self._cache is None:
            self._cache = getattr(config, "cache_service", None)

    # ── Permission Dependency ────────────────────────────────────────────

    def get_permission_dependency(self) -> Callable:
        """
        Return a FastAPI ``Depends()`` function based on ``permission_classes``.

        Automatically uses ``get_current_user`` if any permission requires
        authentication, ``get_optional_user`` otherwise.

        Returns:
            An async callable suitable for ``Depends()``.
        """
        return PermissionDependency(self.permission_classes)

    # ── Object Retrieval ─────────────────────────────────────────────────

    async def get_object(
        self,
        pk: str,
        request: Request,
        user: Any,
    ) -> dict:
        """
        Fetch a single object by primary key using ``self.lookup_field``.

        Runs all object-level permission checks.

        Override this to customise object lookup::

            async def get_object(self, pk, request, user):
                obj = await super().get_object(pk, request, user)
                if obj["owner"] != str(user.id):
                    raise HTTPException(403, "Not your resource")
                return obj

        Args:
            pk: The primary key value (string).
            request: The incoming Request.
            user: The current user (or ``None``).

        Returns:
            The document as a dict.

        Raises:
            HTTPException(404): If the object is not found.
            HTTPException(403): If object-level permissions deny access.
        """
        query = self._build_lookup_query(pk)
        item = await self._repository.get_one(
            query,
            populate_fields=self._get_populate_fields(),
        )

        if not item:
            raise HTTPException(
                status_code=404,
                detail=f"{self.schema.__name__} not found.",
            )

        await self._check_object_permissions(request, user, item)
        return item

    async def _check_object_permissions(
        self,
        request: Request,
        user: Any,
        obj: Any,
    ) -> None:
        """Run object-level permission checks."""
        for perm_class in self.permission_classes:
            perm = perm_class(request, user)
            if not await perm.has_object_permission(obj):
                raise HTTPException(
                    status_code=403,
                    detail="Object-level access denied.",
                )

    # ── Internal Helpers ─────────────────────────────────────────────────

    def _build_lookup_query(self, pk: str) -> dict:
        """
        Build a query to find an object by PK using lookup_field.
        Smart lookup: Only adds 'id' to the query if 'pk' looks like an ObjectId.
        """
        query = {"is_deleted": False}
        
        if self.lookup_field == "id" or self.lookup_field == "_id":
            query["id"] = pk
            return query

        # Check if pk looks like an ObjectId (24 hex chars)
        is_oid = len(pk) == 24 and all(c in "0123456789abcdefABCDEF" for c in pk)
        
        if is_oid:
            query["$or"] = [{self.lookup_field: pk}, {"id": pk}]
        else:
            query[self.lookup_field] = pk
            
        return query

    def _get_populate_fields(self) -> Dict[str, Any]:
        """Return the populate_fields config, auto-detecting if fetch_links is set."""
        fields = dict(self.populate_fields or {})
        if self.fetch_links:
            fields.update(BeanieRepository.detect_populate_fields(self.schema))
        return fields

    def _get_projection(self) -> Optional[Dict[str, int]]:
        """Build a projection dict from list_fields."""
        if not self.list_fields:
            return None
        projection = {field: 1 for field in self.list_fields}
        projection["_id"] = 1
        return projection

    async def _invalidate_cache(self) -> None:
        """Clear cached data for this view's prefix."""
        if self._cache and self._cache.enabled:
            pattern = f"{self._cache_namespace}:*"
            await self._cache.delete_pattern(pattern)

    @property
    def _cache_namespace(self) -> str:
        settings_name = getattr(getattr(self.schema, "Settings", None), "name", None)
        return f"backbone:{settings_name or self.schema.__name__.lower()}"

    def _build_cache_key(self, operation: str, payload: Dict[str, Any]) -> str:
        raw = json.dumps(payload, sort_keys=True, default=str)
        digest = hashlib.md5(raw.encode()).hexdigest()
        return f"{self._cache_namespace}:{operation}:{digest}"

    def _serialize_response(self, data: Any) -> Any:
        if data is None:
            return None
        if self._repository is None:
            return data
        return self._repository.serialize_document(data)

    async def _process_link_fields(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert string IDs in the payload into MongoDB DBRef objects for
        Beanie Link fields. Also automatically detects Base64 image data
        and handles attachment creation.

        Args:
            payload: The request data dict.

        Returns:
            The modified payload with DBRef values for Link fields.
        """
        populate = self._get_populate_fields()

        for field_name, config in populate.items():
            if field_name not in payload or not payload[field_name]:
                continue

            val = payload[field_name]
            collection_name = config.get("collection") if isinstance(config, dict) else config
            if not collection_name:
                continue

            # --- Automated Media Handling ---
            # If it looks like Base64 data and targets the attachments collection, handle it automatically
            if collection_name == "attachments" and isinstance(val, str) and val.startswith("data:"):
                attachment = await self._handle_base64_attachment(field_name, val)
                if attachment:
                    payload[field_name] = attachment
                    continue

            # Handle gallery/list of links
            if isinstance(val, list):
                processed_list = []
                for item in val:
                    if isinstance(item, str) and item.startswith("data:"):
                        att = await self._handle_base64_attachment(field_name, item)
                        if att: processed_list.append(att)
                    else:
                        processed_list.append(item)
                val = processed_list

            try:
                payload[field_name] = self._convert_to_dbref(val, collection_name)
            except Exception:
                pass

        return payload

    async def _handle_base64_attachment(self, field_name: str, base64_data: str) -> Optional[Any]:
        """
        Internal helper to create an Attachment record from Base64 data
        and queue the background file storage task.
        """
        try:
            from .models import Attachment
            from .media import process_attachment_upload
            from .config import BackboneConfig
            from beanie import PydanticObjectId
            import mimetypes

            # Determine file extension from data URI
            ext = "bin"
            if "image/png" in base64_data: ext = "png"
            elif "image/jpeg" in base64_data: ext = "jpg"
            elif "image/webp" in base64_data: ext = "webp"
            
            # Extract clean encoded data
            if "," in base64_data:
                encoded = base64_data.split(",")[1]
            else:
                encoded = base64_data

            # Create the Attachment record (status: pending)
            filename = f"pending_{PydanticObjectId()}.{ext}"
            
            # Use self.schema name for folder organization
            collection_name = getattr(getattr(self.schema, "Settings", None), "name", self.schema.__name__.lower())
            
            attachment = Attachment(
                filename=filename,
                content_type=mimetypes.guess_type(filename)[0] or "application/octet-stream",
                status="pending",
                collection_name=collection_name,
                field_name=field_name
            )
            await attachment.insert()
            
            # 5. Queue background processing task
            config = BackboneConfig.get_instance()
            
            # Use the internal task queue to process the upload
            if hasattr(config, "internal_task_queue") and config.internal_task_queue.enabled:
                await config.internal_task_queue.enqueue(
                    process_attachment_upload,
                    str(attachment.id),
                    encoded
                )
            else:
                # If workers are disabled, we might want to process synchronously 
                # or just log a warning. For now, we trust the queue.
                logger.warning("Could not enqueue media processing task: Task queue disabled or missing.")
            
            return attachment
        except Exception as e:
            logger.error(f"Failed to auto-handle base64 attachment for {field_name}: {e}")
            return None

    @staticmethod
    def _convert_to_dbref(val: Any, collection_name: str) -> Any:
        """Convert a value to DBRef(s) for a Link field."""
        from bson import ObjectId as BsonObjectId
        from bson.dbref import DBRef

        if isinstance(val, str) and len(val) == 24:
            return DBRef(collection=collection_name, id=BsonObjectId(val))

        if isinstance(val, list):
            result = []
            for item in val:
                if isinstance(item, str) and len(item) == 24:
                    result.append(DBRef(collection=collection_name, id=BsonObjectId(item)))
                elif isinstance(item, dict) and "id" in item:
                    result.append(DBRef(collection=collection_name, id=BsonObjectId(item["id"])))
                else:
                    result.append(item)
            return result

        if isinstance(val, dict) and "id" in val:
            return DBRef(collection=collection_name, id=BsonObjectId(val["id"]))

        return val


# ── ListMixin ───────────────────────────────────────────────────────────────

class ListMixin(ViewContext):
    """
    Provides paginated list behaviour for ``GET /`` endpoint.

    Hook execution order:
        1. ``get_queryset()``     — build base query
        2. ``filter_queryset()``  — apply request filters & search
        3. ``perform_list()``     — hit the database
        4. ``format_list()``      — shape the response

    To customise, override any hook in your view class.  You do **NOT**
    need to override the full ``list()`` flow.
    """

    async def get_queryset(
        self,
        request: Request,
        user: Any,
    ) -> dict:
        """
        Return the base MongoDB query dict for this view.

        Override to scope results (e.g., filter by current user)::

            async def get_queryset(self, request, user):
                base = await super().get_queryset(request, user)
                return {**base, "owner": str(user.id)}

        Args:
            request: The incoming Request.
            user: The current user (or ``None``).

        Returns:
            A MongoDB query dict.
        """
        return {"is_deleted": {"$ne": True}}

    async def filter_queryset(
        self,
        query: dict,
        request: Request,
    ) -> dict:
        """
        Apply search and filter parameters from the request URL.

        Search uses ``re.escape()`` to prevent ReDoS attacks.

        Override to add custom filter logic::

            async def filter_queryset(self, query, request):
                query = await super().filter_queryset(query, request)
                query["is_published"] = True
                return query

        Args:
            query: The base query from ``get_queryset()``.
            request: The incoming Request.

        Returns:
            The modified query dict with applied filters.
        """
        search = request.query_params.get("search")
        if search and self.search_fields:
            query = self._apply_search(query, search)

        query = self._apply_filters(query, request)
        return query

    def _apply_search(self, query: dict, search: str) -> dict:
        """Apply full-text search across configured search_fields."""
        safe_search = re.escape(search)
        search_clause = [
            {field: {"$regex": safe_search, "$options": "i"}}
            for field in self.search_fields
        ]
        if "$or" in query:
            existing_or = query.pop("$or")
            query["$and"] = query.get("$and", [])
            query["$and"].append({"$or": existing_or})
            query["$and"].append({"$or": search_clause})
        else:
            query["$or"] = search_clause
        return query

    def _apply_filters(self, query: dict, request: Request) -> dict:
        """Apply query-parameter filters for allowed filter_fields."""
        for key, val in request.query_params.items():
            key = unquote(key)

            if key in RESERVED_QUERY_PARAMS:
                continue

            if not self._is_filter_allowed(key):
                continue

            val = self._coerce_filter_value(val)

            if "__" in key:
                query = self._apply_operator_filter(query, key, val)
            else:
                query[key] = self._maybe_convert_id(key, val)

        return query

    def _is_filter_allowed(self, key: str) -> bool:
        """Check if a filter key is in the allowed filter_fields."""
        if not self.filter_fields:
            return False

        field_name = key.split("__")[0] if "__" in key else key

        if field_name in self.filter_fields or key in self.filter_fields:
            return True

        return any(
            field_name.startswith(f + ".") or f == field_name
            for f in self.filter_fields
        )

    @staticmethod
    def _coerce_filter_value(val: str) -> Any:
        """Coerce string filter values to appropriate Python types."""
        if isinstance(val, str):
            lower = val.lower()
            if lower == "true":
                return True
            if lower == "false":
                return False
            if val.isdigit():
                return int(val)
        return val

    @staticmethod
    def _apply_operator_filter(
        query: dict,
        key: str,
        val: Any,
    ) -> dict:
        """Apply Django-style operators (__ne, __in, __gt, etc.)."""
        field, op = key.split("__", 1)
        val = ListMixin._maybe_convert_id(field, val)

        operator_map = {
            "ne": "$ne",
            "gt": "$gt",
            "gte": "$gte",
            "lt": "$lt",
            "lte": "$lte",
        }

        if op in operator_map:
            query[field] = {operator_map[op]: val}
        elif op == "in":
            items = val if isinstance(val, list) else str(val).split(",")
            items = [ListMixin._maybe_convert_id(field, item.strip()) if isinstance(item, str) else item for item in items]
            query[field] = {"$in": items}
        elif op == "nin":
            items = val if isinstance(val, list) else str(val).split(",")
            items = [ListMixin._maybe_convert_id(field, item.strip()) if isinstance(item, str) else item for item in items]
            query[field] = {"$nin": items}

        return query

    @staticmethod
    def _maybe_convert_id(key: str, val: Any) -> Any:
        """Convert string to PydanticObjectId if the field is ID-like."""
        if not isinstance(val, str):
            return val

        id_suffixes = (".id", ".$id", "_id")
        if any(key.endswith(sfx) for sfx in id_suffixes):
            try:
                if "," in val:
                    return [PydanticObjectId(v.strip()) for v in val.split(",")]
                return PydanticObjectId(val)
            except Exception:
                pass
        return val

    async def perform_list(
        self,
        query: dict,
        *,
        page: int,
        page_size: int,
        sort: Optional[list] = None,
    ) -> tuple[list, int]:
        """
        Execute the database query.

        Returns (results, total_count) via ``$facet`` — single round-trip.

        Override to use a different data source.

        Args:
            query: The final query dict.
            page: Current page number (1-based).
            page_size: Items per page.
            sort: Sort specification.

        Returns:
            Tuple of ``(list_of_documents, total_count)``.
        """
        skip = (page - 1) * page_size
        projection = self._get_projection()
        populate_fields = self._get_populate_fields()

        async def fetch_results() -> tuple[list, int]:
            return await self._repository.get_all(
                query,
                skip=skip,
                limit=page_size,
                sort=sort,
                projection=projection,
                populate_fields=populate_fields,
            )

        if not self._cache or not self._cache.enabled:
            return await fetch_results()

        cache_key = self._build_cache_key(
            "list",
            {
                "query": query,
                "skip": skip,
                "limit": page_size,
                "sort": sort,
                "projection": projection,
                "populate_fields": populate_fields,
            },
        )
        return await self._cache.get_or_set(cache_key, self.cache_ttl, fetch_results)

    async def format_list(
        self,
        results: list,
        total: int,
        page: int,
        page_size: int,
    ) -> dict:
        """
        Shape the final paginated response.

        Override to change the response format.

        Args:
            results: List of documents.
            total: Total matching documents.
            page: Current page number.
            page_size: Items per page.

        Returns:
            A dict with pagination metadata and results.
        """
        return {
            "total": total,
            "count": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, ceil(total / page_size)) if page_size else 1,
            "results": results,
        }


# ── CreateMixin ─────────────────────────────────────────────────────────────

class CreateMixin(ViewContext):
    """
    Provides object creation for ``POST /`` endpoint.

    Hook execution order:
        1. ``before_create()``   — modify / validate data
        2. ``perform_create()``  — save to database
        3. ``after_create()``    — post-save logic (signals, emails, etc.)

    Common override::

        async def before_create(self, data, user):
            data["author"] = str(user.id)
            return data
    """

    async def before_create(
        self,
        data: dict,
        user: Any,
    ) -> dict:
        """
        Modify or validate data before saving to the database.

        Override this in your view to add custom logic:
            • Set fields automatically (e.g., author, timestamps)
            • Validate business rules
            • Raise ``HTTPException`` to reject the request

        Args:
            data: The validated request body as a dict.
            user: The current authenticated user, or ``None``.

        Returns:
            The (possibly modified) data dict to be saved.

        Raises:
            HTTPException: To reject the creation with an error response.

        Example::

            async def before_create(self, data, user):
                data["author"] = str(user.id)
                data["published"] = False
                return data
        """
        return data

    async def perform_create(self, data: dict) -> Any:
        """
        Save the object to the database.

        Override to change persistence behaviour.

        Args:
            data: The final data dict to persist.

        Returns:
            The created Beanie Document instance.
        """
        return await self._repository.create(data)

    async def after_create(self, instance: Any, user: Any) -> Any:
        """
        Called after successful save.

        Override for post-creation side effects (notifications, etc.).
        Return the instance (you can modify it for the response).

        Args:
            instance: The created document.
            user: The current user.

        Returns:
            The instance (possibly modified for the response).
        """
        return instance


# ── RetrieveMixin ───────────────────────────────────────────────────────────

class RetrieveMixin(ViewContext):
    """
    Provides single-object retrieval for ``GET /{pk}`` endpoint.

    Hook execution order:
        1. ``get_object()``        — fetch + permission check (inherited)
        2. ``before_retrieve()``   — pre-processing
        3. ``perform_retrieve()``  — return the object
        4. ``after_retrieve()``    — post-processing (analytics, etc.)
    """

    async def before_retrieve(
        self,
        pk: str,
        request: Request,
        user: Any,
    ) -> None:
        """
        Called before fetching the object.

        Override for pre-fetch validation or logging.

        Args:
            pk: The primary key value.
            request: The incoming Request.
            user: The current user.
        """
        pass

    async def perform_retrieve(
        self,
        pk: str,
        request: Request,
        user: Any,
    ) -> dict:
        """
        Fetch and return the object.

        Override to customise the retrieval logic.

        Args:
            pk: The primary key value.
            request: The incoming Request.
            user: The current user.

        Returns:
            The document as a dict.
        """
        return await self.get_object(pk, request, user)

    async def after_retrieve(
        self,
        instance: dict,
        request: Request,
        user: Any,
    ) -> dict:
        """
        Called after successful retrieval.

        Override for analytics (view counting, etc.).

        Args:
            instance: The retrieved document.
            request: The incoming Request.
            user: The current user.

        Returns:
            The instance (possibly modified for the response).
        """
        # Emit view signal for analytics
        from .signals import signals

        try:
            await signals.on_view.emit(
                instance,
                model_class=self.schema,
                request=request,
                user=user,
            )
        except Exception:
            logger.debug("View signal emission failed", exc_info=True)

        return instance


# ── UpdateMixin ─────────────────────────────────────────────────────────────

class UpdateMixin(ViewContext):
    """
    Provides partial update for ``PATCH /{pk}`` endpoint.

    Hook execution order:
        1. ``get_object()``       — fetch + permission check
        2. ``before_update()``    — modify / validate update data
        3. ``perform_update()``   — save changes
        4. ``after_update()``     — post-save logic

    Common override::

        async def before_update(self, instance, data, user):
            data.pop("author", None)  # prevent author reassignment
            return data
    """

    async def before_update(
        self,
        instance: dict,
        data: dict,
        user: Any,
    ) -> dict:
        """
        Modify or validate update data before saving.

        ``instance`` is the current DB record (read-only here).
        Return the (possibly modified) data dict.

        Args:
            instance: The current document from the database.
            data: The update data from the request.
            user: The current user.

        Returns:
            The (possibly modified) data dict.
        """
        return data

    async def perform_update(
        self,
        instance: dict,
        data: dict,
    ) -> Any:
        """
        Apply updates to the database.

        Only updates fields explicitly allowed by the schema.

        Args:
            instance: The current document.
            data: The update data.

        Returns:
            The updated Beanie Document instance.
        """
        query = {"$or": [{self.lookup_field: instance.get(self.lookup_field, instance.get("id"))}, {"id": instance.get("id")}]}
        return await self._repository.update(
            query,
            data,
            allowed_fields=list(self.schema.model_fields.keys()),
        )

    async def after_update(self, instance: Any, user: Any) -> Any:
        """
        Called after successful update.

        Override for post-update side effects.

        Args:
            instance: The updated document.
            user: The current user.

        Returns:
            The instance (possibly modified for the response).
        """
        return instance


# ── DeleteMixin ─────────────────────────────────────────────────────────────

class DeleteMixin(ViewContext):
    """
    Provides soft-delete for ``DELETE /{pk}`` endpoint.

    Hook execution order:
        1. ``get_object()``       — fetch + permission check
        2. ``before_delete()``    — return ``False`` to cancel
        3. ``perform_delete()``   — mark as deleted
        4. ``after_delete()``     — cleanup logic

    Common override::

        async def before_delete(self, instance, user):
            if instance.get("published"):
                raise HTTPException(400, "Cannot delete published post")
            return True
    """

    async def before_delete(
        self,
        instance: dict,
        user: Any,
    ) -> bool:
        """
        Called before deletion.

        Return ``True`` to proceed, ``False`` to silently cancel,
        or raise ``HTTPException`` to return an error response.

        Args:
            instance: The document to be deleted.
            user: The current user.

        Returns:
            ``True`` to proceed with deletion.
        """
        return True

    async def perform_delete(self, instance: dict) -> None:
        """
        Execute the delete.  Soft-delete by default.

        Override to change delete behaviour (e.g., hard delete).

        Args:
            instance: The document to delete.
        """
        query = {"$or": [{self.lookup_field: instance.get(self.lookup_field, instance.get("id"))}, {"id": instance.get("id")}]}
        await self._repository.delete(query, soft=True)

    async def after_delete(
        self,
        instance: dict,
        user: Any,
    ) -> None:
        """
        Called after successful delete.

        Override for cleanup (remove related resources, etc.).

        Args:
            instance: The deleted document.
            user: The current user.
        """
        pass
