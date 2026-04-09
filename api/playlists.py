from fastapi import APIRouter, Request
from typing import Any
from backbone.generic.views import GenericCrudView
from backbone.core.permissions import AllowAny
from schemas.playlists import Playlist

class PlaylistView(GenericCrudView):
    schema = Playlist
    search_fields = ["name", "description"]
    list_fields = ["id", "owner", "name", "slug", "description", "thumbnail", "is_public", "created_at", "blogs"]
    fetch_links = True
    permission_classes = [AllowAny]
    lookup_field = "slug"
    filter_fields = ["slug", "owner.$id", "is_public"]

    async def _enhance_playlist_stats(self, instance: dict) -> dict:
        total_views = 0
        total_likes = 0
        if "blogs" in instance and isinstance(instance["blogs"], list):
            for blog in instance["blogs"]:
                if isinstance(blog, dict):
                    total_views += int(blog.get("views", 0) or 0)
                    total_likes += int(blog.get("likes", 0) or 0)
                elif hasattr(blog, 'views'):
                    total_views += int(getattr(blog, "views", 0) or 0)
                    total_likes += int(getattr(blog, "likes", 0) or 0)
            instance["blog_count"] = len(instance["blogs"])
        else:
            instance["blog_count"] = 0
            
        instance["total_views"] = total_views
        instance["total_likes"] = total_likes
        
        # Optionally remove the full blogs array from the list view to keep payload light
        # but keep it in retrieve. Actually we will leave it as is or remove it in list.
        return instance

    async def after_retrieve(self, instance: dict, request: Request, user: Any) -> dict:
        instance = await super().after_retrieve(instance, request, user)
        instance = await self._enhance_playlist_stats(instance)
        return instance

    async def after_list(self, instances: list, request: Request, user: Any) -> list:
        instances = await super().after_list(instances, request, user)
        enhanced_instances = []
        for instance in instances:
            enhanced = await self._enhance_playlist_stats(instance)
            # Remove heavy blogs array from list view to optimize payload
            if "blogs" in enhanced:
                del enhanced["blogs"]
            enhanced_instances.append(enhanced)
        return enhanced_instances

router = APIRouter()
router.include_router(PlaylistView.as_router("/playlists", tags=["Playlists"]))
