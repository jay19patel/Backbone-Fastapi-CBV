from fastapi import APIRouter, Depends, HTTPException, status, Request
from backbone import GenericCrud, AllowAny, BeanieRepository
from backbone.core.dependencies import get_current_user, get_optional_user
from backbone.core.models import User
from schemas.playlists import Playlist
from schemas.blogs import Blog
from typing import List, Optional
from beanie import PydanticObjectId

playlist_crud = GenericCrud(
    schema=Playlist,
    prefix="/playlists",
    tags=["Playlists"],
    search_fields=["name", "description"],
    list_fields=["id", "name", "slug", "owner", "is_public"],
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

from backbone.generic.views import GenericSubResource

playlist_blogs = GenericSubResource(
    schema=Playlist,
    array_field="blogs",
    target_id_param="blog_id",
    prefix="/playlists",
    tags=["Playlists"],
    lookup_field="slug"
)
router.include_router(playlist_blogs.router)

# Include generic routing AFTER custom specific routes
router.include_router(playlist_crud.router)

class PlaylistRepository(BeanieRepository[Playlist]):
    pass

class BlogRepository(BeanieRepository[Blog]):
    pass
