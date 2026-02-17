from fastapi import FastAPI
from contextlib import asynccontextmanager
from motor.motor_asyncio import AsyncIOMotorClient
from backbone import (
    AuthRouter, IsOwner,AllowAny, GenericCrud, BeanieRepository, BackboneConfig,
    GenericList, GenericCreate, GenericRetrieve, GenericUpdate, GenericDelete
)
from schema import BlogSchema, NoteSchema, PlaylistSchema
from pydantic_settings import BaseSettings

# Configuration
class AppConfig(BaseSettings):
    MONGODB_URL: str = "mongodb+srv://justj:admin@cluster0.fsgzjrl.mongodb.net"
    DATABASE_NAME: str = "backbone_app"

config = AppConfig()

# Database Connection
client = AsyncIOMotorClient(config.MONGODB_URL)
database = client[config.DATABASE_NAME]

# App Definition
app = FastAPI(title="Modular Backbone Framework")

from backbone.core.models import User, Session

# --------------------------------------------------------------------------
# Backbone Global Configuration
# Sets the default Database and Repository Class for all GenericCrud views.
# Also manages the Application Lifespan (Startup/Shutdown).
# --------------------------------------------------------------------------
BackboneConfig(
    app=app, 
    config=config, 
    database=database,
    mongo_client=client, 
    repository_class=BeanieRepository,
    document_models=[User, Session, BlogSchema, NoteSchema, PlaylistSchema]
)

# Initialize Resources
# Views explicitly use the configured Defaults from BackboneConfig

# 1. Auth (AuthRouter should ideally use context too, but we pass db for now or update it)
# Let's pass db explicitly to Auth as it might be special, or update Auth to use context.
# Keeping explicit injection for Auth is fine, but views below use Context.
auth = AuthRouter(db_instance=database)

# # 2. Blog
# blog = GenericCrud(
#     schema=BlogSchema,
#     prefix="/blogs",
#     tags=["Blogs"],
#     list_fields=["title", "author_id"],
#     filter_fields=["tags"],
#     permission_classes=[IsOwner]
# )

# 3. Notes (Demonstrating Granular Control as requested)
# List & Create
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

# Detail Operations (Retrieve, Update, Delete)
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

# # 4. Playlists
# playlist = GenericCrud(
#     schema=PlaylistSchema,
#     prefix="/playlists",
#     tags=["Playlists"],
#     list_fields=["name", "is_public"],
#     permission_classes=[IsOwner]
# )

# Register Routers
# We can also automate this if we wanted, but explicit is better for control
app.include_router(auth.router)

# Notes (Granular)
app.include_router(note_list.router)
app.include_router(note_create.router)
app.include_router(note_retrieve.router)
app.include_router(note_update.router)
app.include_router(note_delete.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8012, reload=True)
