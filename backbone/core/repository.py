from typing import Any, Dict, List, Optional, Type, TypeVar, Union
from beanie import Document, PydanticObjectId
from pydantic import BaseModel
from .interface import IDatabaseRepository

T = TypeVar("T", bound=Document)

class BeanieRepository(IDatabaseRepository[T]):
    def __init__(self, db: Any = None, collection_name: Optional[str] = None):
        # Beanie doesn't need explicit db instance per repo, it uses global init
        self.db = db
        self.document_class: Optional[Type[T]] = None

    def initialize(self, schema: Type[BaseModel]):
        # In Beanie, the schema IS the document class (or we map it)
        # For this refactor, we assume the 'schema' passed in Generic views might be a Beanie Document
        # OR we might need a way to map Pydantic Schema -> Beanie Document
        if issubclass(schema, Document):
            self.document_class = schema
        else:
            # Fallback or strict requirement: generic views must use Beanie Documents as schema
            # Or we need a mapping registry. For now, let's assume strict usage.
            # However, existing GenericCrud uses Pydantic schemas (UserSchema). 
            # We might need to change GenericCrud to accept Document classes.
            pass

    async def get_all(
        self, 
        query: Dict[str, Any], 
        skip: int = 0, 
        limit: int = 10, 
        sort: Optional[Any] = None, 
        projection: Optional[Dict[str, int]] = None
    ) -> List[T]:
        if not self.document_class:
            return []
        
        # Beanie find
        find_query = self.document_class.find(query)
        
        if sort:
            find_query = find_query.sort(sort)
        
        find_query = find_query.skip(skip).limit(limit)
        
        if projection:
            find_query = find_query.project(projection_model=None) 

        docs = await find_query.to_list()
        return docs

    async def get_one(self, filter_query: Dict[str, Any], projection: Optional[Dict[str, int]] = None) -> Optional[T]:
        if not self.document_class:
            return None
            
        doc = await self.document_class.find_one(filter_query)
        return doc

    async def create(self, data: Dict[str, Any]) -> T:
        if not self.document_class:
            raise ValueError("Document class not initialized")
        
        # Validate and create
        doc = self.document_class(**data)
        await doc.insert()
        return doc

    async def update(self, filter_query: Dict[str, Any], data: Dict[str, Any]) -> Optional[T]:
        if not self.document_class:
            return None
            
        doc = await self.document_class.find_one(filter_query)
        if not doc:
            return None
            
        # Update fields
        req = {k: v for k, v in data.items()}
        await doc.set(req)
        return doc

    async def delete(self, filter_query: Dict[str, Any], soft: bool = True) -> bool:
        if not self.document_class:
            return False
            
        doc = await self.document_class.find_one(filter_query)
        if not doc:
            return False
            
        if soft:
            doc.is_deleted = True
            from datetime import datetime
            doc.deleted_at = datetime.utcnow()
            await doc.save()
            return True
        else:
            await doc.delete()
            return True

    async def count(self, query: Dict[str, Any]) -> int:
        if not self.document_class:
            return 0
        return await self.document_class.find(query).count()

class UserRepository(BeanieRepository[T]):
    async def get_by_email(self, email: str) -> Optional[T]:
        if not self.document_class:
            return None
        return await self.document_class.find_one({"email": email})
