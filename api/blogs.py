from fastapi import APIRouter, HTTPException, Query, Request, Depends
from backbone import GenericCrudView, AllowAny, BeanieRepository
from schemas.blogs import Blog, BlogCategory, BlogLike, BlogView
from backbone.core.models import User
from backbone.core.dependencies import get_optional_user, get_current_user
from beanie import PydanticObjectId
from typing import List, Optional, Any
import random

from backbone.generic.views import GenericCrudView, GenericStatsView
from backbone.generic.action import action

# ── View Classes ────────────────────────────────────────────────────────────

class BlogCategoryView(GenericCrudView):
    schema = BlogCategory
    search_fields = ["name", "slug"]
    permission_classes = [AllowAny]

class BlogPostView(GenericCrudView):
    schema = Blog
    search_fields = ["title", "subtitle", "excerpt", "introduction"]
    list_fields = ["id", "title", "slug", "thumbnail", "author", "category", "created_at", "views", "likes"]
    fetch_links = True
    permission_classes = [AllowAny]
    lookup_field = "slug"
    filter_fields = ["slug", "author.$id", "category.name", "category.$id", "featured"]


    @action(detail=True, methods=["post"], tags=["Blogs"])
    async def like(
        self,
        request: Request,
        pk: str,
        current_user: Optional[User] = Depends(get_optional_user)
    ):
        """Toggle like for a blog. Supports both ID and Slug."""
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required to like a blog")

        blog_repo = get_repo(Blog, request)
        blog = await blog_repo.get_one({
            "$or": [{"slug": pk}, {"id": pk}],
            "is_deleted": False
        })
        
        if not blog:
            raise HTTPException(status_code=404, detail="Blog not found")
            
        blog_id = str(blog.id) if hasattr(blog, "id") else blog.get("id")
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

class BlogStats(GenericStatsView):
    schema = Blog
    stats_config = [
        {"name": "blogs_published", "model": Blog, "type": "count", "filters": {"is_deleted": False, "isPublished": True}},
        {"name": "total_categories", "model": BlogCategory, "type": "count", "filters": {"is_deleted": False}},
        {"name": "total_views", "model": BlogView, "type": "count", "filters": {"is_deleted": False}},
        {"name": "total_likes", "model": BlogLike, "type": "count", "filters": {"is_deleted": False}},
        {"name": "active_users", "model": User, "type": "count", "filters": {"is_deleted": False, "is_active": True}}
    ]

# ── Router Initialization ───────────────────────────────────────────────────

router = APIRouter()

# Register View Routers
router.include_router(BlogCategoryView.as_router("/blogs/categories", tags=["Blog Categories"]))
router.include_router(BlogStats.as_router("/blogs/stats", tags=["Blogs"]))

# Generic CRUD included LAST to handle both List and Detail (resolved via get_object)
router.include_router(BlogPostView.as_router("/blogs", tags=["Blogs"]))


# Standard generic routes are registered above via as_router()

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
        
    global _recent_views_cache
    if '_recent_views_cache' not in globals():
        _recent_views_cache = {}
        
    try:
        request = kwargs.get("request")
        ip_address = request.client.host if request and hasattr(request, "client") and request.client else None
    except Exception:
        ip_address = None
        
    import time
    now_ts = time.time()
    
    # Clean up cache every ~1000 requests loosely (prevent memory leak)
    if len(_recent_views_cache) > 10000:
        _recent_views_cache.clear()
        
    cache_key = f"{blog_id}:{current_user_id or ip_address or 'unknown'}"
    
    last_view_time = _recent_views_cache.get(cache_key)
    if last_view_time and (now_ts - last_view_time) < (15 * 60): # 15 minutes
        return
        
    _recent_views_cache[cache_key] = now_ts

    # Deduplicate recent views (15 minutes) in Database (for multi-worker sync)
    try:
        from schemas.blogs import BlogView
        from bson import ObjectId
        from datetime import datetime, timezone, timedelta
        
        view_repo = get_repo(BlogView, request)
        
        # Check if a view was recorded recently (15 minutes window)
        time_threshold = datetime.now(timezone.utc) - timedelta(minutes=15)
        query = {
            "blog.$id": ObjectId(blog_id),
            "created_at": {"$gte": time_threshold}
        }
        
        if current_user_id:
            query["user.$id"] = ObjectId(current_user_id)
        elif ip_address:
            query["ip_address"] = ip_address
        else:
            query["ip_address"] = "unknown"
            
        recent_view = await BlogView.get_pymongo_collection().find_one(query)
        if recent_view:
            return  # Skip incrementing, already viewed recently

        # Create a BlogView document in MongoDB and increment Blog counter
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

# Register the signal listener safely to prevent duplication across module reloads
from backbone.core.signals import signals

# Remove old handlers with the same name to prevent duplicates
signals.on_view._handlers[Blog] = [
    h for h in signals.on_view._handlers.get(Blog, []) 
    if getattr(h, "__name__", "") != "handle_blog_view"
]

signals.on_view.connect(Blog, handle_blog_view)
