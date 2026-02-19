from typing import List, Optional, Dict, Any, TypeVar, Generic, Type
from bson import ObjectId
from pydantic import BaseModel
from beanie import Document, PydanticObjectId
from ..schemas import PaginatedResponse
from datetime import datetime, timezone
from .signals import signals

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

    @staticmethod
    def _sanitize(data: Any) -> Any:
        if isinstance(data, dict):
            return {k: BeanieRepository._sanitize(v) for k, v in data.items()}
        if isinstance(data, list):
            return [BeanieRepository._sanitize(v) for v in data]
        if isinstance(data, ObjectId):
            return str(data)
        from beanie import Link
        if isinstance(data, Link):
            if hasattr(data, "ref"): return str(data.ref.id)
            if hasattr(data, "id"): return str(data.id)
            return str(data)
        return data

    async def get_all(
        self, 
        query: Dict[str, Any], 
        skip: int = 0, 
        limit: int = 10, 
        sort: Optional[Any] = None, 
        projection: Optional[Dict[str, int]] = None,
        populate_fields: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetches all documents matching the query, with support for:
        - Pagination (skip, limit)
        - Sorting
        - Projection (selecting specific fields)
        - Population (joining with other collections via $lookup)
        
        Returns:
            List[Dict[str, Any]]: A list of dictionaries representing the documents. 
            We return dicts because aggregation results are dicts and might contain populated fields 
            that don't match the strict original schema.
        """
        pipeline = []

        # 1. Match (Filtering)
        # Beanie's find(query) handles some magic, but for aggregation we need raw query
        # We might need to handle ID conversion if query uses "id" vs "_id"
        if "id" in query:
            query["_id"] = query.pop("id")
            
        pipeline.append({"$match": query})

        # 2. Sort
        if sort:
            # Sort format from beanie/pymongo: [("field", 1), ("other", -1)] or similar
            # If it's a list of tuples, convert to dict for $sort if needed, or just use it if pymongo supports list
            # $sort in aggregation expects a dict like {"field": 1} usually, or strictly ordered dict
            sort_stage = {}
            if isinstance(sort, list):
                for field, direction in sort:
                    sort_stage[field] = direction
            elif isinstance(sort, dict):
                sort_stage = sort
            
            if sort_stage:
                pipeline.append({"$sort": sort_stage})

        # 3. Skip & Limit
        pipeline.append({"$skip": skip})
        pipeline.append({"$limit": limit})

        # 4. Lookup (Population)
        # populate_fields expected format: 
        #   {"local_field": "target_collection"}  -> Simple, alias = local_field
        #   {"local_field": {"collection": "target_collection", "field": "alias_name"}} -> Advanced
        if populate_fields:
            for local_field, config in populate_fields.items():
                target_collection = config
                alias = local_field
                
                if isinstance(config, dict):
                    target_collection = config.get("collection")
                    alias = config.get("field", local_field)
                
                pipeline.append({
                    "$lookup": {
                        "from": target_collection,
                        "localField": local_field,
                        "foreignField": "_id",
                        "as": alias
                    }
                })
                # If we are mapping to a SINGLE user/object from a single ID, we might want to unwind
                # But GenericCrud usually returns list. The UI/Frontend can handle it or we add unwind option.
                # For now, standard $lookup returns an array.
                
                # OPTIONAL: Unwind if the local field is a scalar ID and we want a single object, 
                # but detecting scalar vs array in generic way without schema inspection is hard.
                # We'll leave it as array for consistency or let user specify "unwind": True in config later.

        # 5. Project
        if projection:
            pipeline.append({"$project": projection})

        # Execute Aggregation
        # Execute Aggregation
        results = await self.document_class.get_pymongo_collection().aggregate(pipeline).to_list(length=None)
        
        cleaned_results = []
        for doc in results:
            # Sanitize ObjectIds recursively
            doc = self._sanitize(doc)
            if "_id" in doc:
                doc["id"] = doc["_id"]
            cleaned_results.append(doc)
        
        return cleaned_results

    async def get_one(
        self, 
        filter_query: Dict[str, Any], 
        projection: Optional[Dict[str, int]] = None,
        populate_fields: Optional[Dict[str, str]] = None
    ) -> Optional[Dict[str, Any]]:
        # Handle "id" -> "_id" mapping
        if "id" in filter_query:
            filter_query["_id"] = filter_query.pop("id")
            
        if "_id" in filter_query and isinstance(filter_query["_id"], str):
            try:
                filter_query["_id"] = PydanticObjectId(filter_query["_id"])
            except:
                pass

        if not populate_fields and not projection:
            # Use standard Beanie find_one if no complex operations
            doc = await self.document_class.find_one(filter_query)
            return doc.model_dump(by_alias=True) if doc else None

        # Use Aggregation for Population/Projection
        pipeline = [{"$match": filter_query}]

        if populate_fields:
            for local_field, config in populate_fields.items():
                target_collection = config
                alias = local_field
                
                if isinstance(config, dict):
                    target_collection = config.get("collection")
                    alias = config.get("field", local_field)

                pipeline.append({
                    "$lookup": {
                        "from": target_collection,
                        "localField": local_field,
                        "foreignField": "_id", 
                        "as": alias 
                    }
                })

        if projection:
            pipeline.append({"$project": projection})

        results = await self.document_class.get_pymongo_collection().aggregate(pipeline).to_list(length=1)
        
        if results:
            doc = self._sanitize(results[0])
            if "_id" in doc:
                doc["id"] = doc["_id"]
            return doc
            
        return None

    async def create(self, data: Dict[str, Any]) -> T:
        obj = self.document_class(**data)
        await obj.insert()
        return obj

    async def update(self, filter_query: Dict[str, Any], data: Dict[str, Any]) -> Optional[T]:
        if "id" in filter_query:
            filter_query["_id"] = filter_query.pop("id")

        if "_id" in filter_query and isinstance(filter_query["_id"], str):
            try:
                filter_query["_id"] = PydanticObjectId(filter_query["_id"])
            except:
                pass
            
        item = await self.document_class.find_one(filter_query)
        if item:
            await item.set(data)
            return item
        return None

    async def delete(self, filter_query: Dict[str, Any], soft: bool = True) -> bool:
        if "id" in filter_query:
            filter_query["_id"] = filter_query.pop("id")

        if "_id" in filter_query and isinstance(filter_query["_id"], str):
            try:
                filter_query["_id"] = PydanticObjectId(filter_query["_id"])
            except:
                pass
            
        item = await self.document_class.find_one(filter_query)
        if not item:
            return False
            
        if soft:
            await item.set({"is_deleted": True, "deleted_at": datetime.now(timezone.utc)})
        else:
            await item.delete()
        return True

    async def count(self, query: Dict[str, Any]) -> int:
        return await self.document_class.find(query).count()
