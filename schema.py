from typing import List
from backbone.schemas import AuditSchema

class BlogSchema(AuditSchema):
    title: str
    content: str
    author_id: str
    tags: List[str] = []
    
    # Metadata for MongoDB collection management
    class Meta:
        collection_name = "blogs"
        indexes = [
            {"fields": ["title"], "unique": False},
            {"fields": ["author_id"], "unique": False}
        ]