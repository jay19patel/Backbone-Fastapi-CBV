from typing import List, Optional, Dict, Any, TypeVar, Generic, Type, Union
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
    def detect_populate_fields(schema: Type[BaseModel]) -> Dict[str, Any]:
        """
        Detects Beanie Link fields and explicit audit fields and returns populate_fields config.
        """
        detected = {}
        from beanie import Link
        from typing import get_origin, get_args
        
        # Hardcode audit fields mapper
        audit_fields = ["created_by", "updated_by", "deleted_by"]
        for audit_field in audit_fields:
            if audit_field in schema.model_fields:
                detected[audit_field] = {
                    "collection": "users", 
                    "field": audit_field, 
                    "is_string_id": True,
                    "fields": ["id", "email", "full_name"]
                }
        
        for field_name, field_info in schema.model_fields.items():
            if field_name in detected:
                continue

            # Check for Link type
            annotation = field_info.annotation
            origin = get_origin(annotation)
            
            target_model = None
            
            if origin is Link:
                target_model = get_args(annotation)[0]
            elif origin in (list, List):
                 args = get_args(annotation)
                 if args:
                     inner = args[0]
                     if get_origin(inner) is Link:
                         target_model = get_args(inner)[0]
            elif origin is Union or origin is Any: # Handle Optional[Link]
                args = get_args(annotation)
                for arg in args:
                    if get_origin(arg) is Link:
                        target_model = get_args(arg)[0]
                        break
                    # Also handle List[Link] inside Optional
                    if get_origin(arg) in (list, List):
                        inner_args = get_args(arg)
                        if inner_args and get_origin(inner_args[0]) is Link:
                            target_model = get_args(inner_args[0])[0]
                            is_list = True
                            break

            if target_model and hasattr(target_model, "Settings") and hasattr(target_model.Settings, "name"):
                return_fields = getattr(target_model.Settings, "return_link_data", None)
                collection_name = target_model.Settings.name
                config_dict = {"collection": collection_name, "field": field_name, "is_link": True, "is_list": origin in (list, List)}
                
                if return_fields and isinstance(return_fields, list):
                    config_dict["fields"] = return_fields
                else:
                    if collection_name == "users":
                        config_dict["fields"] = ["id", "email", "full_name"]
                        
                detected[field_name] = config_dict
                
        return detected

    @staticmethod
    def _sanitize(data: Any) -> Any:
        if isinstance(data, dict):
            return {k: BeanieRepository._sanitize(v) for k, v in data.items()}
        if isinstance(data, list):
            return [BeanieRepository._sanitize(v) for v in data]
        if isinstance(data, ObjectId) or isinstance(data, PydanticObjectId):
            return str(data)
        from beanie import Link
        from bson.dbref import DBRef
        if isinstance(data, Link):
            if hasattr(data, "ref"): return str(data.ref.id)
            if hasattr(data, "id"): return str(data.id)
            return str(data)
        if isinstance(data, DBRef):
            return str(data.id)
        return data

    @classmethod
    def _prepare_query(cls, query: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively prepares a query dictionary for MongoDB by:
        1. Replacing "id" keys with "_id"
        2. Attempting to convert string IDs to PydanticObjectId/ObjectId safely
        3. Traversing into operators like $or, $and, $in, $ne
        """
        if not isinstance(query, dict):
            return query

        prepared = {}
        for k, v in query.items():
            new_key = "_id" if k == "id" else k
            
            if isinstance(v, dict):
                prepared[new_key] = cls._prepare_query(v)
            elif isinstance(v, list):
                if k in ("$or", "$and", "$nor"):
                    # Process each condition in the list
                    prepared[new_key] = [cls._prepare_query(item) if isinstance(item, dict) else item for item in v]
                elif new_key == "_id" or (isinstance(new_key, str) and (new_key.endswith(".id") or new_key.endswith(".$id"))):
                     # Process $in / $nin lists
                     prepared_list = []
                     for item in v:
                         if isinstance(item, str):
                             try: prepared_list.append(PydanticObjectId(item))
                             except: prepared_list.append(item)
                         else:
                             prepared_list.append(item)
                     prepared[new_key] = prepared_list
                else:
                    prepared[new_key] = v
            elif isinstance(v, str):
                 # Attempt conversion to ObjectId if the key suggests an ID
                 if new_key == "_id" or new_key.endswith(".id") or new_key.endswith(".$id"):
                     try: prepared[new_key] = PydanticObjectId(v)
                     except: prepared[new_key] = v
                 else:
                     prepared[new_key] = v
            else:
                 prepared[new_key] = v
                 
        return prepared

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

        # 1. Split query into local and joined
        local_query = {}
        joined_query = {}
        
        # Prepare the query first to handle ObjectIds
        full_query = self._prepare_query(query)
        
        for k, v in full_query.items():
            if "." in k and not (k.startswith("$") or k.endswith(".id") or k.endswith(".$id")):
                # Likely a joined field (except for DBRef/id fields)
                joined_query[k] = v
            else:
                local_query[k] = v
            
        pipeline.append({"$match": local_query})

        # 2. Lookup (Population)
        if populate_fields:
            for local_field, config in populate_fields.items():
                target_collection = config
                alias = local_field
                is_link = False
                is_string_id = False
                is_list = False
                fields_to_return = None
                
                if isinstance(config, dict):
                    target_collection = config.get("collection")
                    alias = config.get("field", local_field)
                    is_link = config.get("is_link", False)
                    is_string_id = config.get("is_string_id", False)
                    is_list = config.get("is_list", False)
                    fields_to_return = config.get("fields")
                
                # Extract the local value: it could be a string, ObjectId, dict with id, or dict with $id (DBRef)
                if is_list:
                    # For lists (like categories), we need to extract the ID from each element
                    if is_link:
                       local_val_expr = {"$map": {"input": {"$ifNull": [f"${local_field}", []]}, "as": "item", "in": {"$ifNull": ["$$item.id", {"$ifNull": ["$$item.$id", "$$item"]}]}}}
                    else:
                        local_val_expr = {"$ifNull": [f"${local_field}", []]}
                else:
                    if is_link:
                        # In MongoDB aggregations, $id is an operator if used at top level, but safe in path.
                        # DBRefs store the id in a field called `$id`
                        local_val_expr = {"$ifNull": [f"${local_field}.id", {"$ifNull": [f"${local_field}.$id", f"${local_field}"]}]}
                    else:
                        local_val_expr = f"${local_field}"
                    
                inner_match = {}
                if is_string_id and is_list:
                    inner_match = {"$expr": {"$in": [{"$toString": "$_id"}, "$$local_val"]}}
                elif is_string_id:
                    inner_match = {"$expr": {"$eq": ["$_id", {"$toObjectId": "$$local_val"}]}}
                elif is_list:
                    inner_match = {"$expr": {"$in": ["$_id", "$$local_val"]}}
                else:
                    inner_match = {"$expr": {"$eq": ["$_id", "$$local_val"]}}
                    
                inner_pipeline = [{"$match": inner_match}]
                
                if fields_to_return and isinstance(fields_to_return, list):
                    project_stage = {f: 1 for f in fields_to_return}
                    project_stage["id"] = "$_id"
                    project_stage["_id"] = 0
                    inner_pipeline.append({"$project": project_stage})
                else:
                    inner_pipeline.append({"$addFields": {"id": "$_id"}})
                    inner_pipeline.append({"$project": {"_id": 0}})

                pipeline.append({
                    "$lookup": {
                        "from": target_collection,
                        "let": {"local_val": local_val_expr},
                        "pipeline": inner_pipeline,
                        "as": alias
                    }
                })

                if not is_list:
                    pipeline.append({
                        "$unwind": {
                            "path": f"${alias}",
                            "preserveNullAndEmptyArrays": True
                        }
                    })

        # 3. Joined Match (Filtering after population)
        if joined_query:
            pipeline.append({"$match": joined_query})

        # 4. Sort
        if sort:
            sort_stage = {}
            if isinstance(sort, list):
                for field, direction in sort:
                    sort_stage[field] = direction
            elif isinstance(sort, dict):
                sort_stage = sort
            
            if sort_stage:
                pipeline.append({"$sort": sort_stage})

        # 5. Skip & Limit
        # Moving skip/limit after sorting and potential joined filter for accuracy
        pipeline.append({"$skip": skip})
        pipeline.append({"$limit": limit})

        # 6. Project
        if projection:
            pipeline.append({"$project": projection})

        # Execute Aggregation
        results = await self.document_class.get_pymongo_collection().aggregate(pipeline).to_list(length=None)
        
        cleaned_results = []
        for doc in results:
            # First move root _id to id
            if "_id" in doc:
                doc["id"] = str(doc.pop("_id"))
                
            # Then sanitize remaining ObjectIds recursively
            doc = self._sanitize(doc)
            
            cleaned_results.append(doc)
        
        return cleaned_results

    async def get_one(
        self, 
        filter_query: Dict[str, Any], 
        projection: Optional[Dict[str, int]] = None,
        populate_fields: Optional[Dict[str, str]] = None
    ) -> Optional[Dict[str, Any]]:
        filter_query = self._prepare_query(filter_query)

        if not populate_fields and not projection:
            # Use standard Beanie find_one if no complex operations
            doc = await self.document_class.find_one(filter_query)
            if doc:
                dumped = doc.model_dump(by_alias=True)
                if "_id" in dumped:
                    dumped["id"] = str(dumped.pop("_id"))
                sanitized = self._sanitize(dumped)
                return sanitized
            return None

        # Use Aggregation for Population/Projection
        pipeline = [{"$match": filter_query}]

        if populate_fields:
            for local_field, config in populate_fields.items():
                target_collection = config
                alias = local_field
                is_link = False
                is_string_id = False
                is_list = False
                fields_to_return = None
                
                if isinstance(config, dict):
                    target_collection = config.get("collection")
                    alias = config.get("field", local_field)
                    is_link = config.get("is_link", False)
                    is_string_id = config.get("is_string_id", False)
                    is_list = config.get("is_list", False)
                    fields_to_return = config.get("fields")
                
                # Extract the local value: it could be a string, ObjectId, dict with id, or dict with $id (DBRef)
                if is_list:
                    # For lists (like categories), we need to extract the ID from each element
                    if is_link:
                       local_val_expr = {"$map": {"input": {"$ifNull": [f"${local_field}", []]}, "as": "item", "in": {"$ifNull": ["$$item.id", {"$ifNull": ["$$item.$id", "$$item"]}]}}}
                    else:
                        local_val_expr = {"$ifNull": [f"${local_field}", []]}
                else:
                    if is_link:
                        local_val_expr = {"$ifNull": [f"${local_field}.id", {"$ifNull": [f"${local_field}.$id", f"${local_field}"]}]}
                    else:
                        local_val_expr = f"${local_field}"
                    
                inner_match = {}
                if is_string_id and is_list:
                    inner_match = {"$expr": {"$in": [{"$toString": "$_id"}, "$$local_val"]}}
                elif is_string_id:
                    inner_match = {"$expr": {"$eq": ["$_id", {"$toObjectId": "$$local_val"}]}}
                elif is_list:
                    inner_match = {"$expr": {"$in": ["$_id", "$$local_val"]}}
                else:
                    inner_match = {"$expr": {"$eq": ["$_id", "$$local_val"]}}
                    
                inner_pipeline = [{"$match": inner_match}]
                
                if fields_to_return and isinstance(fields_to_return, list):
                    project_stage = {f: 1 for f in fields_to_return}
                    project_stage["id"] = "$_id"
                    project_stage["_id"] = 0
                    inner_pipeline.append({"$project": project_stage})
                else:
                    inner_pipeline.append({"$addFields": {"id": "$_id"}})
                    inner_pipeline.append({"$project": {"_id": 0}})

                pipeline.append({
                    "$lookup": {
                        "from": target_collection,
                        "let": {"local_val": local_val_expr},
                        "pipeline": inner_pipeline,
                        "as": alias
                    }
                })

                if not is_list:
                    pipeline.append({
                        "$unwind": {
                            "path": f"${alias}",
                            "preserveNullAndEmptyArrays": True
                        }
                    })

        if projection:
            pipeline.append({"$project": projection})

        results = await self.document_class.get_pymongo_collection().aggregate(pipeline).to_list(length=1)
        
        if results:
            doc = results[0]
            if "_id" in doc:
                doc["id"] = str(doc.pop("_id"))
            doc = self._sanitize(doc)
            return doc
            
        return None

    async def create(self, data: Dict[str, Any]) -> T:
        obj = self.document_class(**data)
        await obj.insert()
        return obj

    async def update(self, filter_query: Dict[str, Any], data: Dict[str, Any]) -> Optional[T]:
        filter_query = self._prepare_query(filter_query)
        item = await self.document_class.find_one(filter_query)
        if item:
            await item.set(data)
            return item
        return None

    async def delete(self, filter_query: Dict[str, Any], soft: bool = True) -> bool:
        filter_query = self._prepare_query(filter_query)
        item = await self.document_class.find_one(filter_query)
        if not item:
            return False
            
        if soft:
            await item.set({"is_deleted": True, "deleted_at": datetime.now(timezone.utc)})
        else:
            await item.delete()
        return True

    async def count(self, query: Dict[str, Any], populate_fields: Optional[Dict[str, Any]] = None) -> int:
        full_query = self._prepare_query(query)
        
        # Check if we need aggregation for joined fields
        has_joined = any("." in k and not (k.startswith("$") or k.endswith(".id") or k.endswith(".$id")) for k in full_query.keys())
        
        if not has_joined:
            return await self.document_class.find(full_query).count()
            
        # Use aggregation to get count for joined filters
        pipeline = []
        local_query = {}
        joined_query = {}
        
        for k, v in full_query.items():
            if "." in k and not (k.startswith("$") or k.endswith(".id") or k.endswith(".$id")):
                joined_query[k] = v
            else:
                local_query[k] = v
                
        pipeline.append({"$match": local_query})
        
        # We need to perform lookups even for counting if we filter by joined fields
        if populate_fields:
            for local_field, config in populate_fields.items():
                target_collection = config
                alias = local_field
                is_link = False
                is_string_id = False
                is_list = False
                
                if isinstance(config, dict):
                    target_collection = config.get("collection")
                    alias = config.get("field", local_field)
                    is_link = config.get("is_link", False)
                    is_string_id = config.get("is_string_id", False)
                    is_list = config.get("is_list", False)
                
                # Check if this populated field is actually needed for joined_query
                # If no field in joined_query starts with 'alias.', we can skip this lookup for speed (optional optimization)
                
                if is_list:
                    if is_link:
                       local_val_expr = {"$map": {"input": {"$ifNull": [f"${local_field}", []]}, "as": "item", "in": {"$ifNull": ["$$item.id", {"$ifNull": ["$$item.$id", "$$item"]}]}}}
                    else:
                        local_val_expr = {"$ifNull": [f"${local_field}", []]}
                else:
                    if is_link:
                        local_val_expr = {"$ifNull": [f"${local_field}.id", {"$ifNull": [f"${local_field}.$id", f"${local_field}"]}]}
                    else:
                        local_val_expr = f"${local_field}"
                    
                inner_match = {}
                if is_string_id and is_list:
                    inner_match = {"$expr": {"$in": [{"$toString": "$_id"}, "$$local_val"]}}
                elif is_string_id:
                    inner_match = {"$expr": {"$eq": ["$_id", {"$toObjectId": "$$local_val"}]}}
                elif is_list:
                    inner_match = {"$expr": {"$in": ["$_id", "$$local_val"]}}
                else:
                    inner_match = {"$expr": {"$eq": ["$_id", "$$local_val"]}}
                    
                pipeline.append({
                    "$lookup": {
                        "from": target_collection,
                        "let": {"local_val": local_val_expr},
                        "pipeline": [{"$match": inner_match}],
                        "as": alias
                    }
                })

                if not is_list:
                    pipeline.append({
                        "$unwind": {
                            "path": f"${alias}",
                            "preserveNullAndEmptyArrays": True
                        }
                    })

        if joined_query:
            pipeline.append({"$match": joined_query})
            
        pipeline.append({"$count": "total"})
        
        results = await self.document_class.get_pymongo_collection().aggregate(pipeline).to_list(length=1)
        return results[0]["total"] if results else 0
