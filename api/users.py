from fastapi import APIRouter, HTTPException
from backbone import GenericCrudView, AllowAny, BeanieRepository
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



class UserView(GenericCrudView):
    schema = User
    search_fields = ["full_name", "email", "headline", "bio"]
    list_fields = ["id", "full_name", "email", "headline", "profile_image"]
    fetch_links = True
    permission_classes = [AllowAny]


router = APIRouter()

# --- Custom Routes FIRST ---

@router.get("/user/top-authors/", tags=["Users"])
async def get_top_authors():
    from beanie import PydanticObjectId
    from backbone.core.models import Attachment
    
    user_repo = get_repo(User)
    # Get top 5 active users
    users, _ = await user_repo.get_all({"is_active": True}, limit=5)
    
    blog_repo = get_repo(Blog)
    blog_view_repo = get_repo(BlogView)
    blog_like_repo = get_repo(BlogLike)

    enhanced_users = []
    for user in users:
        user_id = user.get("id") or user.get("_id")
        obj_id = PydanticObjectId(user_id) if isinstance(user_id, str) else user_id
        
        # 1. Blog Count
        blog_count = await blog_repo.count({"author.$id": obj_id, "is_deleted": False})
        
        # 2. Total Views & Likes 
        blogs, _ = await blog_repo.get_all({"author.$id": obj_id, "is_deleted": False}, limit=1000, projection={"id": 1})
        blog_ids = [PydanticObjectId(b["id"]) for b in blogs]
        
        total_views = 0
        total_likes = 0
        if blog_ids:
            total_views = await blog_view_repo.count({"blog.$id": {"$in": blog_ids}})
            total_likes = await blog_like_repo.count({"blog.$id": {"$in": blog_ids}})

        # Process stringification and cleanup
        user["id"] = str(user_id)
        if "_id" in user: user["_id"] = str(user["_id"])
        
        # Stats
        user["blog_count"] = blog_count
        user["total_views"] = total_views
        user["total_likes"] = total_likes
            
        profile_image = user.get("profile_image")
        if profile_image:
            image_id = None
            if isinstance(profile_image, dict) and "$id" in profile_image:
                image_id = str(profile_image["$id"])
            elif isinstance(profile_image, dict) and "id" in profile_image:
                image_id = str(profile_image["id"])
            else:
                image_id = str(profile_image)
                
            if image_id:
                try:
                    attachment = await Attachment.get(PydanticObjectId(image_id))
                    if attachment:
                        user["profile_image"] = attachment.model_dump(by_alias=True)
                        if "id" in user["profile_image"] and isinstance(user["profile_image"]["id"], PydanticObjectId):
                            user["profile_image"]["id"] = str(user["profile_image"]["id"])
                        if "_id" in user["profile_image"]:
                            user["profile_image"]["_id"] = str(user["profile_image"]["_id"])
                except Exception:
                    pass
        
        enhanced_users.append(user)

    return {"results": enhanced_users}

@router.get("/user/all/", tags=["Users"])
async def get_all_users_with_stats(
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 10
):
    from beanie import PydanticObjectId
    from backbone.core.models import Attachment
    
    user_repo = get_repo(User)
    
    # 1. Build Query
    query = {"is_active": True}
    if search:
        query["$or"] = [
            {"full_name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
            {"headline": {"$regex": search, "$options": "i"}}
        ]
    
    # 2. Get Users
    users, total = await user_repo.get_all(query, skip=skip, limit=limit)
    
    blog_repo = get_repo(Blog)
    blog_view_repo = get_repo(BlogView)
    blog_like_repo = get_repo(BlogLike)

    enhanced_users = []
    for user in users:
        user_id = user.get("id") or user.get("_id")
        obj_id = PydanticObjectId(user_id) if isinstance(user_id, str) else user_id
        
        # Blog Count
        blog_count = await blog_repo.count({"author.$id": obj_id, "is_deleted": False})
        
        # Views & Likes 
        blogs, _ = await blog_repo.get_all({"author.$id": obj_id, "is_deleted": False}, limit=1000, projection={"id": 1})
        blog_ids = [PydanticObjectId(b["id"]) for b in blogs]
        
        total_views = 0
        total_likes = 0
        if blog_ids:
            total_views = await blog_view_repo.count({"blog.$id": {"$in": blog_ids}})
            total_likes = await blog_like_repo.count({"blog.$id": {"$in": blog_ids}})

        user["id"] = str(user_id)
        if "_id" in user: user["_id"] = str(user["_id"])
        user["blog_count"] = blog_count
        user["total_views"] = total_views
        user["total_likes"] = total_likes
            
        profile_image = user.get("profile_image")
        if profile_image:
            image_id = None
            if isinstance(profile_image, dict) and "$id" in profile_image: image_id = str(profile_image["$id"])
            elif isinstance(profile_image, dict) and "id" in profile_image: image_id = str(profile_image["id"])
            else: image_id = str(profile_image)
            if image_id:
                try:
                    attachment = await Attachment.get(PydanticObjectId(image_id))
                    if attachment:
                        user["profile_image"] = attachment.model_dump(by_alias=True)
                        if "id" in user["profile_image"] and isinstance(user["profile_image"]["id"], PydanticObjectId):
                            user["profile_image"]["id"] = str(user["profile_image"]["id"])
                        if "_id" in user["profile_image"]:
                            user["profile_image"]["_id"] = str(user["profile_image"]["_id"])
                except Exception: pass
        
        enhanced_users.append(user)

    return {"results": enhanced_users, "total": total}

# Include generic routes AFTER
router.include_router(UserView.as_router("/users", tags=["Users"]))


def get_repo(model) -> BeanieRepository:
    repo = BeanieRepository(BackboneConfig.get_instance().database)
    repo.initialize(model)
    return repo

from backbone.schemas import UserOut

class UserProfileOut(UserOut):
    blog_count: int = 0
    total_views: int = 0
    total_likes: int = 0

@router.get("/user/profile/{email}/", response_model=UserProfileOut, tags=["Users"])
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
    blogs_stats, _ = await blog_repo.get_all({"author.$id": PydanticObjectId(user_id), "is_deleted": False}, limit=1000)
    blog_ids = [b["id"] for b in blogs_stats]
    
    total_views = await blog_view_repo.count({"blog.$id": {"$in": blog_ids}})
    total_likes = await blog_like_repo.count({"blog.$id": {"$in": blog_ids}})
    
    # Ensure user IDs are stringified properly to prevent serialization errors
    user_id = str(user_id) if hasattr(user_id, 'binary') or isinstance(user_id, PydanticObjectId) else user_id
    if "id" in user:
        user["id"] = user_id
    if "_id" in user:
        user["_id"] = str(user["_id"])
        
    # Serialize profile image if present and contains nested ObjectId
    if "profile_image" in user and isinstance(user["profile_image"], dict):
        if "id" in user["profile_image"]:
            user["profile_image"]["id"] = str(user["profile_image"]["id"])
        if "_id" in user["profile_image"]:
            user["profile_image"]["_id"] = str(user["profile_image"]["_id"])

    return {
        **user,
        "blog_count": blog_count,
        "total_views": total_views,
        "total_likes": total_likes
    }

