"""
blogging/api/users
~~~~~~~~~~~~~~~~~~

Implements user-related analytics, ranking, and profile endpoints.
Provides custom routes first, followed by the GenericCrudView router for Users.
"""

from __future__ import annotations

import urllib.parse
from typing import Any

from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException

from backbone.core.models import Attachment, User
from backbone.core.permissions import AllowAny
from backbone.generic.views import GenericCrudView
from backbone.schemas import UserOut
from blogging.schemas.blog import Blog


class UserProfileOut(UserOut):
    """Pydantic response model enriching user profiles with blogging activity metrics."""

    blog_count: int = 0
    total_views: int = 0
    total_likes: int = 0


async def _enhance_user_with_stats(user: dict[str, Any]) -> dict[str, Any]:
    """
    Enriches raw user dictionary with blog totals and resolves profile images.
    Returns the modified dict safely.
    """
    user_id = user.get("id") or user.get("_id")
    if not user_id:
        return user

    try:
        obj_id = PydanticObjectId(user_id) if isinstance(user_id, str) else user_id
    except Exception:
        return user

    # 1. Total post count
    blog_count = await Blog.find({"author.$id": obj_id, "is_deleted": False}).count()

    # 2. Sum up views and likes of all posts (up to 1000 limit)
    blogs = await Blog.find({"author.$id": obj_id, "is_deleted": False}).limit(1000).to_list()
    total_views = sum(int(b.views or 0) for b in blogs)
    total_likes = sum(int(b.likes or 0) for b in blogs)

    # Normalize ID keys
    user["id"] = str(user_id)
    if "_id" in user:
        user["_id"] = str(user["_id"])

    # Attach stats
    user["blog_count"] = blog_count
    user["total_views"] = total_views
    user["total_likes"] = total_likes

    # 3. Resolve profile image attachment URL
    profile_image = user.get("profile_image")
    if profile_image:
        image_id = None
        if isinstance(profile_image, dict) and "$id" in profile_image:
            image_id = str(profile_image["$id"])
        elif isinstance(profile_image, dict) and "id" in profile_image:
            image_id = str(profile_image["id"])
        elif isinstance(profile_image, str | PydanticObjectId):
            image_id = str(profile_image)

        if image_id:
            try:
                attachment = await Attachment.get(PydanticObjectId(image_id))
                if attachment:
                    user["profile_image"] = attachment.model_dump(by_alias=True)
                    if "id" in user["profile_image"] and isinstance(
                        user["profile_image"]["id"], PydanticObjectId
                    ):
                        user["profile_image"]["id"] = str(user["profile_image"]["id"])
                    if "_id" in user["profile_image"]:
                        user["profile_image"]["_id"] = str(user["profile_image"]["_id"])
            except Exception:
                pass

    return user


class UserView(GenericCrudView):
    """View endpoints for general User management queries."""

    schema = User
    search_fields = ["full_name", "email", "headline", "bio"]
    list_fields = ["id", "full_name", "email", "headline", "profile_image"]
    fetch_links = True
    permission_classes = [AllowAny]


router = APIRouter()

# ── Custom Endpoints Mount FIRST to Avoid ID Routing Hijacking ────────────────


@router.get("/user/top-authors/", tags=["Users"])
async def get_top_authors() -> dict[str, list[dict[str, Any]]]:
    """Retrieve top 5 active users decorated with blogging productivity metrics."""
    users = await User.find({"is_active": True, "is_deleted": False}).limit(5).to_list()
    enhanced_users = []

    for user in users:
        enhanced_users.append(await _enhance_user_with_stats(user.model_dump(by_alias=True)))

    # Sort authors by total post views in descending order
    enhanced_users.sort(key=lambda u: u.get("total_views", 0), reverse=True)
    return {"results": enhanced_users}


@router.get("/user/all/", tags=["Users"])
async def get_all_users_with_stats(
    search: str | None = None,
    skip: int = 0,
    limit: int = 10,
) -> dict[str, Any]:
    """Query active authors, decorated with blogging analytics and support searching."""
    query_filter: dict[str, Any] = {"is_active": True, "is_deleted": False}

    if search:
        query_filter["$or"] = [
            {"full_name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
            {"headline": {"$regex": search, "$options": "i"}},
        ]

    # Query counts & listings
    total = await User.find(query_filter).count()
    users = await User.find(query_filter).skip(skip).limit(limit).to_list()

    enhanced_users = []
    for user in users:
        enhanced_users.append(await _enhance_user_with_stats(user.model_dump(by_alias=True)))

    return {"results": enhanced_users, "total": total}


@router.get("/user/profile/{email}/", response_model=UserProfileOut, tags=["Users"])
async def get_user_profile(email: str) -> dict[str, Any]:
    """Retrieve public author profile information by unique email address."""
    decoded_email = urllib.parse.unquote(email).strip().lower()
    user = await User.find_one({"email": decoded_email, "is_deleted": False})

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    enhanced = await _enhance_user_with_stats(user.model_dump(by_alias=True))
    return enhanced


@router.get("/user/{user_id}/", response_model=UserProfileOut, tags=["Users"])
async def get_user_by_id(user_id: str) -> dict[str, Any]:
    """Query user metrics by primary ID key."""
    try:
        obj_id = PydanticObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user ID format")

    user = await User.find_one({"_id": obj_id, "is_deleted": False})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    enhanced = await _enhance_user_with_stats(user.model_dump(by_alias=True))
    return enhanced


# ── Register Crud Routing LAST ───────────────────────────────────────────────
router.include_router(UserView.as_router("/users", tags=["Users"]))
