from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from typing import List, Optional, Any, Type, Dict, Union
from beanie import Document
from ..core.repository import BeanieRepository
from ..core.permissions import IsOwner, BasePermission, PermissionDependency, AllowAny, IsAdminUser
from ..schemas import UserOut, PaginatedResponse
from ..core.config import BackboneConfig
from ..utils.cache import CacheService, cache
import hashlib

class BaseGenericView:
    """
    Base class for generic CRUD views using Beanie.
    """
    def __init__(
        self,
        schema: Type[BaseModel],
        prefix: str,
        tags: List[str] = None,
        repository: BeanieRepository = None,
        permission_classes: List[Type[BasePermission]] = [IsOwner],
        list_fields: List[str] = None,
        search_fields: List[str] = None,
        filter_fields: List[str] = None,
        ordering_fields: List[str] = None,
        database: Any = None,
        use_auth: bool = False,
        cache_ttl: int = 300,
        populate_fields: Dict[str, str] = None,
        fetch_links: bool = False,
        rate_limit: Optional[Any] = None,
        lookup_field: str = "id"
    ):
        
        from ..core.rate_limit import RateLimit
        
        router_kwargs = {"prefix": prefix, "tags": tags or [prefix.strip("/")]}
        
        if rate_limit is True:
            router_kwargs["dependencies"] = [Depends(RateLimit())]
        elif rate_limit:
            if isinstance(rate_limit, list):
                router_kwargs["dependencies"] = rate_limit
            else:
                router_kwargs["dependencies"] = [rate_limit]

        self.router = APIRouter(**router_kwargs)
        
        self.schema = schema
        self.prefix = prefix
        self.cache_ttl = cache_ttl
        self.lookup_field = lookup_field
        
        # Resolve Repository Class and Instance
        self.repository = repository
        if not self.repository:
            self.repository = BeanieRepository(database)

        # Initialize repository with schema metadata
        self.repository.initialize(self.schema)
        
        self.use_auth = use_auth
        self.search_fields = search_fields or []
        self.filter_fields = filter_fields or []
        self.ordering_fields = ordering_fields or []
        
        if not isinstance(permission_classes, list):
            self.permission_classes = [permission_classes]
        else:
            self.permission_classes = permission_classes

        self.list_fields = list_fields
        self.perm_dep = PermissionDependency(self.permission_classes, self.use_auth)
        self.cache_service: Optional[CacheService] = None
        self.fetch_links = fetch_links
        self.populate_fields = populate_fields or {}

        if self.fetch_links:
            self.populate_fields.update(self._detect_populate_fields())
            
    def _detect_populate_fields(self) -> Dict[str, Any]:
        """
        Detects Beanie Link fields and adds them to populate_fields.
        Returns a dict of field_name -> target_collection.
        """
        from ..core.repository import BeanieRepository
        return BeanieRepository.detect_populate_fields(self.schema)

    async def _resolve_context(self, request: Request):
        """
        Ensure the repository and cache have the correct DB/Client from BackboneConfig.
        """
        config = request.app.state.backbone_config
        if self.repository.db is None:
            self.repository.db = config.database
        
        if not self.cache_service:
            self.cache_service = getattr(config, "cache_service", None)

    async def _invalidate_cache(self):
        if self.cache_service:
            # Broad pattern to clear both @cache decorator and manual _get_object_internal cache
            pattern = f"backbone:*{self.prefix}*"
            await self.cache_service.delete_pattern(pattern)

    def _get_projection(self):
        if self.list_fields:
            projection = {field: 1 for field in self.list_fields}
            projection["_id"] = 1
            return projection
        return None

    async def _get_object_internal(self, pk: str, request: Request, user: Optional[UserOut], use_cache: bool = True) -> Any:
        await self._resolve_context(request)
        
        cache_key = f"backbone:cache:{self.prefix}:detail:{pk}"
        
        async def fetch_item():
            query = {
                "$or": [{self.lookup_field: pk}, {"id": pk}],
                "is_deleted": False
            }
            item = await self.repository.get_one(query)
            if not item:
                raise HTTPException(status_code=404, detail="Item not found")
            
            # Note: item is a dict here, make sure permission_class handles dict or convert if needed
            for permission_class in self.permission_classes:
                perm = permission_class(request, user)
                if not await perm.has_object_permission(item):
                    raise HTTPException(status_code=403, detail="Object-level access denied")
            return item if isinstance(item, dict) else item.model_dump(by_alias=True)

        if use_cache and self.cache_service and self.cache_service.enabled:
            data = await self.cache_service.get_or_set(cache_key, self.cache_ttl, fetch_item)
            return self.schema(**data)
            
        item_data = await fetch_item()
        return self.schema(**item_data)

class GenericList(BaseGenericView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._register_list_route()

    def _register_list_route(self):
        # Add filter_fields to OpenAPI documentation dynamically
        parameters = []
        if self.filter_fields:
            for field in self.filter_fields:
                parameters.append({
                    "name": field,
                    "in": "query",
                    "required": False,
                    "schema": {"type": "string"},
                    "description": f"Filter by {field}"
                })
        
        @self.router.get("/", response_model=PaginatedResponse[Any], openapi_extra={"parameters": parameters})
        # @cache(key_prefix=f"backbone:{self.prefix}:list")
        async def list(
            request: Request,
            user: Optional[UserOut] = Depends(self.perm_dep),
            page: int = Query(None, ge=1),
            page_size: int = Query(None, ge=1, le=100),
            skip: int = Query(None, ge=0),
            limit: int = Query(None, ge=1, le=100),
            search: Optional[str] = None,
            sort: Optional[str] = None
        ):
            await self._resolve_context(request)
            
            # Default values if not provided
            page = page or 1
            page_size = page_size or 10
            
            # If skip/limit are provided, calculate page/page_size for consistency
            if skip is not None and limit is not None:
                page_size = limit
                page = (skip // limit) + 1
            
            query = {"is_deleted": {"$ne": True}}
            if search and self.search_fields:
                query["$or"] = [{field: {"$regex": search, "$options": "i"}} for field in self.search_fields]
            
            from urllib.parse import unquote
            from beanie import PydanticObjectId
            
            for key, val in request.query_params.items():
                key = unquote(key)
                if key in ["page", "page_size", "search", "sort", "skip", "limit"]:
                    continue
                
                # Determine the field name for filter check
                field_name = key.split("__")[0] if "__" in key else key
                
                # Check if this field is allowed for filtering
                is_allowed = False
                if self.filter_fields:
                    if field_name in self.filter_fields or key in self.filter_fields:
                        is_allowed = True
                    else:
                        # Handle dot notation partially (e.g. category in filter_fields allows category.name)
                        for f in self.filter_fields:
                            if field_name.startswith(f + ".") or f == field_name:
                                is_allowed = True
                                break
                
                if is_allowed:
                    # Simple type conversion
                    if isinstance(val, str):
                        if val.lower() == 'true': val = True
                        elif val.lower() == 'false': val = False
                        elif val.isdigit(): val = int(val)
                    
                    if "__" in key:
                        field, op = key.split("__", 1)
                        
                        # Special handling for DBRef fields ($id, $ref)
                        # MongoDB handles owner.$id automatically in queries, but we must ensure it's not treated as an operator
                        
                        # Handle ObjectId conversion for related fields
                        if any(suffix in field for suffix in [".id", ".$id", "_id"]):
                            try:
                                if isinstance(val, str) and "," in val:
                                    val = [PydanticObjectId(v.strip()) for v in val.split(",")]
                                else:
                                    val = PydanticObjectId(str(val))
                            except: pass
                            
                        if op == "ne": query[field] = {"$ne": val}
                        elif op == "in": query[field] = {"$in": val if isinstance(val, list) else val.split(",")}
                        # ...
                        elif op == "nin": query[field] = {"$nin": val if isinstance(val, list) else val.split(",")}
                        elif op == "gt": query[field] = {"$gt": val}
                        elif op == "gte": query[field] = {"$gte": val}
                        elif op == "lt": query[field] = {"$lt": val}
                        elif op == "lte": query[field] = {"$lte": val}
                    else:
                        # Handle ObjectId conversion for direct fields
                        if any(suffix in key for suffix in [".id", ".$id", "_id"]):
                            try:
                                val = PydanticObjectId(str(val))
                            except: pass
                        query[key] = val
            
            skip_val = (page - 1) * page_size
            
            results = await self.repository.get_all(
                query, 
                skip=skip_val, 
                limit=page_size, 
                projection=self._get_projection(),
                populate_fields=self.populate_fields
            )
            total = await self.repository.count(query)
            
            return {
                "total": total,
                "count": total, # For compatibility
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size,
                "results": results
            }

class GenericCreate(BaseGenericView):
    def __init__(self, *args, **kwargs):
        # Default use_auth to True for creation unless explicitly set
        if "use_auth" not in kwargs:
            kwargs["use_auth"] = True
        super().__init__(*args, **kwargs)
        self._register_create_route()

    def _register_create_route(self):
        from datetime import datetime, timezone
        @self.router.post("/", response_model=self.schema, status_code=201)
        @cache(expire=30, include_ip=True, key_prefix=f"backbone:{self.prefix}:create") # Idempotency
        async def create(request: Request, data: self.schema, user: Optional[UserOut] = Depends(self.perm_dep)):
            await self._resolve_context(request)
            validated_data = data.model_dump(by_alias=True, exclude={"id"})
            
            # Prepare audit fields
            audit_data = {
                "created_at": datetime.now(timezone.utc),
                "is_deleted": False
            }
            if user:
                audit_data["created_by"] = str(user.id)
                
            validated_data.update(audit_data)
            result = await self.repository.create(validated_data)
            await self._invalidate_cache()
            return result

class GenericRetrieve(BaseGenericView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._register_retrieve_route()

    def _register_retrieve_route(self):
        @self.router.get("/{pk}", response_model=Any)
        @cache(key_prefix=f"backbone:cache:{self.prefix}:detail")
        async def retrieve(request: Request, pk: str, user: Optional[UserOut] = Depends(self.perm_dep)):
            await self._resolve_context(request)
            # We bypass the internal _get_object_internal and do it directly to support projection/population
            # and for the decorator to work perfectly
            query = {
                "$or": [{self.lookup_field: pk}, {"id": pk}],
                "is_deleted": False
            }
            item = await self.repository.get_one(
                query,
                populate_fields=self.populate_fields
            )
            if not item:
                raise HTTPException(status_code=404, detail="Item not found")
            
            for permission_class in self.permission_classes:
                perm = permission_class(request, user)
                if not await perm.has_object_permission(item):
                    raise HTTPException(status_code=403, detail="Object-level access denied")
            
            # Emit Signal for analytics (View counting, etc.)
            from ..core.signals import signals
            try:
                await signals.on_view.emit(item, model_class=self.schema, request=request, user=user)
            except Exception:
                pass 
            
            return item

class GenericUpdate(BaseGenericView):
    def __init__(self, *args, **kwargs):
        kwargs["use_auth"] = True
        super().__init__(*args, **kwargs)
        self._register_update_route()

    def _register_update_route(self):
        @self.router.patch("/{pk}", response_model=self.schema)
        async def update(request: Request, pk: str, data: Dict[str, Any], user: UserOut = Depends(self.perm_dep)):
            # Force validation by creating a partial model if needed, but for now simple Dict
            item = await self._get_object_internal(pk, request, user, use_cache=False)
            update_data = {k: v for k, v in data.items() if v is not None}
            from datetime import datetime, timezone
            update_data["updated_at"] = datetime.now(timezone.utc)
            update_data["updated_by"] = str(user.id)
            
            query = {"$or": [{self.lookup_field: pk}, {"id": pk}]}
            result = await self.repository.update(query, update_data)
            await self._invalidate_cache()
            return result

class GenericDelete(BaseGenericView):
    def __init__(self, *args, **kwargs):
        kwargs["use_auth"] = True
        super().__init__(*args, **kwargs)
        self._register_delete_route()

    def _register_delete_route(self):
        @self.router.delete("/{pk}", status_code=204)
        async def delete(request: Request, pk: str, user: UserOut = Depends(self.perm_dep)):
            item = await self._get_object_internal(pk, request, user, use_cache=False)
            query = {"$or": [{self.lookup_field: pk}, {"id": pk}]}
            await self.repository.delete(query, soft=True)
            await self._invalidate_cache()
            return None

class GenericCrud(GenericList, GenericCreate, GenericRetrieve, GenericUpdate, GenericDelete):
    """
    Combined CRUD view with all standard operations.
    """
    def __init__(self, *args, **kwargs):
        # We don't call super().__init__ because it would call BaseGenericView and then 
        # all mixins would call it again. Instead, we call each mixin's _register method.
        BaseGenericView.__init__(self, *args, **kwargs)
        self._register_list_route()
        self._register_create_route()
        self._register_retrieve_route()
        self._register_update_route()
        self._register_delete_route()
