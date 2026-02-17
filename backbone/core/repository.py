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
    ) -> List[Dict[str, Any]]:
        if not self.document_class:
            return []
        
        # Beanie find
        find_query = self.document_class.find(query)
        
        if sort:
            find_query = find_query.sort(sort)
        
        find_query = find_query.skip(skip).limit(limit)
        
        if projection:
            find_query = find_query.project(projection_model=None) # Beanie projection is tricky with dicts
            # For now, let's just fetch full docs and dump them, or use Pydantic projection if passed
            # A simple approach for this 'dict' return interface:
            docs = await find_query.to_list()
            return [doc.model_dump(by_alias=True) for doc in docs]
        
        docs = await find_query.to_list()
        return [doc.model_dump(by_alias=True) for doc in docs]

    async def get_one(self, filter_query: Dict[str, Any], projection: Optional[Dict[str, int]] = None) -> Optional[Dict[str, Any]]:
        if not self.document_class:
            return None
            
        doc = await self.document_class.find_one(filter_query)
        if doc:
            return doc.model_dump(by_alias=True)
        return None

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.document_class:
            raise ValueError("Document class not initialized")
        
        # Validate and create
        doc = self.document_class(**data)
        await doc.insert()
        return doc.model_dump(by_alias=True)

    async def update(self, filter_query: Dict[str, Any], data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.document_class:
            return None
            
        doc = await self.document_class.find_one(filter_query)
        if not doc:
            return None
            
        # Update fields
        await doc.set(data)
        return doc.model_dump(by_alias=True)

    async def delete(self, filter_query: Dict[str, Any], soft: bool = True) -> bool:
        if not self.document_class:
            return False
            
        doc = await self.document_class.find_one(filter_query)
        if not doc:
            return False
            
        if soft:
            doc.is_deleted = True
            # We can also set deleted_at here if we want, but usually passed in 'data' of update? 
            # The interface says 'delete', so we handle it here.
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
