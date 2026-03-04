from fastapi import APIRouter, HTTPException, Query, Request, Depends
from backbone import GenericCrud, AllowAny, BeanieRepository
from schemas.blogs import Blog, BlogCategory, BlogLike, BlogView
from backbone.core.models import User
from backbone.core.dependencies import get_optional_user, get_current_user
from beanie import PydanticObjectId
from typing import List, Optional
import random

# Router for Blog Categories
blog_category_crud = GenericCrud(
    schema=BlogCategory,
    prefix="/blogs/categories",
    tags=["Blog Categories"],
    search_fields=["name", "slug"],
    permission_classes=[AllowAny]
)

# Router for Blogs
blog_crud = GenericCrud(
    schema=Blog,
    prefix="/blogs",
    tags=["Blogs"],
    search_fields=["title", "subtitle", "excerpt", "introduction"],
    list_fields=["id", "title", "slug", "thumbnail", "author", "category", "created_at", "views", "likes"],
    fetch_links=True,
    permission_classes=[AllowAny],
    lookup_field="slug",
    filter_fields=["slug", "author.$id", "category.name", "category.$id", "featured"]
)

router = APIRouter()

from backbone.generic.views import GenericStats

blog_stats = GenericStats(
    schema=Blog,
    prefix="/blogs/stats",
    tags=["Blogs"],
    stats_config=[
        {"name": "blogs_published", "model": Blog, "type": "count", "filters": {"is_deleted": False, "isPublished": True}},
        {"name": "total_categories", "model": BlogCategory, "type": "count", "filters": {"is_deleted": False}},
        {"name": "total_views", "model": BlogView, "type": "count", "filters": {"is_deleted": False}},
        {"name": "total_likes", "model": BlogLike, "type": "count", "filters": {"is_deleted": False}},
        {"name": "active_users", "model": User, "type": "count", "filters": {"is_deleted": False, "is_active": True}}
    ]
)
router.include_router(blog_category_crud.router)
router.include_router(blog_stats.router)

# Generic Blogs CRUD handles listing, detail, creation, update, deletion
# This includes /blogs/ (GET, POST), /blogs/{slug} (GET, PATCH, DELETE)
router.include_router(blog_crud.router)

class BlogRepository(BeanieRepository[Blog]):
    pass

class BlogCategoryRepository(BeanieRepository[BlogCategory]):
    pass

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


@router.post("/blogs/{blog_id_or_slug}/like/", tags=["Blogs"])
async def like_blog(
    request: Request,
    blog_id_or_slug: str,
    current_user: Optional[User] = Depends(get_optional_user)
):
    """Toggle like for a blog. Supports both ID and Slug."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required to like a blog")

    blog_repo = get_repo(Blog, request)
    blog = await blog_repo.get_one({
        "$or": [{"slug": blog_id_or_slug}, {"id": blog_id_or_slug}],
        "is_deleted": False
    })
    
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")
        
    blog_id = blog.get("id")
    from beanie import PydanticObjectId
    from bson import ObjectId
    
    # Check if user already liked this blog
    like_repo = get_repo(BlogLike, request)
    existing_like = await like_repo.get_one({
        "user.$id": PydanticObjectId(current_user.id),
        "blog.$id": PydanticObjectId(blog_id)
    })
    
    blog_collection = Blog.get_pymongo_collection()
    
    if existing_like:
        # Unlike: Remove from BlogLike
        await like_repo.delete({"id": existing_like["id"]}, soft=False)
        await blog_collection.update_one(
            {"_id": ObjectId(blog_id)},
            {"$inc": {"likes": -1}}
        )
        status = "unliked"
        likes_diff = -1
    else:
        # Like: Create BlogLike
        await like_repo.create({
            "user": str(current_user.id),
            "blog": str(blog_id)
        })
        await blog_collection.update_one(
            {"_id": ObjectId(blog_id)},
            {"$inc": {"likes": 1}}
        )
        status = "liked"
        likes_diff = 1
    
    # Get updated count
    current_likes = blog.get('likes', 0) if isinstance(blog, dict) else getattr(blog, 'likes', 0)
    total_likes = max(0, (current_likes or 0) + likes_diff)
    
    return {
        "message": "Toggle success", 
        "status": status,
        "total_likes": total_likes
    }

# --- Signal Listeners for Analytics ---

async def handle_blog_view(instance: dict, **kwargs):
    """
    Signal handler to increment view count on blogs.
    Skips if the viewer is the author.
    """
    user = kwargs.get("user")
    
    blog_id = instance.get("id")
    if not blog_id:
        return
        
    # Extract author ID (handle both populated dict and raw ID)
    author = instance.get("author")
    author_id = None
    if isinstance(author, dict):
        author_id = str(author.get("id"))
    else:
        author_id = str(author)
        
    # Extract current user ID
    current_user_id = str(user.id) if user else None
    
    # Check if user is the author
    if current_user_id and author_id and current_user_id == author_id:
        # Same user as author, do not increment views
        return
        
    # Create a BlogView document in MongoDB and increment Blog counter
    try:
        from schemas.blogs import BlogView
        from bson import ObjectId
        
        request = kwargs.get("request")
        ip_address = request.client.host if request and hasattr(request, "client") and request.client else None
        
        view_repo = get_repo(BlogView, request)
        await view_repo.create({
            "user": str(current_user_id) if current_user_id else None,
            "blog": str(blog_id),
            "ip_address": ip_address
        })
        
        await Blog.get_pymongo_collection().update_one(
            {"_id": ObjectId(blog_id)},
            {"$inc": {"views": 1}}
        )
    except Exception as e:
        print(f"Analytics Error (View Count): {e}")

# Register the signal listener
from backbone.core.signals import signals
signals.on_view.connect(Blog, handle_blog_view)
