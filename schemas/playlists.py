from typing import List, Optional, Any
from pydantic import Field, field_serializer
from beanie import Link, before_event, Insert
from pymongo import IndexModel, ASCENDING, DESCENDING
from backbone.core.models import AuditDocument, User, slugify
from .blogs import Blog
import uuid

class Playlist(AuditDocument):
    owner: Link[User]
    name: str = Field(max_length=200)
    slug: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    thumbnail: Optional[Link["Attachment"]] = None
    
    blogs: List[Link[Blog]] = Field(default_factory=list)
    
    is_public: bool = True

    @before_event(Insert)
    async def generate_slug(self):
        if not self.slug or self.slug == "string": # "string" is default from some UI/Tools
             base_slug = slugify(self.name)
             entropy = str(uuid.uuid4())[:8]
             self.slug = f"{base_slug}-{entropy}" if base_slug else entropy

    @field_serializer('thumbnail')
    def serialize_thumbnail(self, thumbnail: Any):
        if not thumbnail:
            return None
        from backbone.core.url_utils import get_media_url
        if hasattr(thumbnail, "to_ref"): return None
        path = thumbnail.get("file_path") if isinstance(thumbnail, dict) else getattr(thumbnail, "file_path", str(thumbnail))
        if path and path.startswith("/media/"):
            return get_media_url(path)
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
