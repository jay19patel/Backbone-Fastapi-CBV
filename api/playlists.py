from fastapi import APIRouter
from backbone.generic.views import GenericCrudView
from backbone.core.permissions import AllowAny
from schemas.playlists import Playlist

class PlaylistView(GenericCrudView):
    schema = Playlist
    search_fields = ["name", "description"]
    list_fields = ["id", "owner", "name", "slug", "description", "thumbnail", "is_public", "created_at"]
    fetch_links = True
    permission_classes = [AllowAny]
    lookup_field = "slug"
    filter_fields = ["slug", "owner.$id", "is_public"]

router = APIRouter()
router.include_router(PlaylistView.as_router("/playlists", tags=["Playlists"]))
