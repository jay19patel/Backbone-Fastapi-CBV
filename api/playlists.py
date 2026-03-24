from fastapi import APIRouter, Depends
from backbone import GenericCrud, AllowAny, IsAuthenticated
from schemas.playlists import Playlist
from backbone.core.dependencies import get_optional_user

class PlaylistViewSet(GenericCrud):
    # Override query parameters or custom query behaviors here if needed
    pass

playlist_crud = PlaylistViewSet(
    schema=Playlist,
    prefix="/playlists",
    tags=["Playlists"],
    search_fields=["name", "description"],
    list_fields=["id", "owner", "name", "slug", "description", "thumbnail", "is_public", "created_at"],
    fetch_links=True,
    permission_classes=[AllowAny],
    lookup_field="slug",
    filter_fields=["slug", "owner.$id", "is_public"]
)

router = APIRouter()
router.include_router(playlist_crud.router)
