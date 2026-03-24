"""
Backbone Framework — Usage Examples
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

10 examples showing real-world usage of the Backbone framework.
These demonstrate both the new ``as_router()`` pattern and the
legacy constructor pattern.

Note: These examples assume you have Beanie Document models
      defined elsewhere (e.g., Blog, BlogCategory, etc.).
"""

from typing import Any, Optional

from beanie import Document, Link
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backbone import (
    AllowAny,
    BackboneRouter,
    BeanieRepository,
    GenericCrudView,
    GenericCustomApiView,
    GenericListView,
    GenericStatsView,
    IsAuthenticated,
    IsOwner,
)
from backbone.core.mixins import ViewContext

router = APIRouter()


# ── Example 1: Minimal View ─────────────────────────────────────────────────
# 3 lines of code → full CRUD API with pagination, search, filters

class BlogView(GenericCrudView):
    """Full CRUD for blogs with zero boilerplate."""

    schema = Document  # Replace with your Blog model
    search_fields = ["title", "excerpt"]


# router.include_router(BlogView.as_router("/blogs", tags=["Blogs"]))


# ── Example 2: Filtered Queryset ────────────────────────────────────────────
# Override get_queryset() to scope results

class PublishedBlogView(GenericCrudView):
    """Only show published blogs to non-admin users."""

    schema = Document  # Replace with Blog
    permission_classes = [AllowAny]

    async def get_queryset(self, request: Request, user: Any) -> dict:
        base = await super().get_queryset(request, user)
        if not user or not getattr(user, "is_staff", False):
            return {**base, "isPublished": True}
        return base


# router.include_router(PublishedBlogView.as_router("/blogs", tags=["Blogs"]))


# ── Example 3: before_create — Auto-assign Author ───────────────────────────
# Set the author field automatically from the authenticated user

class AuthorAutoAssignView(GenericCrudView):
    """Automatically set author to the authenticated user on creation."""

    schema = Document  # Replace with Blog
    permission_classes = [IsAuthenticated]

    async def before_create(self, data: dict, user: Any) -> dict:
        data["author"] = str(user.id)
        return data


# router.include_router(AuthorAutoAssignView.as_router("/blogs", tags=["Blogs"]))


# ── Example 4: after_create — Send Notification ─────────────────────────────
# Post-create hook for side effects

class NotifyOnCreateView(GenericCrudView):
    """Send a notification email after creating a resource."""

    schema = Document  # Replace with Blog
    permission_classes = [IsAuthenticated]

    async def after_create(self, instance: Any, user: Any) -> Any:
        # Example: send notification (non-blocking)
        print(f"New {self.schema.__name__} created by {user.id}: {instance.id}")
        # await send_email(user.email, "New post created!", ...)
        return instance


# router.include_router(NotifyOnCreateView.as_router("/blogs", tags=["Blogs"]))


# ── Example 5: before_delete — Prevent Deletion of Published ────────────────
# Guard hook that can cancel the operation

class GuardedDeleteView(GenericCrudView):
    """Prevent deletion of published blogs."""

    schema = Document  # Replace with Blog
    permission_classes = [IsAuthenticated]

    async def before_delete(self, instance: dict, user: Any) -> bool:
        if instance.get("isPublished"):
            raise HTTPException(
                status_code=400,
                detail="Cannot delete a published blog. Unpublish it first.",
            )
        return True


# router.include_router(GuardedDeleteView.as_router("/blogs", tags=["Blogs"]))


# ── Example 6: Custom Response Schema ───────────────────────────────────────
# Use a different Pydantic model for list/detail responses

class BlogListItemSchema(BaseModel):
    """Lightweight schema for list responses — excludes content."""

    id: str
    title: str
    slug: str
    created_at: Optional[str] = None


class BlogListView(GenericCrudView):
    """Use a slim response schema for listing, full schema for detail."""

    schema = Document  # Replace with Blog
    response_schema = BlogListItemSchema
    list_fields = ["id", "title", "slug", "created_at"]


# router.include_router(BlogListView.as_router("/blogs", tags=["Blogs"]))


# ── Example 7: Combined Overrides ───────────────────────────────────────────
# Multiple hooks and config in one view

class FullBlogView(GenericCrudView):
    """Production blog view with all customisations."""

    schema = Document  # Replace with Blog
    permission_classes = [IsAuthenticated]
    search_fields = ["title", "subtitle", "excerpt"]
    filter_fields = ["category.$id", "featured", "author.$id"]
    lookup_field = "slug"
    fetch_links = True

    async def get_queryset(self, request: Request, user: Any) -> dict:
        base = await super().get_queryset(request, user)
        return {**base, "isPublished": True}

    async def before_create(self, data: dict, user: Any) -> dict:
        data["author"] = str(user.id)
        data["isPublished"] = False  # Draft by default
        return data

    async def before_update(
        self,
        instance: dict,
        data: dict,
        user: Any,
    ) -> dict:
        # Prevent non-owners from updating
        if str(instance.get("author")) != str(user.id):
            raise HTTPException(403, "You can only edit your own blogs.")
        return data


# router.include_router(FullBlogView.as_router("/blogs", tags=["Blogs"]))


# ── Example 8: Custom Endpoint + CRUD ───────────────────────────────────────
# @action decorator for custom endpoints alongside standard CRUD

from backbone.generic.action import action


class BlogWithActionsView(GenericCrudView):
    """CRUD + custom action endpoints."""

    schema = Document  # Replace with Blog
    permission_classes = [AllowAny]
    search_fields = ["title"]

    @action(detail=True, methods=["post"], tags=["Blogs"])
    async def like(self, request: Request, pk: str) -> dict:
        """Toggle like for a blog post."""
        await self.resolve_context(request)
        blog = await self.get_object(pk, request, None)
        # ... your like/unlike logic here
        return {"status": "liked", "blog_id": pk}

    @action(detail=False, methods=["get"], tags=["Blogs"])
    async def trending(self, request: Request) -> list:
        """Get trending blogs."""
        await self.resolve_context(request)
        results, _ = await self._repository.get_all(
            {"is_deleted": False},
            sort=[("views", -1)],
            limit=5,
        )
        return results


# router.include_router(BlogWithActionsView.as_router("/blogs", tags=["Blogs"]))


# ── Example 9: Two Views on One Router ──────────────────────────────────────
# Compose multiple view sets using BackboneRouter

class CategoryView(GenericCrudView):
    """CRUD for blog categories."""

    schema = Document  # Replace with BlogCategory
    permission_classes = [AllowAny]
    search_fields = ["name", "slug"]


class PostView(GenericCrudView):
    """CRUD for blog posts."""

    schema = Document  # Replace with Blog
    permission_classes = [IsAuthenticated]
    search_fields = ["title"]


# Use BackboneRouter to compose them
# backbone_router = BackboneRouter(prefix="/api/v1")
# backbone_router.register_view("/categories", CategoryView, tags=["Categories"])
# backbone_router.register_view("/posts", PostView, tags=["Posts"])
# app.include_router(backbone_router.get_router())


# ── Example 10: Stats View ──────────────────────────────────────────────────
# Aggregated dashboard statistics

class DashboardStats(GenericStatsView):
    """Dashboard statistics — counts and sums across models."""

    schema = Document  # Any model works as the base
    stats_config = [
        {
            "name": "total_blogs",
            "model": Document,  # Replace with Blog
            "type": "count",
            "filters": {"is_deleted": False},
        },
        {
            "name": "total_views",
            "model": Document,  # Replace with BlogView
            "type": "count",
            "filters": {"is_deleted": False},
        },
        # Sum example:
        # {
        #     "name": "total_likes",
        #     "model": Blog,
        #     "type": "sum",
        #     "field": "likes",
        #     "filters": {"is_deleted": False},
        # },
    ]


# router.include_router(DashboardStats.as_router("/stats", tags=["Dashboard"]))
