"""
blogging/schemas/playlist
~~~~~~~~~~~~~~~~~~~~~~~~~

Defines the Playlist Beanie Document for compiling curated sets of blogs.
"""

from __future__ import annotations

from beanie import Link
from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from backbone.core.fields import Name, Owner, Slug, Text, Thumbnail
from backbone.core.models import Attachment, BackboneDocument  # noqa: F401
from blogging.schemas.blog import Blog


class Playlist(BackboneDocument):
    """A curated collection of blog posts grouped together by a user."""

    owner: Owner = Field(description="The user who created the playlist")
    name: Name = Field(description="Name of the playlist")
    slug: Slug(depend="name") = Field(
        default=None, description="URL-friendly identifier for the playlist"
    )
    description: Text = Field(default=None, description="Description of the playlist")
    thumbnail: Thumbnail = Field(default=None, description="Cover image for the playlist")
    blogs: list[Link[Blog]] = Field(
        default_factory=list, description="List of blogs curated in this playlist"
    )
    is_public: bool = Field(default=True, description="Whether this playlist is public or not")

    class Settings:
        name = "playlists"
        return_link_data = ["id", "name", "slug", "thumbnail", "owner"]
        indexes = [
            IndexModel(
                [("slug", ASCENDING)],
                unique=True,
                partialFilterExpression={"is_deleted": {"$eq": False}},
            ),
            IndexModel([("owner.$id", ASCENDING)], unique=False),
            IndexModel([("created_at", DESCENDING)], unique=False),
        ]
