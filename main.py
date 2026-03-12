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
from backbone.core.models import User, Session, Attachment, LogEntry, TaskLog
from schemas.blogs import Blog, BlogCategory, BlogLike, BlogView
from schemas.playlists import Playlist
from schemas.content import FAQ, Testimonial, ContactMessage

# Routers
from api.users import router as users_router
from api.blogs import router as blogs_router
from api.playlists import router as playlists_router
from api.content import router as content_router
from api.chats import router as chats_router
from backbone.core.media_router import router as media_router

# --------------------------------------------------------------------------
# Application Setup & Dependencies
# --------------------------------------------------------------------------
from backbone.core.settings import settings

app = FastAPI(title="Modular Backbone Framework")


models_to_register = [
    User, Session, Attachment, LogEntry, TaskLog,
    Blog, BlogCategory, BlogLike, BlogView,
    Playlist,
    FAQ, Testimonial, ContactMessage
]

BackboneConfig(
    app=app, 
    config=settings, 
    document_models=models_to_register
)

# --------------------------------------------------------------------------
# Register Routers
# --------------------------------------------------------------------------
# Use standard naming conventions for APIs
app.include_router(users_router, prefix="/api")
app.include_router(blogs_router, prefix="/api")
app.include_router(playlists_router, prefix="/api")
app.include_router(content_router, prefix="/api")
app.include_router(chats_router, prefix="/api/chat")
app.include_router(media_router, prefix="/api")

@app.get("/")
async def root():
    return {"message": "Blogermenia Backbone FastApi Server"}
