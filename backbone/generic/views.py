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
        cache_ttl: int = 300
    ):
        self.router = APIRouter(prefix=prefix, tags=tags or [prefix.strip("/")])
        self.schema = schema
        self.prefix = prefix
        self.cache_ttl = cache_ttl
        
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
            item = await self.repository.get_one({"id": pk, "is_deleted": False})
            if not item:
                raise HTTPException(status_code=404, detail="Item not found")
            
            for permission_class in self.permission_classes:
                perm = permission_class(request, user)
                if not await perm.has_object_permission(item):
                    raise HTTPException(status_code=403, detail="Object-level access denied")
            return item.model_dump(by_alias=True)

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
        @self.router.get("/", response_model=PaginatedResponse[Any])
        @cache(key_prefix=f"backbone:{self.prefix}:list")
        async def list(
            request: Request,
            user: Optional[UserOut] = Depends(self.perm_dep),
            page: int = Query(1, ge=1),
            page_size: int = Query(10, ge=1, le=100),
            search: Optional[str] = None,
            sort: Optional[str] = None
        ):
            await self._resolve_context(request)
            
            query = {"is_deleted": False}
            if search and self.search_fields:
                query["$or"] = [{field: {"$regex": search, "$options": "i"}} for field in self.search_fields]
            
            skip = (page - 1) * page_size
            results = await self.repository.get_all(query, skip=skip, limit=page_size, projection=self._get_projection())
            total = await self.repository.count(query)
            
            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size,
                "results": results
            }

class GenericCreate(BaseGenericView):
    def __init__(self, *args, **kwargs):
        kwargs["use_auth"] = True
        super().__init__(*args, **kwargs)
        self._register_create_route()

    def _register_create_route(self):
        from datetime import datetime, timezone
        @self.router.post("/", response_model=self.schema, status_code=201)
        @cache(expire=30, include_ip=True, key_prefix=f"backbone:{self.prefix}:create") # Idempotency
        async def create(request: Request, data: self.schema, user: UserOut = Depends(self.perm_dep)):
            await self._resolve_context(request)
            validated_data = data.model_dump(by_alias=True, exclude={"id"})
            validated_data.update({
                "created_at": datetime.now(timezone.utc),
                "created_by": str(user.id),
                "is_deleted": False
            })
            result = await self.repository.create(validated_data)
            await self._invalidate_cache()
            return result

class GenericRetrieve(BaseGenericView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._register_retrieve_route()

    def _register_retrieve_route(self):
        @self.router.get("/{pk}", response_model=self.schema)
        @cache(key_prefix=f"backbone:cache:{self.prefix}:detail")
        async def retrieve(request: Request, pk: str, user: Optional[UserOut] = Depends(self.perm_dep)):
            await self._resolve_context(request)
            # We bypass the internal _get_object_internal and do it directly for the decorator to work perfectly
            item = await self.repository.get_one({"id": pk, "is_deleted": False})
            if not item:
                raise HTTPException(status_code=404, detail="Item not found")
            
            for permission_class in self.permission_classes:
                perm = permission_class(request, user)
                if not await perm.has_object_permission(item):
                    raise HTTPException(status_code=403, detail="Object-level access denied")
            
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
            
            result = await self.repository.update({"id": pk}, update_data)
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
            await self.repository.delete({"id": pk}, soft=True)
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
