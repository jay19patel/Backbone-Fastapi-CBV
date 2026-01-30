from fastapi import APIRouter, Request, Query, HTTPException, status, Depends
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from bson import ObjectId
from datetime import datetime
from typing import List, Optional, Any, Type, Dict, Union
from pydantic import BaseModel
import math
from .permissions import IsOwner, BasePermission, PermissionDependency
from .schemas import UserOut, PaginatedResponse

class GenericList:
    """
    Base class for listing functionality with filtering, ordering, and owner isolation.
    """
    def __init__(
        self, 
        db: AsyncIOMotorDatabase,
        schema: Type[BaseModel],
        prefix: str,
        tags: Optional[List[str]] = None,
        search_fields: Optional[List[str]] = None,
        filter_fields: Optional[List[str]] = None,
        ordering_fields: Optional[List[str]] = None,
        permission_classes: Optional[List[Type[BasePermission]]] = None,
        list_fields: Optional[List[str]] = None,
        use_auth: bool = True
    ):
        self.router = APIRouter(prefix=prefix, tags=tags or [prefix.strip("/")])
        self.db = db
        self.schema = schema
        self.use_auth = use_auth
        self.search_fields = search_fields or []
        self.filter_fields = filter_fields or []
        self.ordering_fields = ordering_fields or []
        self.permission_classes = permission_classes or []
        self.list_fields = list_fields
        
        meta = getattr(schema, "Meta", None)
        self.collection_name = getattr(meta, "collection_name", prefix.strip("/"))
        self.collection = self.db[self.collection_name]
        
        self._register_list_route()

    def _get_projection(self):
        if self.list_fields:
            projection = {field: 1 for field in self.list_fields}
            projection["_id"] = 1
            return projection
        return None

    def _register_list_route(self):
        perm_dep = PermissionDependency(self.permission_classes, self.use_auth)

        @self.router.get("/", response_model=PaginatedResponse[Dict[str, Any]])
        async def list(
            request: Request,
            user: Optional[UserOut] = Depends(perm_dep),
            page: int = Query(1, ge=1),
            page_size: int = Query(10, ge=1, le=100),
            search: Optional[str] = None,
            sort: Optional[str] = None,
        ):
            query = {"is_deleted": False}

            # Owner Isolation
            if any(issubclass(p, IsOwner) for p in self.permission_classes):
                if not user:
                    raise HTTPException(status_code=401, detail="Authentication required")
                query["created_by"] = str(user.id)

            # Dynamic Filtering
            query_params = request.query_params
            for field in self.filter_fields:
                if field in query_params:
                    query[field] = query_params[field]

            if search and self.search_fields:
                query["$or"] = [{f: {"$regex": search, "$options": "i"}} for f in self.search_fields]

            projection = self._get_projection()
            cursor = self.collection.find(query, projection).skip((page-1)*page_size).limit(page_size)
            
            if sort and (sort.strip("-") in self.ordering_fields):
                direction = -1 if sort.startswith("-") else 1
                cursor = cursor.sort(sort.strip("-"), direction)
            else:
                cursor = cursor.sort("created_at", -1)

            total = await self.collection.count_documents(query)
            items = await cursor.to_list(length=page_size)
            for item in items: item["id"] = str(item["_id"])

            return {
                "total": total, "page": page, "page_size": page_size,
                "total_pages": math.ceil(total / page_size), "results": items
            }

class GenericCrud(GenericList):
    """
    Consolidated View for Full CRUD logic.
    Inherits listing functionality from GenericList.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._register_crud_routes()

    def _register_crud_routes(self):
        perm_dep = PermissionDependency(self.permission_classes, self.use_auth)

        async def get_object(
            pk: str, 
            request: Request, 
            user: Optional[UserOut] = Depends(perm_dep)
        ) -> dict:
            try:
                obj_id = ObjectId(pk)
            except:
                raise HTTPException(status_code=400, detail="Invalid ID format")
                
            item = await self.collection.find_one({"_id": obj_id, "is_deleted": False})
            if not item:
                raise HTTPException(status_code=404, detail="Item not found")
            
            for permission_class in self.permission_classes:
                perm = permission_class(request, user)
                if not await perm.has_object_permission(item):
                    raise HTTPException(status_code=403, detail="Object-level access denied")
            return item

        @self.router.post("/", response_model=self.schema, status_code=201)
        async def create(
            request: Request, 
            data: dict, 
            user: UserOut = Depends(perm_dep)
        ):
            validated_data = self.schema(**data).model_dump(by_alias=True, exclude={"id"})
            validated_data.update({
                "created_at": datetime.utcnow(),
                "created_by": str(user.id),
                "is_deleted": False
            })
            result = await self.collection.insert_one(validated_data)
            return await self.collection.find_one({"_id": result.inserted_id})

        @self.router.get("/{pk}/", response_model=self.schema)
        async def get(item: dict = Depends(get_object)):
            return item

        @self.router.patch("/{pk}/", response_model=self.schema)
        async def update(
            data: dict, 
            user: UserOut = Depends(perm_dep),
            item: dict = Depends(get_object)
        ):
            update_data = data.copy()
            update_data.update({
                "updated_at": datetime.utcnow(),
                "updated_by": str(user.id)
            })
            await self.collection.update_one({"_id": item["_id"]}, {"$set": update_data})
            return await self.collection.find_one({"_id": item["_id"]})

        @self.router.delete("/{pk}/")
        async def delete(
            user: UserOut = Depends(perm_dep),
            item: dict = Depends(get_object)
        ):
            await self.collection.update_one(
                {"_id": item["_id"]},
                {"$set": {
                    "is_deleted": True, 
                    "deleted_at": datetime.utcnow(), 
                    "deleted_by": str(user.id)
                }}
            )
            return {"detail": "Deleted"}

    async def sync_indexes(self):
        meta = getattr(self.schema, "Meta", None)
        if meta and hasattr(meta, "indexes"):
            for index in meta.indexes:
                fields = [(field, 1) for field in index["fields"]]
                await self.collection.create_index(fields, unique=index.get("unique", False))
