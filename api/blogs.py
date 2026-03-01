from fastapi import APIRouter
from backbone import GenericCrud, AllowAny
from schemas.blogs import Blog, BlogCategory

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
    permission_classes=[AllowAny]
)

router = APIRouter()
router.include_router(blog_category_crud.router)
router.include_router(blog_crud.router)

# Custom routes can be added like so:
@router.post("/blogs/{slug}/like", tags=["Blogs"])
async def like_blog(slug: str):
    # Logic to like/unlike a blog
    return {"message": f"Toggled like for blog {slug}"}
