from typing import List, Optional, Any
from beanie import Link
from pymongo import IndexModel, ASCENDING, DESCENDING
from backbone.core.models import BackboneDocument, User, Attachment
from pydantic import Field
from pydantic import Field
from backbone.core.fields import Name, Slug, Text, Thumbnail, Owner, Bool, Connect
from .blogs import Blog

class Playlist(BackboneDocument):
    owner: Owner = Field(description="The user who created and owns this playlist")
    name: Name = Field(description="The display name of the playlist")
    slug: Slug(depend="name") = Field(default=None, description="URL-friendly identifier for the playlist")
    description: Text = Field(description="A detailed description of the playlist's contents")
    thumbnail: Thumbnail = Field(default=None, description="Cover image for the playlist")
    
    blogs: List[Connect(Blog, label="Blog")] = Field(default_factory=list, description="List of connected blogs included in this playlist")
    is_public: Bool = Field(default=True, description="Indicates if this playlist is visible to the public")

    class Settings:
        name = "playlists"
        indexes = [
            IndexModel([("slug", ASCENDING)], unique=True),
            IndexModel([("owner.id", ASCENDING)], unique=False),
            IndexModel([("created_at", DESCENDING)], unique=False)
        ]

# Resolve forward references
Playlist.model_rebuild()
