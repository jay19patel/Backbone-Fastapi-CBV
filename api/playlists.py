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

# --- Custom Routes FIRST (to avoid being shadowed by generic slug route) ---

@router.get("/playlists/public/", tags=["Playlists"])
async def get_public_playlists(request: Request):
    """Get all public playlists."""
    repo = get_repo(Playlist, request)
    # Filter for public playlists that are not deleted
    query = {"is_public": True, "is_deleted": False}
    results = await repo.get_all(
        query, 
        populate_fields=repo.detect_populate_fields(Playlist)
    )
    return {"results": results, "total": len(results)}

@router.get("/playlists/popular/", tags=["Playlists"])
async def get_popular_playlists(request: Request):
    """Get popular (public) playlists."""
    repo = get_repo(Playlist, request)
    # For now, popular = public playlists sorted by newest
    query = {"is_public": True, "is_deleted": False}
    results = await repo.get_all(
        query, 
        populate_fields=repo.detect_populate_fields(Playlist),
        limit=6,
        sort=[("views", -1)]
    )
    return {"results": results, "total": len(results)}

# Include generic routes AFTER custom specific routes
router.include_router(playlist_crud.router)


class PlaylistRepository(BeanieRepository[Playlist]):
    pass

class BlogRepository(BeanieRepository[Blog]):
    pass



# --- Custom Routes ---


# --- Custom POST/DELETE Routes ---

@router.post("/playlists/{playlist_id_or_slug}/blogs/", tags=["Playlists"])
async def add_blog_to_playlist(
    playlist_id_or_slug: str,
    blog_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Add a blog to a playlist."""
    playlist_repo = get_repo(Playlist)
    playlist = await playlist_repo.get_one(
        {"$or": [{"slug": playlist_id_or_slug}, {"id": playlist_id_or_slug}], "is_deleted": False}
    )
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
        
    owner_id = playlist["owner"]["id"] if isinstance(playlist.get("owner"), dict) else str(playlist.get("owner", ""))
    if owner_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    blog_repo = get_repo(Blog)
    blog_id = blog_data.get("blog_id")
    blog = await blog_repo.get_one({"id": blog_id, "is_deleted": False})
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")
        
    # Check if blog already exists in playlist blogs array via pure DB approach
    playlist_id = playlist["id"]
    from beanie import PydanticObjectId
    from pymongo import UpdateOne
    
    # We securely use the motor collection to push
    # For robust repositry isolation, we add a push abstraction conceptually,
    # or just use native update pipeline in Beanie: 
    await playlist_repo.update({"_id": playlist_id}, {
        "$addToSet": {"blogs": PydanticObjectId(blog_id)}
    })
    
    return {"status": "success", "message": "Blog added"}

@router.delete("/playlists/{playlist_id_or_slug}/blogs/{blog_id}/", tags=["Playlists"])
async def remove_blog_from_playlist(
    playlist_id_or_slug: str,
    blog_id: str,
    current_user: User = Depends(get_current_user)
):
    """Remove a blog from a playlist."""
    playlist_repo = get_repo(Playlist)
    playlist = await playlist_repo.get_one(
        {"$or": [{"slug": playlist_id_or_slug}, {"id": playlist_id_or_slug}], "is_deleted": False}
    )
    
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
        
    owner_id = playlist["owner"]["id"] if isinstance(playlist.get("owner"), dict) else str(playlist.get("owner", ""))
    if owner_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")
        
    playlist_id = playlist["id"]
    from beanie import PydanticObjectId
    
    await playlist_repo.update({"_id": playlist_id}, {
        "$pull": {"blogs": PydanticObjectId(blog_id)}
    })

    return {"status": "success", "message": "Blog removed"}
