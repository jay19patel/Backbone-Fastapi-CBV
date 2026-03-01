from backbone import EventDocument, logger
from backbone.core.models import AuditDocument
from pymongo import IndexModel, ASCENDING
from typing import List, Optional, Dict, Any
from beanie import Insert, Replace, Save, Delete, Update, before_event, after_event, Link
from backbone.core.models import User

class BlogCategory(AuditDocument):
    name: str
    slug: str
    
    class Settings:
        name = "blog_categories"
        return_link_data = ["id", "name", "slug"]
        indexes = [
            IndexModel([("name", ASCENDING)], unique=True),
            IndexModel([("slug", ASCENDING)], unique=True)
        ]

class BlogSchema(AuditDocument):
    title: str
    content: str
    
    # Use Beanie Link for automatic relationship management
    # When fetch_links=True, these will be populated with the actual documents
    author: Link[User]
    categories: List[Link[BlogCategory]] = [] 
    
    tags: List[str] = []
    
    class Settings:
        name = "blogs"
        indexes = [
            IndexModel([("author.id", ASCENDING)], unique=False), # Beanie Links store as DBRef or object with id
            IndexModel([("categories.id", ASCENDING)], unique=False)
        ]