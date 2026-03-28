from fastapi import FastAPI

from backbone import BackboneConfig
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
# Register Routers
# --------------------------------------------------------------------------
app.include_router(users_router, prefix="/api")
app.include_router(blogs_router, prefix="/api")
app.include_router(media_router, prefix="/api")
app.include_router(content_router, prefix="/api")
app.include_router(playlists_router, prefix="/api")
app.include_router(pages_router, prefix="/pages")
app.include_router(auth_pages_router, prefix="/pages")


@app.get("/")
async def root():
    return {"message": "Blogermenia Backbone FastApi Server"}
