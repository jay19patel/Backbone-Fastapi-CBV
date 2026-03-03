from datetime import datetime
from typing import List, Optional, Dict, Any
from beanie import Link
from pydantic import Field
from pymongo import IndexModel, ASCENDING, DESCENDING
from backbone.core.models import AuditDocument, User


class BlogCategory(AuditDocument):
    name: str = Field(max_length=150)
    slug: str
    
    class Settings:
        name = "blog_categories"
        return_link_data = ["id", "name", "slug"]
        indexes = [
            IndexModel([("name", ASCENDING)], unique=True),
            IndexModel([("slug", ASCENDING)], unique=True)
        ]


class Blog(AuditDocument):
    title: str = Field(max_length=200)
    subtitle: Optional[str] = Field(default=None, max_length=300)
    slug: str = Field(max_length=255)

    excerpt: Optional[str] = None
    introduction: Optional[str] = None
    sections: List[Dict[str, Any]] = Field(default_factory=list)
    conclusion: Optional[str] = None

    author: Link[User]
    category: Optional[Link[BlogCategory]] = None

    thumbnail: Optional[Link["Attachment"]] = None
    
    isPublished: bool = False
    publishedDate: Optional[datetime] = None

    # Analytics
    views: int = 0
    likes: int = 0

    # Store embeddings as vector/list
    embedding: Optional[List[float]] = Field(default=None, description="Mistral embeddings (1024 dim)")

    class Settings:
        name = "blogs"
        return_link_data = ["id", "title", "slug", "thumbnail", "author", "category"]
        indexes = [
            IndexModel([("slug", ASCENDING)], unique=False),
            IndexModel([("author.id", ASCENDING)], unique=False),
            IndexModel([("category.id", ASCENDING)], unique=False),
            IndexModel([("created_at", DESCENDING)], unique=False)
        ]


class BlogLike(AuditDocument):
    user: Link[User]
    blog: Link[Blog]

    class Settings:
        name = "blog_likes"
        indexes = [
            IndexModel([("user.id", ASCENDING), ("blog.id", ASCENDING)], unique=True),
            IndexModel([("created_at", DESCENDING)], unique=False)
        ]


class BlogView(AuditDocument):
    user: Optional[Link[User]] = None
    blog: Link[Blog]
    ip_address: Optional[str] = None

    class Settings:
        name = "blog_views"
        indexes = [
            IndexModel([("created_at", DESCENDING)], unique=False)
        ]

# Resolve forward references
from backbone.core.models import Attachment
Blog.model_rebuild()
BlogLike.model_rebuild()
BlogView.model_rebuild()
