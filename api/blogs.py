from fastapi import APIRouter, HTTPException, Query, Request, Depends
from backbone import GenericCrud, AllowAny, BeanieRepository
from schemas.blogs import Blog, BlogCategory
from backbone.core.models import User
from backbone.core.dependencies import get_optional_user
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
    list_fields=["id", "title", "slug", "thumbnail", "author", "category", "created_at"],
    fetch_links=True,
    permission_classes=[AllowAny],
    lookup_field="slug",
    filter_fields=["slug", "author.$id", "category.name", "category.$id", "featured"]
)

router = APIRouter()

# --- Custom Routes FIRST (to avoid being shadowed by generic slug route) ---

@router.get("/blogs/stats/", tags=["Blogs"])
async def get_blog_stats():
    blog_repo = get_repo(Blog)
    total_blogs = await blog_repo.count({"is_deleted": False})
    
    cat_repo = get_repo(BlogCategory)
    total_categories = await cat_repo.count({"is_deleted": False})
    
    # Aggregate total views and likes
    pipeline = [
        {"$match": {"is_deleted": False}},
        {"$group": {
            "_id": None,
            "total_views": {"$sum": "$views"},
            "total_likes": {"$sum": "$likes"}
        }}
    ]
    agg_results = await Blog.get_motor_collection().aggregate(pipeline).to_list(length=1)
    stats = agg_results[0] if agg_results else {"total_views": 0, "total_likes": 0}

    return {
        "total_posts": total_blogs,
        "total_categories": total_categories,
        "total_views": stats.get("total_views", 0),
        "total_likes": stats.get("total_likes", 0)
    }

@router.get("/blogs/featured/", tags=["Blogs"])
async def get_featured_blogs():
    """Get all featured blogs."""
    repo = get_repo(Blog)
    # Filter for featured blogs that are not deleted
    query = {"featured": True, "is_deleted": False}
    results = await repo.get_all(
        query, 
        fetch_links=True,
        limit=10,
        sort=[("created_at", -1)]
    )
    return {"results": results, "total": len(results)}

# Include generic routes AFTER custom specific routes
router.include_router(blog_category_crud.router)
router.include_router(blog_crud.router)

class BlogRepository(BeanieRepository[Blog]):
    pass

class BlogCategoryRepository(BeanieRepository[BlogCategory]):
    pass

def get_repo(model) -> BeanieRepository:
    from backbone import BackboneConfig
    repo = BeanieRepository(BackboneConfig.get_instance().database)
    repo.initialize(model)
    return repo


@router.post("/blogs/{blog_id_or_slug}/like/", tags=["Blogs"])
async def like_blog(
    blog_id_or_slug: str,
    current_user: Optional[User] = Depends(get_optional_user)
):
    """Toggle like for a blog. Supports both ID and Slug."""
    blog_repo = get_repo(Blog)
    blog = await blog_repo.get_one({
        "$or": [{"slug": blog_id_or_slug}, {"id": blog_id_or_slug}]
    })
    
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")
        
    # For now, return a successful toggle mock
    # In a real app, we would check BlogLike collection and current_user
    likes_count = blog.get('likes', 0) if isinstance(blog, dict) else getattr(blog, 'likes', 0)
    
    return {
        "message": "Toggle success", 
        "status": "liked",  # Hardcoded for now to satisfy frontend
        "total_likes": (likes_count or 0) + 1
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
        
    # Increment view count in MongoDB
    try:
        from bson import ObjectId
        await Blog.get_motor_collection().update_one(
            {"_id": ObjectId(blog_id)},
            {"$inc": {"views": 1}}
        )
    except Exception as e:
        print(f"Analytics Error (View Count): {e}")

# Register the signal listener
from backbone.core.signals import signals
signals.on_view.connect(Blog, handle_blog_view)
