import asyncio
from fastapi import FastAPI
from backbone import (
    BackboneConfig, 
    GenericList, 
    GenericCreate, 
    GenericRetrieve, 
    GenericUpdate, 
    GenericDelete, 
    GenericCrud,
    AllowAny,
    IsOwner,
    settings,
    Settings,
    signals,
    background_task
)
from schema import BlogSchema, NoteSchema, PlaylistSchema
from backbone.core.models import User, Session, LogEntry

# --------------------------------------------------------------------------
# Application Setup & Dependencies
# --------------------------------------------------------------------------
class AppConfig(Settings):
    ENVIRONMENT: str = "develop"
    MONGODB_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "backbone_app"
    REDIS_URL: str = "redis://localhost:6380/0"
    CACHE_ENABLED: bool = True

config = AppConfig()

# App Definition
app = FastAPI(title="Modular Backbone Framework")

# --------------------------------------------------------------------------
# Custom Model Event Handlers (Decoupled)
# --------------------------------------------------------------------------
from backbone import logger

async def process_new_note_task(note_id: str):
    """
    Simulation of a heavy background task (async).
    """
    logger.info(f"⏳ [Background-Async] Started processing for Note: {note_id}")
    await asyncio.sleep(3)
    logger.info(f"✅ [Background-Async] Finished processing for Note: {note_id}")

def sync_log_process(message: str):
    """
    Example of a synchronous background task.
    """
    import time
    logger.info(f"⏳ [Background-Sync] Processing log: {message}")
    time.sleep(1) # Simulate sync work
    logger.info(f"✅ [Background-Sync] Finished log: {message}")

async def note_create_notifier(instance: NoteSchema, **kwargs):
    logger.info(f"📣 [Signal] New Note Detected: {instance.title}")
    
    # Using the Simplified background_task syntax
    await background_task(process_new_note_task, note_id=str(instance.id))
    
    # Also launching a sync task
    await background_task(sync_log_process, f"Note {instance.title} created")
    
    logger.info(f"🚀 [Queue] Tasks enqueued via background_task()")

async def note_update_notifier(instance: NoteSchema, changed_fields: dict = None, **kwargs):
    if changed_fields:
        logger.info(f"📣 SIGNAL RECIPIED: Note updated - {instance.id}. Changes: {changed_fields}")

async def note_field_change_handler(instance: NoteSchema, changed_fields: dict = None, **kwargs):
    if changed_fields and "is_pinned" in changed_fields:
        old, new = changed_fields["is_pinned"]
        logger.warning(f"📌 PIN STATUS CHANGED for note {instance.id}: {old} -> {new}")

async def note_delete_notifier(instance: NoteSchema, **kwargs):
    logger.warning(f"📣 SIGNAL RECIPIED: Note was deleted - {instance.id}")

# Register Handlers with Signals
signals.post_create.connect(NoteSchema, note_create_notifier)
signals.post_update.connect(NoteSchema, note_update_notifier)
signals.on_field_change.connect(NoteSchema, note_field_change_handler)
signals.post_delete.connect(NoteSchema, note_delete_notifier)

# --------------------------------------------------------------------------
# Backbone Global Configuration
# --------------------------------------------------------------------------
BackboneConfig(
    app=app, 
    config=config, 
    document_models=[BlogSchema, NoteSchema, PlaylistSchema]
)

# 1. Notes (Demonstrating Granular Control)
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
app.include_router(note_list.router)
app.include_router(note_create.router)
app.include_router(note_retrieve.router)
app.include_router(note_update.router)
app.include_router(note_delete.router)
app.include_router(playlist_crud.router)

@app.get("/")
async def root():
    return {"message": "Backbone Framework: MongoDB-Only Edition"}
