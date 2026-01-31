from .interface import IDatabaseRepository
from bson import ObjectId
from typing import Dict, Any, List, Optional, TypeVar, Generic, Type
from pydantic import BaseModel

T = TypeVar("T")

class MongoRepository(IDatabaseRepository[T]):
    def __init__(self, db: Any, collection_name: Optional[str] = None):
        self.db = db
        self.collection = db[collection_name] if collection_name else None

    def initialize(self, schema: Type[BaseModel]):
        if self.collection is None:
            meta = getattr(schema, "Meta", None)
            collection_name = getattr(meta, "collection_name", None)
            if not collection_name:
                raise ValueError(f"Schema {schema.__name__} must define Meta.collection_name or provide it to MongoRepository")
            self.collection = self.db[collection_name]

    def _convert_id(self, query: Dict[str, Any]) -> Dict[str, Any]:
        """Internal helper to convert 'id' or '_id' to ObjectId if needed."""
        new_query = query.copy()
        if "id" in new_query:
            val = new_query.pop("id")
            if isinstance(val, str) and ObjectId.is_valid(val):
                new_query["_id"] = ObjectId(val)
            else:
                new_query["_id"] = val
        elif "_id" in new_query and isinstance(new_query["_id"], str) and ObjectId.is_valid(new_query["_id"]):
            new_query["_id"] = ObjectId(new_query["_id"])
        return new_query

    def _format_item(self, item: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if item:
            item["id"] = str(item.pop("_id"))
        return item

    async def get_all(self, query, skip=0, limit=10, sort=None, projection=None):
        query = self._convert_id(query)
        cursor = self.collection.find(query, projection).skip(skip).limit(limit)
        if sort:
            cursor = cursor.sort(sort)
        items = await cursor.to_list(length=limit)
        return [self._format_item(item) for item in items if item]

    async def get_one(self, filter_query, projection=None):
        filter_query = self._convert_id(filter_query)
        item = await self.collection.find_one(filter_query, projection)
        return self._format_item(item)

    async def create(self, data):
        data.pop("id", None)
        result = await self.collection.insert_one(data)
        return await self.get_one({"_id": result.inserted_id})

    async def update(self, filter_query, data):
        filter_query = self._convert_id(filter_query)
        data.pop("id", None)
        data.pop("_id", None)
        result = await self.collection.find_one_and_update(
            filter_query, 
            {"$set": data},
            return_document=True
        )
        return self._format_item(result)

    async def delete(self, filter_query, soft=True):
        filter_query = self._convert_id(filter_query)
        if soft:
            result = await self.collection.update_one(filter_query, {"$set": {"is_deleted": True}})
            return result.modified_count > 0
        return (await self.collection.delete_one(filter_query)).deleted_count > 0

    async def count(self, query):
        query = self._convert_id(query)
        return await self.collection.count_documents(query)