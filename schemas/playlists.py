from typing import Optional, List
from beanie import Link
from pydantic import Field
from pymongo import IndexModel, ASCENDING, DESCENDING
from backbone.core.models import BackboneDocument, Attachment, User
from backbone.core.fields import Name, Slug, Text, Thumbnail, Connect, Owner
from schemas.blogs import Blog

class Playlist(BackboneDocument):
    owner: Owner = Field(description="The user who created the playlist")
    name: Name = Field(description="Name of the playlist")
    slug: Slug(depend="name") = Field(default=None, description="URL-friendly identifier for the playlist")
    description: Text = Field(default=None, description="Description of the playlist")
    thumbnail: Thumbnail = Field(default=None, description="Cover image for the playlist")
    blogs: List[Connect(Blog)] = Field(default_factory=list, description="List of blogs in this playlist")
    is_public: bool = Field(default=True, description="Whether this playlist is public or not")

    class Settings:
        name = "playlists"
        return_link_data = ["id", "name", "slug", "thumbnail", "owner"]
        indexes = [
            IndexModel([("slug", ASCENDING)], unique=True),
            IndexModel([("owner.id", ASCENDING)], unique=False),
            IndexModel([("created_at", DESCENDING)], unique=False)
        ]

# Resolve forward references
Playlist.model_rebuild()
