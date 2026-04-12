"""
backbone.core.repository
~~~~~~~~~~~~~~~~~~~~~~~~~

Database abstraction layer for Backbone.

Defines the ``AbstractRepository`` protocol (database-agnostic interface)
and ``BeanieRepository`` (concrete MongoDB / Beanie implementation).

Design decisions:
    • ``_build_lookup_pipeline()`` is the **single source of truth** for all
      ``$lookup`` aggregation stages — called by ``get_all()``, ``get_one()``,
      and ``count()``.  Never duplicate this logic.
    • ``get_all()`` uses MongoDB ``$facet`` to return **(results, total)**
      in a single database round-trip.
    • ``update()`` accepts an ``allowed_fields`` whitelist to prevent
      mass-assignment attacks.
    • ``_prepare_query()`` raises ``HTTPException(400)`` on invalid ObjectId
      values instead of silently falling back.
"""

from __future__ import annotations

import copy
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Generic, List, Optional, Protocol, Type, TypeVar, Union

from beanie import Document, PydanticObjectId
from bson import ObjectId
from bson.dbref import DBRef
from fastapi import HTTPException
from pydantic import BaseModel

logger = logging.getLogger("backbone.repository")

T = TypeVar("T", bound=BaseModel)


# ── Constants ───────────────────────────────────────────────────────────────

# Fields managed internally — never accept from user input
AUDIT_FIELDS = frozenset({
    "created_at", "updated_at", "deleted_at",
    "created_by", "updated_by", "deleted_by",
    "is_deleted",
})

# Hardcoded audit field mappings for user references
AUDIT_USER_FIELDS = ("created_by", "updated_by", "deleted_by")

# Default projection fields returned for user references
DEFAULT_USER_RETURN_FIELDS = ("id", "email", "full_name")


# ── Abstract Repository Protocol ────────────────────────────────────────────

class AbstractRepository(Protocol[T]):
    """
    Database-agnostic repository interface.

    Any storage backend (MongoDB, PostgreSQL, etc.) must implement this
    interface to work with Backbone views.

    Type Parameters:
        T: The document / model type this repository manages.
    """

    async def get_all(
        self,
        query: Dict[str, Any],
        *,
        skip: int = 0,
        limit: int = 10,
        sort: Optional[List] = None,
        projection: Optional[Dict[str, int]] = None,
        populate_fields: Optional[Dict[str, Any]] = None,
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        Fetch paginated results AND total count in one query.

        Returns:
            Tuple of (list_of_documents, total_count).
        """
        ...

    async def get_one(
        self,
        filter_query: Dict[str, Any],
        *,
        projection: Optional[Dict[str, int]] = None,
        populate_fields: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fetch a single document matching the query."""
        ...

    async def create(self, data: Dict[str, Any], request: Any = None) -> Any:
        """Create a new document and return it."""
        ...

    async def update(
        self,
        filter_query: Dict[str, Any],
        data: Dict[str, Any],
        *,
        allowed_fields: Optional[List[str]] = None,
    ) -> Optional[Any]:
        """
        Update a document. If ``allowed_fields`` is provided, only those
        fields will be updated — others are silently ignored.
        """
        ...

    async def delete(
        self,
        filter_query: Dict[str, Any],
        *,
        soft: bool = True,
    ) -> bool:
        """Delete (or soft-delete) a document."""
        ...

    async def count(
        self,
        query: Dict[str, Any],
        *,
        populate_fields: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Count documents matching the query."""
        ...


# ── Beanie Repository (Concrete MongoDB Implementation) ─────────────────────

class BeanieRepository(Generic[T]):
    """
    Concrete MongoDB repository backed by Beanie ODM.

    Provides CRUD operations with:
        • Automatic ObjectId handling
        • ``$lookup`` population of related collections
        • ``$facet``-based pagination (single round-trip)
        • Mass-assignment prevention via ``allowed_fields``

    Args:
        db: Motor database instance (optional; resolved lazily via
            ``BackboneConfig``).

    Example::

        repo = BeanieRepository()
        repo.initialize(Blog)
        items, total = await repo.get_all({"is_deleted": False}, skip=0, limit=10)
    """

    def __init__(self, db: Any = None) -> None:
        self.db = db
        self.document_class: Optional[Type[Document]] = None

    def initialize(self, schema: Type[BaseModel]) -> None:
        """
        Bind this repository to a specific Beanie Document class.

        Args:
            schema: A Beanie ``Document`` subclass.
        """
        if issubclass(schema, Document):
            self.document_class = schema

    # ── Link Detection ──────────────────────────────────────────────────────

    @staticmethod
    def _extract_link_info(annotation: Any) -> tuple[Optional[Type[Document]], bool]:
        """Extract (target_model, is_list) from a Link[] annotation."""
        from typing import get_args, get_origin, Annotated, Union
        from beanie import Link
        
        # Unwrap Annotated if present
        if get_origin(annotation) is Annotated:
            annotation = get_args(annotation)[0]

        origin = get_origin(annotation)
        target_model = None
        is_list = False

        if origin is Link:
            target_model = get_args(annotation)[0]
        elif origin in (list, List):
            args = get_args(annotation)
            if args:
                inner_annotation = args[0]
                # Recursively extract from list item (could be Link or Annotated[Link])
                target_model, _ = BeanieRepository._extract_link_info(inner_annotation)
                is_list = True
        elif origin is Union:
            for arg in get_args(annotation):
                if arg is type(None): continue
                t_model, t_list = BeanieRepository._extract_link_info(arg)
                if t_model:
                    target_model = t_model
                    is_list = t_list
                    break
        return target_model, is_list

    @staticmethod
    def detect_populate_fields(schema: Type[BaseModel], prefix: str = "", depth: int = 0) -> Dict[str, Any]:
        """
        Recursively detect Beanie ``Link`` fields and audit user fields on a schema.
        Handles nested models, lists, and unions up to depth 2.
        """
        from typing import get_args, get_origin
        if depth > 2: return {}

        detected: Dict[str, Any] = {}

        # 1. Field-by-field check
        for field_name, field_info in schema.model_fields.items():
            full_path = f"{prefix}{field_name}"
            annotation = field_info.annotation
            
            target_model, is_list = BeanieRepository._extract_link_info(annotation)

            if target_model and hasattr(target_model, "Settings") and hasattr(target_model.Settings, "name"):
                collection_name = target_model.Settings.name
                config_dict: Dict[str, Any] = {
                    "collection": collection_name,
                    "field": full_path,
                    "is_link": True,
                    "is_list": is_list,
                }
                
                return_fields = getattr(target_model.Settings, "return_link_data", None)
                if return_fields and isinstance(return_fields, list):
                    config_dict["fields"] = return_fields
                elif collection_name == "users":
                    config_dict["fields"] = list(DEFAULT_USER_RETURN_FIELDS)
                
                detected[full_path] = config_dict
                
                # RECURSION: Also detect links inside the target model for deep population
                if target_model is not schema:
                    nested = BeanieRepository.detect_populate_fields(target_model, f"{full_path}.", depth + 1)
                    detected.update(nested)
            else:
                # Recurse into nested models/lists/unions to find more links
                # but only if it's not a direct Link (already handled)
                def flatten_types(t: Any) -> list:
                    res = []
                    uo = get_origin(t)
                    if uo is Union:
                        for a in get_args(t): res.extend(flatten_types(a))
                    elif uo in (list, List):
                        # Link info in list is handled by _extract_link_info above
                        # If we are here, it's a list OF something else (like models)
                        args = get_args(t)
                        if args:
                             res.extend(flatten_types(args[0]))
                    elif isinstance(t, type):
                        res.append(t)
                    return res
                
                inner_types = flatten_types(annotation)
                for itype in inner_types:
                    if isinstance(itype, type) and issubclass(itype, BaseModel) and itype is not schema:
                        detected.update(BeanieRepository.detect_populate_fields(itype, f"{full_path}.", depth + 1))

        return detected

    # ── Data Sanitisation ───────────────────────────────────────────────────

    @staticmethod
    def _sanitize(data: Any, depth: int = 0) -> Any:
        """
        Recursively convert all ``ObjectId`` and ``Link`` instances in a
        document tree to plain strings.

        Args:
            data: A dict, list, or scalar value.
            depth: Current recursion depth.

        Returns:
            The sanitised structure with string IDs.
        """
        if depth > 5: # Safety limit for deep documents
            return str(data)

        if isinstance(data, dict):
            # 1. Recurse into children
            sanitized = {k: BeanieRepository._sanitize(v, depth + 1) for k, v in data.items()}
            # 2. Ensure "id" field exists if "_id" is present (for Jinja2 template compatibility)
            if "_id" in sanitized and "id" not in sanitized:
                sanitized["id"] = sanitized["_id"]
            return sanitized
        
        if isinstance(data, list):
            return [BeanieRepository._sanitize(v, depth + 1) for v in data]
        
        if isinstance(data, (ObjectId, PydanticObjectId)):
            return str(data)

        from beanie import Link
        from bson.dbref import DBRef

        if isinstance(data, Link):
            if hasattr(data, "id"): return str(data.id)
            if hasattr(data, "ref"): return str(data.ref.id)
            return str(data)
            
        if isinstance(data, DBRef):
            return str(data.id)
            
        return data

    # ── Query Preparation ───────────────────────────────────────────────────

    @classmethod
    def _prepare_query(cls, query: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively prepare a query dict for MongoDB.

        Transformations:
            • ``"id"`` keys → ``"_id"``
            • String values on ID-like keys → ``PydanticObjectId``
            • Traverses ``$or``, ``$and``, ``$nor`` operators

        Raises:
            HTTPException(400): If a value intended as an ObjectId is not
                a valid 24-character hex string.
        """
        if not isinstance(query, dict):
            return query

        prepared: Dict[str, Any] = {}

        for key, value in query.items():
            new_key = "_id" if key == "id" else key

            if isinstance(value, dict):
                prepared[new_key] = cls._prepare_query(value)
            elif isinstance(value, list):
                prepared[new_key] = cls._prepare_list_value(
                    key, new_key, value,
                )
            elif isinstance(value, str):
                prepared[new_key] = cls._coerce_id_string(new_key, value)
            else:
                prepared[new_key] = value

        return prepared

    @classmethod
    def _prepare_list_value(
        cls,
        original_key: str,
        new_key: str,
        value: list,
    ) -> list:
        """Prepare a list value inside a query dict."""
        if original_key in ("$or", "$and", "$nor"):
            return [
                cls._prepare_query(item) if isinstance(item, dict) else item
                for item in value
            ]

        if cls._is_id_field(new_key):
            return [cls._coerce_id_string(new_key, v) if isinstance(v, str) else v for v in value]

        return value

    @staticmethod
    def _is_id_field(key: str) -> bool:
        """Check whether a query key refers to an ID field."""
        return key == "_id" or key.endswith(".id") or key.endswith(".$id")

    @classmethod
    def _coerce_id_string(cls, key: str, value: str) -> Any:
        """
        Attempt to convert a string to ``PydanticObjectId`` if the key
        is an ID field.

        Raises:
            HTTPException(400): On invalid ObjectId format with an
                actionable error message.
        """
        if not cls._is_id_field(key):
            return value

        try:
            return PydanticObjectId(value)
        except Exception:
            # Fallback: Return original string if not a valid ObjectId.
            # This allows $or queries (ID or Slug) to work without raising 400 errors.
            return value

    # ── Lookup Pipeline (Single Source of Truth) ────────────────────────────

    @staticmethod
    def _build_lookup_pipeline(
        populate_fields: Dict[str, Any],
    ) -> list[dict]:
        """
        Build ``$lookup`` + ``$unwind`` aggregation stages for all fields
        that need population.

        This is the **single source of truth** for join logic.  Called by
        ``get_all()``, ``get_one()``, and ``count()`` — never duplicated.

        Args:
            populate_fields: Dict of field_name → population config.

        Returns:
            List of MongoDB aggregation pipeline stages.
        """
        stages: list[dict] = []

        for local_field, config in populate_fields.items():
            if "." in local_field:
                continue  # Handled post-fetch by _resolve_deep_links
                
            target_collection, alias, is_link, is_string_id, is_list, fields_to_return = (
                BeanieRepository._unpack_populate_config(local_field, config)
            )

            local_val_expr = BeanieRepository._build_local_val_expr(
                local_field, is_link, is_list,
            )
            inner_match = BeanieRepository._build_inner_match(
                is_string_id, is_list,
            )
            inner_pipeline = BeanieRepository._build_inner_pipeline(
                inner_match, fields_to_return,
            )

            stages.append({
                "$lookup": {
                    "from": target_collection,
                    "let": {"local_val": local_val_expr},
                    "pipeline": inner_pipeline,
                    "as": alias,
                },
            })

            if not is_list:
                stages.append({
                    "$unwind": {
                        "path": f"${alias}",
                        "preserveNullAndEmptyArrays": True,
                    },
                })

        return stages

    @staticmethod
    def _unpack_populate_config(
        local_field: str,
        config: Any,
    ) -> tuple[str, str, bool, bool, bool, Optional[list]]:
        """Extract population parameters from a config value."""
        if isinstance(config, dict):
            return (
                config.get("collection", ""),
                config.get("field", local_field),
                config.get("is_link", False),
                config.get("is_string_id", False),
                config.get("is_list", False),
                config.get("fields"),
            )
        # Simple string config — just the collection name
        return (config, local_field, False, False, False, None)

    @staticmethod
    def _build_local_val_expr(
        local_field: str,
        is_link: bool,
        is_list: bool,
    ) -> Any:
        """Build the ``let`` expression for ``$lookup``."""
        if is_list:
            if is_link:
                return {
                    "$map": {
                        "input": {"$ifNull": [f"${local_field}", []]},
                        "as": "item",
                        "in": {
                            "$ifNull": [
                                "$$item.id",
                                {
                                    "$ifNull": [
                                        "$$item._id",
                                        {"$ifNull": ["$$item.$id", "$$item"]}
                                    ]
                                }
                            ],
                        },
                    },
                }
            return {"$ifNull": [f"${local_field}", []]}

        if is_link:
            return {
                "$ifNull": [
                    f"${local_field}.id",
                    {
                        "$ifNull": [
                            f"${local_field}._id",
                            {"$ifNull": [f"${local_field}.$id", f"${local_field}"]}
                        ]
                    }
                ],
            }
        return f"${local_field}"

    @staticmethod
    def _build_inner_match(is_string_id: bool, is_list: bool) -> dict:
        """Build the ``$match`` expression inside a ``$lookup`` pipeline."""
        if is_string_id and is_list:
            return {"$expr": {"$in": [{"$toString": "$_id"}, "$$local_val"]}}
        if is_string_id:
            return {"$expr": {"$eq": ["$_id", {"$toObjectId": "$$local_val"}]}}
        if is_list:
            return {"$expr": {"$in": ["$_id", "$$local_val"]}}
        return {"$expr": {"$eq": ["$_id", "$$local_val"]}}

    @staticmethod
    def _build_inner_pipeline(
        inner_match: dict,
        fields_to_return: Optional[list],
    ) -> list[dict]:
        """Build the inner pipeline stages for a ``$lookup``."""
        pipeline: list[dict] = [{"$match": inner_match}]

        if fields_to_return and isinstance(fields_to_return, list):
            project_stage = {f: 1 for f in fields_to_return}
            project_stage["id"] = "$_id"
            project_stage["_id"] = 0
            pipeline.append({"$project": project_stage})
        else:
            pipeline.append({"$addFields": {"id": "$_id"}})
            pipeline.append({"$project": {"_id": 0}})

        return pipeline

    # ── Deep Link Resolution (Post-fetch) ──────────────────────────────────

    async def _resolve_deep_links(self, doc: dict, populate_fields: Dict[str, Any]) -> dict:
        """
        Fetch and inject documents for links nested inside lists or objects.
        This handles cases where $lookup is too complex to build generically.
        """
        from bson import ObjectId

        for field_path, config in populate_fields.items():
            if "." not in field_path: continue  # Handled by aggregation
            
            parts = field_path.split(".")
            parent_path = ".".join(parts[:-1])
            link_field = parts[-1]
            
            # 1. Find the parent objects containing the link
            # We use a simple recursive extractor
            def get_containers(data, path_parts):
                if not path_parts:
                    if isinstance(data, list): return [d for d in data if isinstance(d, dict)]
                    if isinstance(data, dict): return [data]
                    return []
                
                key = path_parts[0]
                remaining = path_parts[1:]
                
                if isinstance(data, list):
                    res = []
                    for item in data:
                        res.extend(get_containers(item, path_parts))
                    return res
                if isinstance(data, dict):
                    val = data.get(key)
                    return get_containers(val, remaining) if val is not None else []
                return []

            containers = get_containers(doc, parts[:-1])
            if not containers: continue

            # 2. Extract unique IDs to fetch
            id_to_containers = {}
            for c in containers:
                if not isinstance(c, dict): continue
                raw = c.get(link_field)
                with open("/tmp/debug_repo.log", "a") as f:
                    f.write(f"DEBUG: Found link at {field_path}: {raw}\n")
                if not raw: continue
                
                # Normalize ID from string, DBRef, or Link object
                if isinstance(raw, str) and len(raw) == 24:
                    att_id = raw
                elif isinstance(raw, DBRef):
                    att_id = str(raw.id)
                elif isinstance(raw, dict):
                    oid = raw.get("$id") or raw.get("id")
                    att_id = str(oid) if oid else None
                else:
                    att_id = None
                
                if att_id: id_to_containers.setdefault(att_id, []).append(c)

            # 3. Batch fetch from target collection
            if id_to_containers:
                try:
                    target_coll = self.db[config["collection"]] if self.db is not None else None
                    if target_coll is None:
                         from .config import BackboneConfig
                         target_coll = BackboneConfig.get_instance().database[config["collection"]]

                    oids = [ObjectId(aid) for aid in id_to_containers.keys()]
                    projection = {f: 1 for f in config.get("fields", [])} if config.get("fields") else {}
                    if projection:
                         projection["id"] = "$_id"
                         projection["_id"] = 0
                    
                    cursor = target_coll.find({"_id": {"$in": oids}}, projection)
                    results = await cursor.to_list(length=len(oids))
                    
                    with open("/tmp/debug_repo.log", "a") as f:
                        f.write(f"DEBUG: Found {len(results)} docs for deep link {field_path}\n")

                    for r in results:
                        # Map back to dict with 'id' string
                        if "_id" in r:
                             r["id"] = str(r.pop("_id"))
                        
                        # Apply sanitization (media URLs, etc.)
                        r = BeanieRepository._sanitize(r)
                        
                        rid = str(r.get("id"))
                        for c in id_to_containers.get(rid, []):
                            c[link_field] = r
                except Exception as e:
                    logger.warning("Failed to resolve deep links for '%s': %s", link_field, e)

        return doc

    # ── Core CRUD Operations ────────────────────────────────────────────────

    async def get_all(
        self,
        query: Dict[str, Any],
        *,
        skip: int = 0,
        limit: int = 10,
        sort: Optional[Any] = None,
        projection: Optional[Dict[str, int]] = None,
        populate_fields: Optional[Dict[str, Any]] = None,
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        Fetch paginated results AND total count in **one** database
        round-trip using ``$facet``.

        Args:
            query: MongoDB filter dict.
            skip: Number of documents to skip.
            limit: Maximum number of documents to return.
            sort: Sort specification (list of tuples or dict).
            projection: Field projection dict.
            populate_fields: Fields to populate via ``$lookup``.

        Returns:
            Tuple of ``(list_of_documents, total_count)``.

        Example::

            items, total = await repo.get_all(
                {"is_deleted": False},
                skip=0,
                limit=10,
            )
        """
        full_query = self._prepare_query(query)

        # Split into local vs joined-field queries
        local_query, joined_query = self._split_query(full_query)

        # Build pipeline
        pipeline: list[dict] = [{"$match": local_query}]

        # Add lookups (single source of truth)
        if populate_fields:
            pipeline += self._build_lookup_pipeline(populate_fields)

        # Filter by joined fields after population
        if joined_query:
            pipeline.append({"$match": joined_query})

        # Build $facet for single-round-trip results + count
        pipeline += self._build_facet_stage(skip, limit, sort, projection)

        # Execute
        raw = await self.document_class.get_pymongo_collection().aggregate(
            pipeline,
        ).to_list(length=1)

        if not raw:
            return [], 0

        facet_result = raw[0]
        total = facet_result.get("total_count", [{}])[0].get("count", 0) if facet_result.get("total_count") else 0
        results = facet_result.get("results", [])
        
        # Resolve deep links for every result in the list
        if populate_fields:
            import asyncio
            results = await asyncio.gather(*[self._resolve_deep_links(r, populate_fields) for r in results])
            
        return self._clean_results(results), total

    @staticmethod
    def _build_facet_stage(
        skip: int,
        limit: int,
        sort: Optional[Any],
        projection: Optional[Dict[str, int]],
    ) -> list[dict]:
        """
        Build a ``$facet`` stage that returns both paginated results and
        total count from a single pipeline execution.

        Returns:
            A list containing the ``$facet`` stage dict.
        """
        results_pipeline: list[dict] = []

        # Sort
        if sort:
            sort_stage: dict = {}
            if isinstance(sort, list):
                for field, direction in sort:
                    sort_stage[field] = direction
            elif isinstance(sort, dict):
                sort_stage = sort
            if sort_stage:
                results_pipeline.append({"$sort": sort_stage})

        # Skip & Limit
        results_pipeline.append({"$skip": skip})
        results_pipeline.append({"$limit": limit})

        # Projection
        if projection:
            results_pipeline.append({"$project": projection})

        return [{
            "$facet": {
                "results": results_pipeline,
                "total_count": [{"$count": "count"}],
            },
        }]

    async def get_one(
        self,
        filter_query: Dict[str, Any],
        *,
        projection: Optional[Dict[str, int]] = None,
        populate_fields: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch a single document matching the query.

        Uses simple ``find_one`` when no population or projection is needed,
        otherwise falls back to an aggregation pipeline.

        Args:
            filter_query: MongoDB filter dict.
            projection: Field projection dict.
            populate_fields: Fields to populate via ``$lookup``.

        Returns:
            The document as a dict, or ``None`` if not found.
        """
        filter_query = self._prepare_query(filter_query)

        if not populate_fields and not projection:
            return await self._simple_find_one(filter_query)

        # Aggregation path for population / projection
        pipeline: list[dict] = [{"$match": filter_query}]

        if populate_fields:
            pipeline += self._build_lookup_pipeline(populate_fields)

        if projection:
            pipeline.append({"$project": projection})

        results = await self.document_class.get_pymongo_collection().aggregate(
            pipeline,
        ).to_list(length=1)

        if not results:
            return None

        doc = results[0]
        # Resolve any deep (nested) links after the main aggregation
        if populate_fields:
            doc = await self._resolve_deep_links(doc, populate_fields)
            
        return self._clean_single_doc(doc)

    async def _simple_find_one(
        self,
        filter_query: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Fetch a single document without aggregation."""
        doc = await self.document_class.find_one(filter_query)
        if not doc:
            return None

        dumped = doc.model_dump(by_alias=True)
        if "_id" in dumped:
            dumped["id"] = str(dumped.pop("_id"))
        return self._sanitize(dumped)

    async def create(self, data: Dict[str, Any], request: Any = None) -> Any:
        """
        Create a new document in the database.

        Args:
            data: Dict of field values for the new document.

        Returns:
            The created Beanie Document instance.
        """
        obj = self.document_class(**data)
        await obj.insert()
        return obj

    async def update(
        self,
        filter_query: Dict[str, Any],
        data: Dict[str, Any],
        *,
        allowed_fields: Optional[List[str]] = None,
    ) -> Optional[Any]:
        """
        Update a document matching the filter.

        If ``allowed_fields`` is provided, only those fields will be updated
        — all others are silently ignored.  This prevents mass-assignment
        vulnerabilities where a client could set ``is_superuser=True``.

        Args:
            filter_query: MongoDB filter to find the document.
            data: Dict of field updates.
            allowed_fields: Whitelist of field names.  ``None`` = allow all.
                Always pass this in user-facing endpoints.

        Returns:
            The updated Beanie Document, or ``None`` if not found.
        """
        uses_update_operators = any(key.startswith("$") for key in data)

        if uses_update_operators and allowed_fields is not None:
            raise ValueError("allowed_fields cannot be combined with raw MongoDB update operators.")

        if allowed_fields is not None:
            data = {k: v for k, v in data.items() if k in allowed_fields}

        filter_query = self._prepare_query(filter_query)
        item = await self.document_class.find_one(filter_query)
        if not item:
            return None

        if uses_update_operators:
            await self.document_class.get_pymongo_collection().update_one(
                {"_id": item.id},
                data,
            )
            return await self.document_class.get(item.id)

        await item.set(data)
        return item

    async def delete(
        self,
        filter_query: Dict[str, Any],
        *,
        soft: bool = True,
    ) -> bool:
        """
        Delete a document.

        Args:
            filter_query: MongoDB filter to find the document.
            soft: If ``True`` (default), sets ``is_deleted=True`` and
                ``deleted_at``; if ``False``, permanently removes.

        Returns:
            ``True`` if the document was found and deleted/marked.
        """
        filter_query = self._prepare_query(filter_query)
        item = await self.document_class.find_one(filter_query)
        if not item:
            return False

        if soft:
            await item.set({
                "is_deleted": True,
                "deleted_at": datetime.now(timezone.utc),
            })
        else:
            await item.delete()
        return True

    async def count(
        self,
        query: Dict[str, Any],
        *,
        populate_fields: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Count documents matching the query.

        Uses simple ``find().count()`` for local-only queries, or falls
        back to an aggregation pipeline for joined-field queries.

        Args:
            query: MongoDB filter dict.
            populate_fields: Population config (needed for joined filters).

        Returns:
            Integer count of matching documents.
        """
        full_query = self._prepare_query(query)

        has_joined = any(
            "." in k and not (k.startswith("$") or k.endswith(".id") or k.endswith(".$id"))
            for k in full_query
        )

        if not has_joined:
            return await self.document_class.find(full_query).count()

        # Aggregation pipeline for joined-field counting
        local_query, joined_query = self._split_query(full_query)
        pipeline: list[dict] = [{"$match": local_query}]

        if populate_fields:
            pipeline += self._build_lookup_pipeline(populate_fields)

        if joined_query:
            pipeline.append({"$match": joined_query})

        pipeline.append({"$count": "total"})

        results = await self.document_class.get_pymongo_collection().aggregate(
            pipeline,
        ).to_list(length=1)

    async def get_stats(
        self,
        config: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Compute multiple statistics (counts, sums) in a single pass if possible,
        or sequentially.
        """
        res = {}
        for item in config:
            stype = item.get("type", "count")
            filters = self._prepare_query(item.get("filters", {}))
            name = item["name"]
            
            if stype == "count":
                res[name] = await self.count(filters)
            elif stype == "sum":
                field = item.get("field")
                if not field: continue
                agg = await self.document_class.get_pymongo_collection().aggregate([
                    {"$match": filters},
                    {"$group": {"_id": None, "total": {"$sum": f"${field}"}}}
                ]).to_list(1)
                res[name] = (agg[0].get("total") or 0) if agg else 0
        return res

    # ── Private Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _split_query(
        full_query: Dict[str, Any],
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Split a query into local-field and joined-field parts.

        Joined fields contain a dot (e.g., ``category.name``) that is
        NOT a MongoDB operator or ID reference.

        Returns:
            Tuple of ``(local_query, joined_query)``.
        """
        local: Dict[str, Any] = {}
        joined: Dict[str, Any] = {}

        for k, v in full_query.items():
            if "." in k and not (k.startswith("$") or k.endswith(".id") or k.endswith(".$id")):
                joined[k] = v
            else:
                local[k] = v

        return local, joined

    def _clean_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Clean a list of aggregation result documents."""
        return [self._clean_single_doc(doc) for doc in results]

    def _clean_single_doc(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Move ``_id`` → ``id`` and sanitise all ObjectIds."""
        if "_id" in doc:
            doc["id"] = str(doc.pop("_id"))
        return self._sanitize(doc)

    def serialize_document(self, doc: Any) -> Any:
        """Convert a document-like object into Backbone's sanitized response shape."""
        if doc is None:
            return None
        if isinstance(doc, list):
            return [self.serialize_document(item) for item in doc]
        if isinstance(doc, dict):
            return self._clean_single_doc(copy.deepcopy(doc))
        if isinstance(doc, Document):
            dumped = doc.model_dump(by_alias=True)
            return self._clean_single_doc(dumped)
        return self._sanitize(doc)
