from typing import List, Optional, Any
from pydantic import Field, field_serializer
from beanie import Link
from pymongo import IndexModel, ASCENDING, DESCENDING
from backbone.core.models import AuditDocument, User
from .blogs import Blog

class Playlist(AuditDocument):
    owner: Link[User]
    name: str = Field(max_length=200)
    slug: str = Field(max_length=255)
    description: Optional[str] = None
    thumbnail: Optional[Link["Attachment"]] = None
    
    blogs: List[Link[Blog]] = Field(default_factory=list)
    
    is_public: bool = True

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
        name = "playlists"
        indexes = [
            IndexModel([("slug", ASCENDING)], unique=True),
            IndexModel([("owner.id", ASCENDING)], unique=False),
            IndexModel([("created_at", DESCENDING)], unique=False)
        ]

# Resolve forward references
from backbone.core.models import Attachment
Playlist.model_rebuild()
