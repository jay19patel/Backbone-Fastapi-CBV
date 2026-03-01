from typing import List, Optional
from pydantic import Field
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
