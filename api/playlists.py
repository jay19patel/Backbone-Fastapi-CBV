from fastapi import APIRouter
from backbone import GenericCrud, AllowAny
from schemas.playlists import Playlist

playlist_crud = GenericCrud(
    schema=Playlist,
    prefix="/playlists",
    tags=["Playlists"],
    search_fields=["name", "description"],
    list_fields=["id", "name", "slug", "owner", "is_public"],
    fetch_links=True,
    permission_classes=[AllowAny]
)

router = playlist_crud.router

# Custom routes for adding / removing blogs
@router.post("/{slug}/blogs/", tags=["Playlists"])
async def add_blog_to_playlist(slug: str):
    return {"message": f"Add blog to playlist {slug}"}

@router.delete("/{slug}/blogs/{blog_id}/", tags=["Playlists"])
async def remove_blog_from_playlist(slug: str, blog_id: str):
    return {"message": f"Remove blog {blog_id} from playlist {slug}"}
