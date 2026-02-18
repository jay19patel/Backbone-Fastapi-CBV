from fastapi import FastAPI
from backbone import (
    BackboneConfig, 
    AuthRouter, 
    GenericList, 
    GenericCreate, 
    GenericRetrieve, 
    GenericUpdate, 
    GenericDelete, 
    GenericCrud,
    AllowAny,
    IsOwner,
    settings
)
from schema import BlogSchema, NoteSchema, PlaylistSchema
from backbone.core.models import User, Session, LogEntry

# --------------------------------------------------------------------------
# Application Setup & Dependencies
# --------------------------------------------------------------------------
class AppConfig(settings.__class__):
    ENVIRONMENT: str = "develop"
    MONGODB_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "backbone_app"
    REDIS_URL: str = "redis://localhost:6380/0"
    CACHE_ENABLED: bool = True

config = AppConfig()

# App Definition
app = FastAPI(title="Modular Backbone Framework")

# --------------------------------------------------------------------------
# Backbone Global Configuration
# --------------------------------------------------------------------------
BackboneConfig(
    app=app, 
    config=config, 
    document_models=[User, Session, LogEntry, BlogSchema, NoteSchema, PlaylistSchema]
)

# 1. Auth
auth = AuthRouter(config=config)

# 2. Notes (Demonstrating Granular Control)
note_list = GenericList(
    schema=NoteSchema,
    prefix="/notes",
    tags=["Notes List"],
    list_fields=["title", "is_pinned"],
    search_fields=["title", "body"],
    permission_classes=[AllowAny]
)

note_create = GenericCreate(
    schema=NoteSchema,
    prefix="/notes",
    tags=["Notes"],
    permission_classes=[IsOwner]
)

note_retrieve = GenericRetrieve(
    schema=NoteSchema,
    prefix="/notes",
    tags=["Notes"],
    permission_classes=[IsOwner]
)

note_update = GenericUpdate(
    schema=NoteSchema,
    prefix="/notes",
    tags=["Notes"],
    permission_classes=[IsOwner]
)

note_delete = GenericDelete(
    schema=NoteSchema,
    prefix="/notes",
    tags=["Notes"],
    permission_classes=[IsOwner]
)

# 3. Playlists (Full CRUD)
playlist_crud = GenericCrud(
    schema=PlaylistSchema,
    prefix="/playlists",
    tags=["Playlists"],
    search_fields=["name"],
    permission_classes=[IsOwner]
)

# Register Routers
app.include_router(auth.router)
app.include_router(note_list.router)
app.include_router(note_create.router)
app.include_router(note_retrieve.router)
app.include_router(note_update.router)
app.include_router(note_delete.router)
app.include_router(playlist_crud.router)

@app.get("/")
async def root():
    return {"message": "Backbone Framework: MongoDB-Only Edition"}
