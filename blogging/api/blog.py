"""
blogging/api/blog
~~~~~~~~~~~~~~~~~

Implements CBVs and generic endpoints for blogging administration and public queries.
Provides views for Category, Post, and Stats.
"""

from __future__ import annotations

from typing import Any

from beanie import PydanticObjectId
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request

from backbone.core.dependencies import get_optional_user
from backbone.core.models import User
from backbone.core.permissions import AllowAny
from backbone.generic.action import action
from backbone.generic.views import GenericCrudView, GenericStatsView
from blogging.schemas.blog import Blog, BlogCategory, BlogLike, BlogView


class BlogCategoryView(GenericCrudView):
    """View endpoints for managing Blog Categories."""

    schema = BlogCategory
    search_fields = ["name", "slug"]
    list_fields = ["id", "name", "slug", "created_at"]
    permission_classes = [AllowAny]


class BlogPostView(GenericCrudView):
    """View endpoints for reading and writing Blog Posts."""

    schema = Blog
    search_fields = ["title", "subtitle", "excerpt", "introduction"]
    list_fields = [
        "id",
        "title",
        "slug",
        "thumbnail",
        "author",
        "category",
        "created_at",
        "views",
        "likes",
    ]
    filter_fields = ["slug", "author.$id", "category.name", "category.$id", "isPublished"]
    fetch_links = True
    permission_classes = [AllowAny]
    lookup_field = "slug"

    @staticmethod
    def _extract_blog_id(blog: Any) -> str | None:
        """Safely extract string ID representation from a Blog instance or dictionary."""
        if not blog:
            return None
        if isinstance(blog, dict):
            return str(blog.get("id") or blog.get("_id") or "")
        return str(getattr(blog, "id", getattr(blog, "_id", "")))

    async def _is_liked_by_user(self, blog_id: str, user: User | None) -> bool:
        """Check if the given user has liked the specified blog post."""
        if not user or not blog_id:
            return False
        try:
            existing_like = await BlogLike.find_one(
                {
                    "user.$id": PydanticObjectId(user.id),
                    "blog.$id": PydanticObjectId(blog_id),
                    "is_deleted": False,
                }
            )
            return bool(existing_like)
        except Exception:
            return False

    async def after_retrieve(self, instance: dict, request: Request, user: Any) -> dict:
        """Enriches retrieve payload with is_liked metrics for current user."""
        instance = await super().after_retrieve(instance, request, user)
        blog_id = self._extract_blog_id(instance)

        if isinstance(instance, dict) and blog_id:
            instance["likes"] = int(instance.get("likes") or 0)
            instance["is_liked"] = await self._is_liked_by_user(blog_id, user)

        return instance

    @action(detail=True, methods=["post"], tags=["Blogs"])
    async def like(
        self, request: Request, pk: str, current_user: User | None = Depends(get_optional_user)
    ) -> dict:
        """
        Toggle like action for a blog post.
        Accepts slug or object ID as target pk identifier.
        """
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required to like a blog")

        # Resolve the target post
        try:
            blog_id_obj = PydanticObjectId(pk) if len(pk) == 24 else None
        except Exception:
            blog_id_obj = None

        blog = await Blog.find_one(
            {
                "$or": [{"slug": pk}, {"_id": blog_id_obj}] if blog_id_obj else [{"slug": pk}],
                "is_deleted": False,
            }
        )

        if not blog:
            raise HTTPException(status_code=404, detail="Blog not found")

        blog_id = str(blog.id)

        # Check existing like
        existing_like = await BlogLike.find_one(
            {
                "user.$id": PydanticObjectId(current_user.id),
                "blog.$id": PydanticObjectId(blog_id),
            }
        )

        if existing_like:
            # Hard delete the like record
            await existing_like.delete()
            status = "unliked"
        else:
            # Create a new like record
            new_like = BlogLike(user=current_user, blog=blog)
            await new_like.insert()
            status = "liked"

        # Recalculate true likes count atomically
        total_likes = await BlogLike.find(
            {
                "blog.$id": PydanticObjectId(blog_id),
                "is_deleted": False,
            }
        ).count()

        # Save true like count on Blog
        await Blog.get_pymongo_collection().update_one(
            {"_id": ObjectId(blog_id)},
            {"$set": {"likes": int(total_likes)}},
        )

        return {
            "message": "Toggle success",
            "status": status,
            "total_likes": total_likes,
        }


class BlogStats(GenericStatsView):
    """View endpoints for compiling aggregate analytics on blogging."""

    schema = Blog
    stats_config = [
        {
            "name": "blogs_published",
            "model": Blog,
            "type": "count",
            "filters": {"is_deleted": False, "isPublished": True},
        },
        {
            "name": "total_categories",
            "model": BlogCategory,
            "type": "count",
            "filters": {"is_deleted": False},
        },
        {
            "name": "total_views",
            "model": BlogView,
            "type": "count",
            "filters": {"is_deleted": False},
        },
        {
            "name": "total_likes",
            "model": BlogLike,
            "type": "count",
            "filters": {"is_deleted": False},
        },
        {
            "name": "active_users",
            "model": User,
            "type": "count",
            "filters": {"is_deleted": False, "is_active": True},
        },
    ]


router = APIRouter()
router.include_router(BlogCategoryView.as_router("/blogs/categories", tags=["Blog Categories"]))
router.include_router(BlogStats.as_router("/blogs/stats", tags=["Blogs"]))
router.include_router(BlogPostView.as_router("/blogs", tags=["Blogs"]))
