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

# Routers
from api.users import router as users_router
from api.blogs import router as blogs_router
from backbone.core.media_router import router as media_router
from backbone.core.media_router import router as media_router

# --------------------------------------------------------------------------
# Application Setup & Dependencies
# --------------------------------------------------------------------------
from backbone.core.settings import settings

app = FastAPI(title="Modular Backbone Framework")


models_to_register = [
    User, Session, Attachment, LogEntry, TaskLog,
    Blog, BlogCategory, BlogLike, BlogView
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
app.include_router(media_router, prefix="/api")

@app.get("/")
async def root():
    return {"message": "Blogermenia Backbone FastApi Server"}
