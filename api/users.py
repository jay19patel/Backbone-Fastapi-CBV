from fastapi import APIRouter, HTTPException
from backbone import GenericCrud, AllowAny, BeanieRepository
import urllib.parse
from beanie import PydanticObjectId
from backbone.core.models import User
from backbone.core.config import BackboneConfig
from schemas.blogs import Blog, BlogView, BlogLike
from typing import List, Optional

# --- Custom Repositories ---
class UserRepository(BeanieRepository[User]):
    pass

class BlogRepository(BeanieRepository[Blog]):
    pass

class BlogViewRepository(BeanieRepository[BlogView]):
    pass

class BlogLikeRepository(BeanieRepository[BlogLike]):
    pass

user_crud = GenericCrud(
    schema=User,
    prefix="/user",
    tags=["Users"],
    search_fields=["full_name", "email", "headline", "bio"],
    list_fields=["id", "full_name", "email", "headline", "profile_image"],
    permission_classes=[AllowAny]
)

router = APIRouter()

# --- Custom Routes FIRST ---

@router.get("/user/top-authors/", tags=["Users"])
async def get_top_authors():
    user_repo = get_repo(User)
    users = await user_repo.get_all({"is_active": True}, limit=5)
    return {"results": users}

# Include generic routes AFTER
router.include_router(user_crud.router)


def get_repo(model) -> BeanieRepository:
    repo = BeanieRepository(BackboneConfig.get_instance().database)
    repo.initialize(model)
    return repo

@router.get("/user/profile/{email}/", tags=["Users"])
async def get_user_profile(email: str):
    decoded_email = urllib.parse.unquote(email)
    
    user_repo = get_repo(User)
    user = await user_repo.get_one(
        {"email": decoded_email},
        populate_fields=BeanieRepository.detect_populate_fields(User)
    )
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_id = user.get("id") or user.get("_id")
    
    blog_repo = get_repo(Blog)
    blog_view_repo = get_repo(BlogView)
    blog_like_repo = get_repo(BlogLike)
    
    # 1. Blog Count
    blog_count = await blog_repo.count({"author.$id": PydanticObjectId(user_id), "is_deleted": False})
    
    # 2. Total Views & Likes 
    blogs_stats = await blog_repo.get_all({"author.$id": PydanticObjectId(user_id), "is_deleted": False}, limit=1000)
    blog_ids = [b["id"] for b in blogs_stats]
    
    total_views = await blog_view_repo.count({"blog.$id": {"$in": blog_ids}})
    total_likes = await blog_like_repo.count({"blog.$id": {"$in": blog_ids}})
    
    return {
        **user,
        "blog_count": blog_count,
        "total_views": total_views,
        "total_likes": total_likes
    }

