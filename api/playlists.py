from fastapi import APIRouter, Depends, HTTPException, status, Request
from backbone import GenericCrud, AllowAny, BeanieRepository
from backbone.core.dependencies import get_current_user, get_optional_user
from backbone.core.models import User
from schemas.playlists import Playlist
from schemas.blogs import Blog
from typing import List, Optional
from beanie import PydanticObjectId
from backbone.generic.views import GenericSubResource

class PlaylistRepository(BeanieRepository[Playlist]):
    async def get_all(self, *args, **kwargs):
        results = await super().get_all(*args, **kwargs)
        for res in results:
            blogs = res.get("blogs", [])
            res["blog_count"] = len(blogs) if isinstance(blogs, list) else 0
            res["total_views"] = sum(b.get("views", 0) for b in blogs if isinstance(b, dict))
            res["total_likes"] = sum(b.get("likes", 0) for b in blogs if isinstance(b, dict))
        return results

    async def get_one(self, *args, **kwargs):
        res = await super().get_one(*args, **kwargs)
        if res:
            blogs = res.get("blogs", [])
            res["blog_count"] = len(blogs) if isinstance(blogs, list) else 0
            res["total_views"] = sum(b.get("views", 0) for b in blogs if isinstance(b, dict))
            res["total_likes"] = sum(b.get("likes", 0) for b in blogs if isinstance(b, dict))
        return res

# Repository Instance
playlist_repo = PlaylistRepository()

playlist_crud = GenericCrud(
    schema=Playlist,
    repository=playlist_repo,
    prefix="/playlists",
    tags=["Playlists"],
    search_fields=["name", "description"],
    list_fields=["id", "name", "slug", "owner", "thumbnail", "is_public", "blogs", "blog_count", "total_views", "total_likes"],
    fetch_links=True,
    permission_classes=[AllowAny],
    filter_fields=["owner.$id", "is_public", "slug", "blogs.$id"],
    lookup_field="slug"
)

# Create a new router to control route order
router = APIRouter()

def get_repo(model, request: Request = None) -> BeanieRepository:
    from backbone import BackboneConfig
    db = None
    if request and hasattr(request.app.state, "backbone_config"):
        db = request.app.state.backbone_config.database
    else:
        try:
            db = BackboneConfig.get_instance().database
        except:
            pass
            
    repo = BeanieRepository(db)
    repo.initialize(model)
    return repo

playlist_blogs = GenericSubResource(
    schema=Playlist,
    repository=playlist_repo,
    array_field="blogs",
    target_id_param="blog_id",
    prefix="/playlists",
    tags=["Playlists"],
    lookup_field="slug"
)
router.include_router(playlist_blogs.router)

# Include generic routing AFTER custom specific routes
router.include_router(playlist_crud.router)

class BlogRepository(BeanieRepository[Blog]):
    pass
