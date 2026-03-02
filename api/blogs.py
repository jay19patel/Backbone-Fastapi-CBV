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
router.include_router(blog_category_crud.router)
router.include_router(blog_crud.router)

# --- Custom Routes ---

class BlogRepository(BeanieRepository[Blog]):
    pass

class BlogCategoryRepository(BeanieRepository[BlogCategory]):
    pass

def get_repo(model) -> BeanieRepository:
    from backbone import BackboneConfig
    repo = BeanieRepository(BackboneConfig.get_instance().database)
    repo.initialize(model)
    return repo


@router.get("/blogs/stats/", tags=["Blogs"])
async def get_blog_stats():
    blog_repo = get_repo(Blog)
    total_blogs = await blog_repo.count({"is_deleted": False})
    
    cat_repo = get_repo(BlogCategory)
    total_categories = await cat_repo.count({"is_deleted": False})
    
    return {
        "total_posts": total_blogs,
        "total_categories": total_categories,
        "total_views": 0,
        "total_likes": 0
    }



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
