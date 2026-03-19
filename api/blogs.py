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

from backbone.generic.action import action

class BlogViewSet(GenericCrud):
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

# Router for Blogs
blog_crud = BlogViewSet(
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

# --- Custom Blog Detail with Section Attachment Resolution ---
@router.get("/blogs/{slug}", tags=["Blogs"])
async def get_blog_detail(
    slug: str,
    request: Request,
    user = Depends(get_optional_user)
):
    """
    Fetch a blog by slug/id, resolving author, category, thumbnail, and
    image section attachments.
    """
    from bson import ObjectId
    from backbone.core.url_utils import get_media_url
    from backbone.core.models import Attachment

    # --- Step 1: Fetch blog with author/category/thumbnail resolved via aggregation ---
    collection = Blog.get_pymongo_collection()

    try:
        slug_as_oid = ObjectId(slug) if len(slug) == 24 else None
    except Exception:
        slug_as_oid = None

    match_q = {"slug": slug, "is_deleted": {"$ne": True}}
    if slug_as_oid:
        match_q = {"$or": [{"slug": slug}, {"_id": slug_as_oid}], "is_deleted": {"$ne": True}}

    pipeline = [
        {"$match": match_q},
        # Resolve author
        {"$lookup": {
            "from": "users",
            "let": {"aid": {"$ifNull": ["$author.$id", "$author.id", "$author"]}},
            "pipeline": [
                {"$match": {"$expr": {"$eq": ["$_id", "$$aid"]}}},
                {"$project": {"id": "$_id", "_id": 0, "full_name": 1, "email": 1, "username": 1, "headline": 1}}
            ],
            "as": "author"
        }},
        {"$unwind": {"path": "$author", "preserveNullAndEmptyArrays": True}},
        # Resolve category
        {"$lookup": {
            "from": "blog_categories",
            "let": {"cid": {"$ifNull": ["$category.$id", "$category.id", "$category"]}},
            "pipeline": [
                {"$match": {"$expr": {"$eq": ["$_id", "$$cid"]}}},
                {"$project": {"id": "$_id", "_id": 0, "name": 1, "slug": 1}}
            ],
            "as": "category"
        }},
        {"$unwind": {"path": "$category", "preserveNullAndEmptyArrays": True}},
        # Resolve thumbnail
        {"$lookup": {
            "from": "attachments",
            "let": {"tid": {"$ifNull": ["$thumbnail.$id", "$thumbnail.id", "$thumbnail"]}},
            "pipeline": [
                {"$match": {"$expr": {"$eq": ["$_id", "$$tid"]}}},
                {"$project": {"id": "$_id", "_id": 0, "file_path": 1, "filename": 1, "content_type": 1}}
            ],
            "as": "thumbnail"
        }},
        {"$unwind": {"path": "$thumbnail", "preserveNullAndEmptyArrays": True}},
        {"$project": {"embedding": 0}},
    ]

    results = await collection.aggregate(pipeline).to_list(length=1)

    if not results:
        raise HTTPException(status_code=404, detail="Blog not found")

    doc = results[0]
    doc["id"] = str(doc.pop("_id"))

    # --- Step 2: Resolve section attachment IDs in Python ---
    att_id_to_section_idx = {}  # attachment_id_str -> list of section indices
    for i, section in enumerate(doc.get("sections", [])):
        if section.get("type") != "image":
            continue
        raw = section.get("attachment")
        if not raw:
            continue

        # Normalize: could be a plain string ID, a dict with $id (DBRef), or a dict with id
        if isinstance(raw, str) and len(raw) == 24:
            att_id_str = raw
        elif isinstance(raw, dict):
            oid = raw.get("$id") or raw.get("id")
            att_id_str = str(oid) if oid else None
        else:
            att_id_str = None

        if att_id_str:
            att_id_to_section_idx.setdefault(att_id_str, []).append(i)

    if att_id_to_section_idx:
        # Fetch all referenced attachments in one query
        try:
            oid_list = [ObjectId(aid) for aid in att_id_to_section_idx.keys()]
            att_collection = Attachment.get_pymongo_collection()
            att_docs = await att_collection.find(
                {"_id": {"$in": oid_list}},
                {"file_path": 1, "filename": 1, "content_type": 1, "size": 1}
            ).to_list(length=len(oid_list))

            for att_doc in att_docs:
                att_id_str = str(att_doc["_id"])
                att_data = {
                    "id": att_id_str,
                    "file_path": att_doc.get("file_path", ""),
                    "filename": att_doc.get("filename", ""),
                    "content_type": att_doc.get("content_type", ""),
                    "size": att_doc.get("size"),
                }
                # Prepend base URL if needed
                fp = att_data["file_path"]
                if fp and fp.startswith("/media/"):
                    att_data["file_path"] = get_media_url(fp)

                # Assign back to each section that references this attachment
                for idx in att_id_to_section_idx.get(att_id_str, []):
                    doc["sections"][idx]["attachment"] = att_data
        except Exception as e:
            print(f"Warning: could not resolve section attachments: {e}")

    # --- Step 3: Serialize thumbnail file_path ---
    if isinstance(doc.get("thumbnail"), dict):
        fp = doc["thumbnail"].get("file_path", "")
        if fp and fp.startswith("/media/"):
            doc["thumbnail"]["file_path"] = get_media_url(fp)

    # --- Step 4: Sanitize remaining ObjectIds to strings ---
    def sanitize(obj):
        if isinstance(obj, dict):
            return {k: sanitize(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [sanitize(i) for i in obj]
        elif isinstance(obj, ObjectId):
            return str(obj)
        return obj

    doc = sanitize(doc)

    # Emit view signal (non-blocking)
    from backbone.core.signals import signals
    try:
        await signals.on_view.emit(doc, model_class=Blog, request=request, user=user)
    except Exception:
        pass

    return doc


# Generic Blogs CRUD handles listing, detail, creation, update, deletion
# This includes /blogs/ (GET, POST), /blogs/{slug} (PATCH, DELETE)
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
