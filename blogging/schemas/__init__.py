"""
blogging/schemas
~~~~~~~~~~~~~~~~

Export and initialization of all Blogging database schemas.
Forces model rebuilding to resolve circular dependencies/forward references at load time.
"""

from blogging.schemas.blog import (
    Blog,
    BlogCategory,
    BlogLike,
    BlogPromptState,
    BlogSection,
    BlogSectionBase,
    BlogSectionBullets,
    BlogSectionCode,
    BlogSectionFlowchart,
    BlogSectionFlowchartStep,
    BlogSectionImage,
    BlogSectionLinkItem,
    BlogSectionLinks,
    BlogSectionNote,
    BlogSectionTable,
    BlogSectionText,
    BlogSectionYoutube,
    BlogView,
)
from blogging.schemas.playlist import Playlist

# Force model rebuilding for Beanie Link resolution and Pydantic serialization
BlogCategory.model_rebuild()
Blog.model_rebuild()
BlogLike.model_rebuild()
BlogView.model_rebuild()
Playlist.model_rebuild()

__all__ = [
    "BlogCategory",
    "Blog",
    "BlogLike",
    "BlogView",
    "BlogSectionBase",
    "BlogSectionText",
    "BlogSectionBullets",
    "BlogSectionTable",
    "BlogSectionNote",
    "BlogSectionLinkItem",
    "BlogSectionLinks",
    "BlogSectionImage",
    "BlogSectionCode",
    "BlogSectionYoutube",
    "BlogSectionFlowchartStep",
    "BlogSectionFlowchart",
    "BlogSection",
    "BlogPromptState",
    "Playlist",
]
