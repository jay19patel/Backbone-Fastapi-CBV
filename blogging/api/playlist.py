"""
blogging/api/playlist
~~~~~~~~~~~~~~~~~~~~~

Defines CBVs for Playlist operations and public listing.
Includes customized lifecycles to calculate composite stats (total views, likes, count) dynamically.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from backbone.core.permissions import AllowAny
from backbone.generic.views import GenericCrudView
from blogging.schemas.playlist import Playlist


class PlaylistView(GenericCrudView):
    """View endpoints for managing collections of blog posts (Playlists)."""

    schema = Playlist
    search_fields = ["name", "description"]
    list_fields = [
        "id",
        "owner",
        "name",
        "slug",
        "description",
        "thumbnail",
        "is_public",
        "created_at",
        "blogs",
    ]
    filter_fields = ["slug", "owner.$id", "is_public"]
    fetch_links = True
    permission_classes = [AllowAny]
    lookup_field = "slug"

    async def _enhance_playlist_stats(self, instance: dict[str, Any]) -> dict[str, Any]:
        """Aggregate total views and likes across all blogs nested in this playlist."""
        total_views = 0
        total_likes = 0
        blogs = instance.get("blogs")

        if isinstance(blogs, list):
            for blog in blogs:
                if isinstance(blog, dict):
                    total_views += int(blog.get("views", 0) or 0)
                    total_likes += int(blog.get("likes", 0) or 0)
                elif hasattr(blog, "views"):
                    total_views += int(getattr(blog, "views", 0) or 0)
                    total_likes += int(getattr(blog, "likes", 0) or 0)
            instance["blog_count"] = len(blogs)
        else:
            instance["blog_count"] = 0

        instance["total_views"] = total_views
        instance["total_likes"] = total_likes

        return instance

    async def after_retrieve(
        self, instance: dict[str, Any], request: Request, user: Any
    ) -> dict[str, Any]:
        """Add aggregated statistics to the individual playlist response."""
        instance = await super().after_retrieve(instance, request, user)
        return await self._enhance_playlist_stats(instance)

    async def after_list(
        self, instances: list[dict[str, Any]], request: Request, user: Any
    ) -> list[dict[str, Any]]:
        """Add stats to listed playlists, removing heavy blogs mapping to keep network payload optimized."""
        instances = await super().after_list(instances, request, user)
        enhanced_instances = []

        for inst in instances:
            enhanced = await self._enhance_playlist_stats(inst)
            # Drop nested array in list response for payload optimization
            if "blogs" in enhanced:
                del enhanced["blogs"]
            enhanced_instances.append(enhanced)

        return enhanced_instances


router = APIRouter()
router.include_router(PlaylistView.as_router("/playlists", tags=["Playlists"]))
