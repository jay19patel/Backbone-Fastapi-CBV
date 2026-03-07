from datetime import datetime
from typing import List, Optional, Dict, Any
from beanie import Link
from pydantic import Field, field_serializer
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

    # Store embeddings in any flexible format
    embedding: Optional[Any] = Field(default=None, description="Embeddings (Any format)")

    @field_serializer('thumbnail')
    def serialize_thumbnail(self, thumbnail: Any):
        if not thumbnail:
            return None
        from backbone.core.settings import settings
        if hasattr(thumbnail, "to_ref"): return None
        path = thumbnail.get("file_path") if isinstance(thumbnail, dict) else getattr(thumbnail, "file_path", str(thumbnail))
        if path and path.startswith("/media/"):
            return f"{settings.BACKEND_URL}{path}"
        return path

    class Settings:
        name = "blogs"
        return_link_data = ["id", "title", "slug", "thumbnail", "author", "category", "views", "likes"]
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
