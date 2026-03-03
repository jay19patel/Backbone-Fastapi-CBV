from fastapi import APIRouter, HTTPException, Query, Request, Depends
from backbone import GenericCrud, AllowAny, BeanieRepository
from schemas.blogs import Blog, BlogCategory, BlogLike, BlogView
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
async def get_blog_stats(request: Request):
    try:
        blog_repo = get_repo(Blog, request)
        total_blogs = await blog_repo.count({"is_deleted": False})
        
        cat_repo = get_repo(BlogCategory, request)
        total_categories = await cat_repo.count({"is_deleted": False})
        
        # Aggregate total views and likes using Beanie find()
        pipeline = [
            {"$group": {
                "_id": None,
                "total_views": {"$sum": "$views"},
                "total_likes": {"$sum": "$likes"}
            }}
        ]
        
        # Beanie's aggregate returns a cursor
        cursor = Blog.find({"is_deleted": False}).aggregate(pipeline)
        agg_results = await cursor.to_list(length=1)
        
        stats = agg_results[0] if agg_results else {"total_views": 0, "total_likes": 0}

        return {
            "total_posts": total_blogs,
            "total_categories": total_categories,
            "total_views": stats.get("total_views", 0),
            "total_likes": stats.get("total_likes", 0)
        }
    except Exception as e:
        print(f"DEBUG ERROR in get_blog_stats: {str(e)}")
        # Fallback to simple counts if aggregation fails
        return {
            "total_posts": 0,
            "total_categories": 0,
            "total_views": 0,
            "total_likes": 0
        }

@router.get("/blogs/featured/", tags=["Blogs"])
async def get_featured_blogs(request: Request):
    """Get all featured blogs."""
    repo = get_repo(Blog, request)
    # Filter for featured blogs that are not deleted
    query = {"featured": True, "is_deleted": False}
    results = await repo.get_all(
        query, 
        populate_fields=repo.detect_populate_fields(Blog),
        limit=10,
        sort=[("created_at", -1)]
    )
    return {"results": results, "total": len(results)}

@router.get("/blogs/{id_or_slug}/", tags=["Blogs"])
async def get_blog_detail(
    request: Request,
    id_or_slug: str,
    current_user: Optional[User] = Depends(get_optional_user)
):
    """Get blog detail with like status for current user."""
    repo = get_repo(Blog, request)
    blog = await repo.get_one(
        {"$or": [{"slug": id_or_slug}, {"id": id_or_slug}], "is_deleted": False},
        populate_fields=repo.detect_populate_fields(Blog)
    )
    
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")
        
    # Check like status
    is_liked = False
    if current_user:
        like_repo = get_repo(BlogLike, request)
        from beanie import PydanticObjectId
        like = await like_repo.get_one({
            "user.$id": PydanticObjectId(current_user.id),
            "blog.$id": PydanticObjectId(blog["id"])
        })
        is_liked = True if like else False
        
    blog["is_liked"] = is_liked
    
    # Trigger view signal for analytics
    from backbone.core.signals import signals
    try:
        await signals.on_view.emit(blog, model_class=Blog, request=request, user=current_user)
    except:
        pass
        
    return blog

# Include generic routes AFTER custom specific routes
router.include_router(blog_category_crud.router)
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
        # Unlike: Remove from BlogLike and decrement count
        await like_repo.delete({"id": existing_like["id"]}, soft=False)
        await blog_collection.update_one(
            {"_id": ObjectId(blog_id)},
            {"$inc": {"likes": -1}}
        )
        status = "unliked"
        likes_diff = -1
    else:
        # Like: Create BlogLike and increment count
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
