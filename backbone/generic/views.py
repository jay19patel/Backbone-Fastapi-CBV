from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from typing import List, Optional, Any, Type, Dict, Union
from beanie import Document
from ..core.repository import BeanieRepository
from ..core.permissions import IsOwner, BasePermission, PermissionDependency, AllowAny, IsAdminUser
from ..schemas import UserOut, PaginatedResponse
from ..core.config import BackboneConfig
from ..utils.cache import CacheService
import hashlib
import json

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
        self.cache: Optional[CacheService] = None

    async def _resolve_context(self, request: Request):
        """
        Ensure the repository and cache have the correct DB/Client from BackboneConfig.
        """
        config = request.app.state.backbone_config
        if not self.repository.db:
            self.repository.db = config.database
        
        if not self.cache:
            self.cache = CacheService(
                redis_client=getattr(config, "redis_client", None),
                enabled=getattr(config.config, "CACHE_ENABLED", False)
            )

    async def _invalidate_cache(self):
        if self.cache:
            pattern = f"backbone:cache:{self.prefix}:*"
            await self.cache.delete_pattern(pattern)

    def _get_projection(self):
        if self.list_fields:
            projection = {field: 1 for field in self.list_fields}
            projection["_id"] = 1
            return projection
        return None

    async def _get_object_internal(self, pk: str, request: Request, user: Optional[UserOut], use_cache: bool = True) -> Any:
        await self._resolve_context(request)
        
        cache_key = f"backbone:cache:{self.prefix}:detail:{pk}"
        if use_cache and self.cache:
            cached_item = await self.cache.get(cache_key)
            if cached_item:
                return self.schema(**cached_item)

        item = await self.repository.get_one({"id": pk, "is_deleted": False})
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        
        for permission_class in self.permission_classes:
            perm = permission_class(request, user)
            if not await perm.has_object_permission(item):
                raise HTTPException(status_code=403, detail="Object-level access denied")
        
        if use_cache and self.cache:
            await self.cache.set(cache_key, item.model_dump(by_alias=True), ttl=self.cache_ttl)
            
        return item

class GenericList(BaseGenericView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._register_list_route()

    def _register_list_route(self):
        @self.router.get("/", response_model=PaginatedResponse[Any])
        async def list(
            request: Request,
            user: Optional[UserOut] = Depends(self.perm_dep),
            page: int = Query(1, ge=1),
            page_size: int = Query(10, ge=1, le=100),
            search: Optional[str] = None,
            sort: Optional[str] = None
        ):
            await self._resolve_context(request)
            
            # Generate Cache Key
            query_params = f"search={search}&sort={sort}&page={page}&page_size={page_size}"
            query_hash = hashlib.md5(query_params.encode()).hexdigest()
            cache_key = f"backbone:cache:{self.prefix}:list:{query_hash}"
            
            if self.cache:
                cached_res = await self.cache.get(cache_key)
                if cached_res:
                    return cached_res

            query = {"is_deleted": False}
            
            if search and self.search_fields:
                query["$or"] = [
                    {field: {"$regex": search, "$options": "i"}} 
                    for field in self.search_fields
                ]
            
            skip = (page - 1) * page_size
            results = await self.repository.get_all(
                query, 
                skip=skip, 
                limit=page_size, 
                projection=self._get_projection()
            )
            total = await self.repository.count(query)
            
            response_data = {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size,
                "results": [r.model_dump(by_alias=True) if hasattr(r, "model_dump") else r for r in results]
            }
            
            if self.cache:
                await self.cache.set(cache_key, response_data, ttl=self.cache_ttl)
                
            return response_data

class GenericCreate(BaseGenericView):
    def __init__(self, *args, **kwargs):
        kwargs["use_auth"] = True
        super().__init__(*args, **kwargs)
        self._register_create_route()

    def _register_create_route(self):
        @self.router.post("/", response_model=self.schema, status_code=201)
        async def create(request: Request, data: self.schema, user: UserOut = Depends(self.perm_dep)):
            await self._resolve_context(request)
            validated_data = data.model_dump(by_alias=True, exclude={"id"})
            validated_data.update({
                "created_at": datetime.utcnow(),
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
        async def retrieve(request: Request, pk: str, user: Optional[UserOut] = Depends(self.perm_dep)):
            return await self._get_object_internal(pk, request, user)

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
            update_data["updated_at"] = datetime.utcnow()
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
