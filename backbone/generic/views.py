from fastapi import APIRouter, Request, Query, HTTPException, status, Depends
from datetime import datetime
from typing import List, Optional, Any, Type, Dict, Union
from pydantic import BaseModel
import math
from ..core.permissions import IsOwner, BasePermission, PermissionDependency, AllowAny, IsAdminUser
from ..schemas import UserOut, PaginatedResponse
from ..core.interface import IDatabaseRepository

class BaseGenericView:
    """
    Base class for all Generic components. Handles initialization and shared logic.
    """
from ..core.repository import BeanieRepository

class BaseGenericView:
    """
    Base class for all Generic components. Handles initialization and shared logic.
    """
    def __init__(
        self, 
        schema: Type[BaseModel],
        prefix: str,
        repository: Optional[IDatabaseRepository] = None,
        database: Any = None, 
        repository_class: Optional[Type[IDatabaseRepository]] = None,
        tags: Optional[List[str]] = None,
        search_fields: Optional[List[str]] = None,
        filter_fields: Optional[List[str]] = None,
        ordering_fields: Optional[List[str]] = None,
        permission_classes: Optional[List[Type[BasePermission]]] = None,
        list_fields: Optional[List[str]] = None,
        use_auth: bool = False
    ):
        self.router = APIRouter(prefix=prefix, tags=tags or [prefix.strip("/")])
        
        # Resolve Repository Class
        active_repo_class = repository_class or BeanieRepository

        # Automatic Repository Wiring
        if repository:
            self.repository = repository
        else:
            self.repository = active_repo_class(database)

        self.schema = schema
        
        # Initialize repository with schema metadata
        self.repository.initialize(self.schema)
        
        self.use_auth = use_auth
        self.search_fields = search_fields or []
        self.filter_fields = filter_fields or []
        self.ordering_fields = ordering_fields or []
        # Ensure permission_classes is a list. User might pass a single class by mistake or we default to empty.
        if permission_classes is None:
            self.permission_classes = []
        elif not isinstance(permission_classes, list):
             # Fallback if a single class is passed (e.g. permission_classes=AllowAny)
            self.permission_classes = [permission_classes]
        else:
            self.permission_classes = permission_classes

        self.list_fields = list_fields
        
        self.perm_dep = PermissionDependency(self.permission_classes, self.use_auth)

    def _get_projection(self):
        if self.list_fields:
            projection = {field: 1 for field in self.list_fields}
            projection["_id"] = 1 # repository handles mapping to "id"
            return projection
        return None

    async def _get_object_internal(self, pk: str, request: Request, user: Optional[UserOut]) -> Any:
        """
        Internal helper for fetching object and checking permissions.
        """
        item = await self.repository.get_one({"id": pk, "is_deleted": False})
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        
        for permission_class in self.permission_classes:
            perm = permission_class(request, user)
            if not await perm.has_object_permission(item):
                raise HTTPException(status_code=403, detail="Object-level access denied")
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
            sort: Optional[str] = None,
        ):
            query = {"is_deleted": False}
            # Smart Permission Logic
            # 1. Default (No permissions) -> Public Access (See all)
            # 2. IsOwner present -> Filter by owner (unless Admin override)
            # 3. IsAuthenticated present -> See all (Authenticated)
            
            is_owner_restricted = any(issubclass(p, IsOwner) for p in self.permission_classes)
            
            # Check for Admin override if IsAdminUser is also in permissions
            has_admin_perm = any(issubclass(p, IsAdminUser) for p in self.permission_classes)
            user_is_admin = user.is_staff if user else False
            
            should_filter_by_owner = False
            
            if is_owner_restricted:
                # If Admin permission is allowed AND user is admin, they bypass owner filter
                if has_admin_perm and user_is_admin:
                    should_filter_by_owner = False
                else:
                    should_filter_by_owner = True
            
            if should_filter_by_owner:
                if not user:
                    raise HTTPException(status_code=401, detail="Authentication required")
                query["created_by"] = str(user.id)

            query_params = request.query_params
            for field in self.filter_fields:
                if field in query_params:
                    query[field] = query_params[field]

            if search and self.search_fields:
                # MongoDB specific $or can be handled by repository if needed, 
                # but for simplicity we keep it here as a Dict that MongoRepository understands.
                # A more advanced SQL repo would translate this.
                query["$or"] = [{f: {"$regex": search, "$options": "i"}} for f in self.search_fields]

            projection = self._get_projection()
            
            # Prepare sort
            sort_val = None
            if sort and (sort.strip("-") in self.ordering_fields):
                direction = -1 if sort.startswith("-") else 1
                sort_val = [(sort.strip("-"), direction)]
            else:
                sort_val = [("created_at", -1)]

            skip = (page - 1) * page_size
            items = await self.repository.get_all(
                query=query, 
                skip=skip, 
                limit=page_size, 
                sort=sort_val, 
                projection=projection
            )
            total = await self.repository.count(query)

            return {
                "total": total, "page": page, "page_size": page_size,
                "total_pages": math.ceil(total / page_size), "results": items
            }

class GenericCreate(BaseGenericView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._register_create_route()

    def _register_create_route(self):
        @self.router.post("/", response_model=self.schema, status_code=201)
        async def create(request: Request, data: dict, user: UserOut = Depends(self.perm_dep)):
            validated_data = self.schema(**data).model_dump(by_alias=True, exclude={"id"})
            validated_data.update({
                "created_at": datetime.utcnow(),
                "created_by": str(user.id),
                "is_deleted": False
            })
            return await self.repository.create(validated_data)

class GenericRetrieve(BaseGenericView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._register_retrieve_route()

    def _register_retrieve_route(self):
        @self.router.get("/{pk}/", response_model=self.schema)
        async def get(request: Request, pk: str, user: Optional[UserOut] = Depends(self.perm_dep)):
            item = await self._get_object_internal(pk, request, user)
            return item

class GenericUpdate(BaseGenericView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._register_update_route()

    def _register_update_route(self):
        @self.router.patch("/{pk}/", response_model=self.schema)
        async def update(request: Request, pk: str, data: dict, user: UserOut = Depends(self.perm_dep)):
            item = await self._get_object_internal(pk, request, user)
            update_data = data.copy()
            update_data.update({
                "updated_at": datetime.utcnow(),
                "updated_by": str(user.id)
            })
            return await self.repository.update({"id": item.id}, update_data)

class GenericDelete(BaseGenericView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._register_delete_route()

    def _register_delete_route(self):
        @self.router.delete("/{pk}/")
        async def delete(request: Request, pk: str, user: UserOut = Depends(self.perm_dep)):
            item = await self._get_object_internal(pk, request, user)
            await self.repository.delete(
                {"id": item.id},
                soft=True
            )
            # Add metadata for soft delete if needed, but repository.delete(soft=True) should handle it.
            # However, BaseGenericView expects to manage created_at/by etc.
            # Let's update the item to record WHO deleted it if it's a soft delete.
            await self.repository.update({"id": item.id}, {
                "deleted_at": datetime.utcnow(), 
                "deleted_by": str(user.id)
            })
            return {"detail": "Deleted"}

class GenericCrud(GenericList, GenericCreate, GenericRetrieve, GenericUpdate, GenericDelete):
    """
    Consolidated View for Full CRUD logic.
    Inherits all routes from granular Generic components.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def sync_indexes(self):
        # Beanie handles indexes automatically via Document.Settings
        pass
