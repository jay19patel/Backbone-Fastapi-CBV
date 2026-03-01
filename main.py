from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from backbone import (
    BackboneConfig,
    Settings,
    background_task
)
from backbone.core.rate_limit import RateLimit
import os

# Schemas
from backbone.core.models import User
from schemas.blogs import Blog, BlogCategory, BlogLike, BlogView
from schemas.playlists import Playlist
from schemas.content import FAQ, Testimonial, ContactMessage
from schemas.notes import Note

# Routers
from api.users import router as users_router
from api.blogs import router as blogs_router
from api.playlists import router as playlists_router
from api.content import router as content_router
from api.notes import router as notes_router

# --------------------------------------------------------------------------
# Application Setup & Dependencies
# --------------------------------------------------------------------------
class AppConfig(Settings):
    ENVIRONMENT: str = "develop"
    MONGODB_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "backbone_app"
    REDIS_URL: str = "redis://localhost:6380/0"
    CACHE_ENABLED: bool = True
    RATE_LIMIT_ENABLED: bool = True

config = AppConfig()

app = FastAPI(title="Modular Backbone Framework")

# CORS middleware for Nextjs frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------
# Backbone Global Configuration
# --------------------------------------------------------------------------
models_to_register = [
    User,
    Blog, BlogCategory, BlogLike, BlogView,
    Playlist,
    FAQ, Testimonial, ContactMessage,
    Note
]

BackboneConfig(
    app=app, 
    config=config, 
    document_models=models_to_register,
    prefix="/api"
)

# --------------------------------------------------------------------------
# Register Routers
# --------------------------------------------------------------------------
# Use standard naming conventions for APIs
app.include_router(users_router, prefix="/api")
app.include_router(blogs_router, prefix="/api")
app.include_router(playlists_router, prefix="/api")
app.include_router(content_router, prefix="/api")
app.include_router(notes_router, prefix="/api")

@app.get("/")
async def root():
    return {"message": "Blogermenia Backbone FastApi Server"}
