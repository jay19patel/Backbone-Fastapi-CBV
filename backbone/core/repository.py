from typing import List, Optional, Dict, Any, TypeVar, Generic, Type
from pydantic import BaseModel
from beanie import Document
from ..schemas import PaginatedResponse
from datetime import datetime

T = TypeVar('T', bound=BaseModel)

class BeanieRepository(Generic[T]):
    def __init__(self, db: Any = None):
        self.db = db
        self.document_class: Optional[Type[Document]] = None

    def initialize(self, schema: Type[BaseModel]):
        if issubclass(schema, Document):
            self.document_class = schema
        else:
            # Fallback if needed, though GenericCrud expects Document for BeanieRepo
            pass

    async def get_all(
        self, 
        query: Dict[str, Any], 
        skip: int = 0, 
        limit: int = 10, 
        sort: Optional[Any] = None, 
        projection: Optional[Dict[str, int]] = None
    ) -> List[T]:
        find_query = self.document_class.find(query)
        if sort:
            find_query = find_query.sort(sort)
        
        results = await find_query.skip(skip).limit(limit).project(self.document_class).to_list()
        return results

    async def get_one(self, filter_query: Dict[str, Any], projection: Optional[Dict[str, int]] = None) -> Optional[T]:
        # Handle "id" -> "_id" mapping for Beanie
        if "id" in filter_query:
            filter_query["_id"] = filter_query.pop("id")
            
        return await self.document_class.find_one(filter_query)

    async def create(self, data: Dict[str, Any]) -> T:
        obj = self.document_class(**data)
        await obj.insert()
        return obj

    async def update(self, filter_query: Dict[str, Any], data: Dict[str, Any]) -> Optional[T]:
        if "id" in filter_query:
            filter_query["_id"] = filter_query.pop("id")
            
        item = await self.document_class.find_one(filter_query)
        if item:
            await item.set(data)
            return item
        return None

    async def delete(self, filter_query: Dict[str, Any], soft: bool = True) -> bool:
        if "id" in filter_query:
            filter_query["_id"] = filter_query.pop("id")
            
        item = await self.document_class.find_one(filter_query)
        if not item:
            return False
            
        if soft:
            await item.set({"is_deleted": True, "deleted_at": datetime.utcnow()})
        else:
            await item.delete()
        return True

    async def count(self, query: Dict[str, Any]) -> int:
        return await self.document_class.find(query).count()
