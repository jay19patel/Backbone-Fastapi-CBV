from fastapi import FastAPI

from backbone import (
    BackboneConfig,
    on_create,
    on_update,
    on_delete,
    on_field_change,
    log as backbone_log,
)
from backbone.core.settings import settings

# Schemas
from schemas.blogs import Blog, BlogCategory, BlogLike, BlogView
from schemas.content import FAQ, Testimonial, Contact
from schemas.playlists import Playlist

# Routers
from api.users import router as users_router
from api.blogs import router as blogs_router
from backbone.core.media_router import router as media_router
from api.content import router as content_router
from api.playlists import router as playlists_router
from api.chat import router as chat_router
from pages.contact import router as pages_router
from backbone.auth.pages import router as auth_pages_router


# --------------------------------------------------------------------------
# Application Setup
# --------------------------------------------------------------------------
app = FastAPI(title="Modular Backbone Framework")

models_to_register = [
    Blog,
    BlogCategory,
    BlogLike,
    BlogView,
    FAQ,
    Testimonial,
    Contact,
    Playlist,
]

BackboneConfig(
    app=app,
    config=settings,
    document_models=models_to_register,
)


# --------------------------------------------------------------------------
# Testing Hooks (Blog model)
# --------------------------------------------------------------------------
def _blog_payload(instance: Blog) -> dict:
    return {
        "id": str(getattr(instance, "id", "") or ""),
        "slug": getattr(instance, "slug", None),
        "title": getattr(instance, "title", None),
        "isPublished": getattr(instance, "isPublished", None),
        "is_deleted": getattr(instance, "is_deleted", None),
    }


@on_create(Blog)
async def blog_on_create_hook(instance: Blog, **kwargs):
    backbone_log(
        "Blog hook triggered: on_create",
        hook="on_create",
        model="Blog",
        payload=_blog_payload(instance),
    )


@on_update(Blog)
async def blog_on_update_hook(instance: Blog, changed_fields=None, **kwargs):
    backbone_log(
        "Blog hook triggered: on_update",
        hook="on_update",
        model="Blog",
        payload=_blog_payload(instance),
        changed_fields=list((changed_fields or {}).keys()),
    )


@on_delete(Blog)
async def blog_on_delete_hook(instance: Blog, **kwargs):
    backbone_log(
        "Blog hook triggered: on_delete",
        hook="on_delete",
        model="Blog",
        payload=_blog_payload(instance),
    )


@on_field_change(Blog, fields=["title", "excerpt", "isPublished", "is_deleted"])
async def blog_on_field_change_hook(instance: Blog, changed_fields=None, matched_fields=None, **kwargs):
    backbone_log(
        "Blog hook triggered: on_field_change",
        hook="on_field_change",
        model="Blog",
        payload=_blog_payload(instance),
        matched_fields=matched_fields or [],
        changed_fields=list((changed_fields or {}).keys()),
    )


# --------------------------------------------------------------------------
# Register Routers
# --------------------------------------------------------------------------
app.include_router(users_router, prefix="/api")
app.include_router(blogs_router, prefix="/api")
app.include_router(media_router, prefix="/api")
app.include_router(content_router, prefix="/api")
app.include_router(playlists_router, prefix="/api")
app.include_router(chat_router, prefix="/api/chat", tags=["AI Chat"])
app.include_router(pages_router, prefix="/pages")
app.include_router(auth_pages_router, prefix="/pages")


@app.get("/")
async def root():
    return {"message": "Blogermenia Backbone FastApi Server"}
