from fastapi import APIRouter, Request, Query, HTTPException, status, Depends
from datetime import datetime
from typing import List, Optional, Any, Type, Dict, Union
from pydantic import BaseModel
import math
from .permissions import IsOwner, BasePermission, PermissionDependency
from .schemas import UserOut, PaginatedResponse
from .interface import IDatabaseRepository

class BaseGenericView:
    """
    Base class for all Generic components. Handles initialization and shared logic.
    """
from .repositories import MongoRepository

# Global Registry for components that need startup actions (like indexing)
REGISTERED_COMPONENTS: List[Any] = []

class BaseGenericView:
    """
    Base class for all Generic components. Handles initialization and shared logic.
    """
    def __init__(
        self, 
        schema: Type[BaseModel],
        prefix: str,
        repository: Optional[IDatabaseRepository] = None,
        database: Any = None, # Accept database instance directly
        tags: Optional[List[str]] = None,
        search_fields: Optional[List[str]] = None,
        filter_fields: Optional[List[str]] = None,
        ordering_fields: Optional[List[str]] = None,
        permission_classes: Optional[List[Type[BasePermission]]] = None,
        list_fields: Optional[List[str]] = None,
        use_auth: bool = True
    ):
        self.router = APIRouter(prefix=prefix, tags=tags or [prefix.strip("/")])
        
        # Automatic Repository Wiring
        if repository:
            self.repository = repository
        elif database is not None:
             # Default to MongoRepository if database is provided
            self.repository = MongoRepository(database)
        else:
            raise ValueError("Either 'repository' or 'database' must be provided.")

        self.schema = schema
        
        # Initialize repository with schema metadata
        self.repository.initialize(self.schema)
        
        self.use_auth = use_auth
        self.search_fields = search_fields or []
        self.filter_fields = filter_fields or []
        self.ordering_fields = ordering_fields or []
        self.permission_classes = permission_classes or []
        self.list_fields = list_fields
        
        self.perm_dep = PermissionDependency(self.permission_classes, self.use_auth)
        
        # Auto-register for lifecycle events
        REGISTERED_COMPONENTS.append(self)

    def _get_projection(self):
        if self.list_fields:
            projection = {field: 1 for field in self.list_fields}
            projection["_id"] = 1 # repository handles mapping to "id"
            return projection
        return None

    async def _get_object_internal(self, pk: str, request: Request, user: Optional[UserOut]) -> dict:
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
        @self.router.get("/", response_model=PaginatedResponse[Dict[str, Any]])
        async def list(
            request: Request,
            user: Optional[UserOut] = Depends(self.perm_dep),
            page: int = Query(1, ge=1),
            page_size: int = Query(10, ge=1, le=100),
            search: Optional[str] = None,
            sort: Optional[str] = None,
        ):
            query = {"is_deleted": False}
            if any(issubclass(p, IsOwner) for p in self.permission_classes):
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
            return await self.repository.update({"id": item["id"]}, update_data)

class GenericDelete(BaseGenericView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._register_delete_route()

    def _register_delete_route(self):
        @self.router.delete("/{pk}/")
        async def delete(request: Request, pk: str, user: UserOut = Depends(self.perm_dep)):
            item = await self._get_object_internal(pk, request, user)
            await self.repository.delete(
                {"id": item["id"]},
                soft=True
            )
            # Add metadata for soft delete if needed, but repository.delete(soft=True) should handle it.
            # However, BaseGenericView expects to manage created_at/by etc.
            # Let's update the item to record WHO deleted it if it's a soft delete.
            await self.repository.update({"id": item["id"]}, {
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
        # Index creation is DB specific. 
        # For MongoDB, we can keep it here if the repository is specifically MongoRepository
        if hasattr(self.repository, "collection"):
            meta = getattr(self.schema, "Meta", None)
            if meta and hasattr(meta, "indexes"):
                for index in meta.indexes:
                    fields = [(field, 1) for field in index["fields"]]
                    await self.repository.collection.create_index(fields, unique=index.get("unique", False))
