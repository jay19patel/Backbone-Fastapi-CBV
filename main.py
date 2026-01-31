from fastapi import FastAPI
from contextlib import asynccontextmanager
from motor.motor_asyncio import AsyncIOMotorClient
from backbone import (
    AuthRouter, IsOwner, GenericCrud, MongoRepository, REGISTERED_COMPONENTS
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

# Initialize Resources
# Views automatically register themselves to REGISTERED_COMPONENTS

# 1. Auth
auth = AuthRouter(db_instance=database)

# 2. Blog
blog = GenericCrud(
    database=database, # Simplified: Pass database directly
    schema=BlogSchema,
    prefix="/blogs",
    tags=["Blogs"],
    list_fields=["title", "author_id"],
    filter_fields=["tags"],
    permission_classes=[IsOwner]
)

# 3. Notes
note = GenericCrud(
    database=database,
    schema=NoteSchema,
    prefix="/notes",
    tags=["Notes"],
    list_fields=["title", "is_pinned"],
    search_fields=["title", "body"],
    permission_classes=[IsOwner]
)

# 4. Playlists
playlist = GenericCrud(
    database=database,
    schema=PlaylistSchema,
    prefix="/playlists",
    tags=["Playlists"],
    list_fields=["name", "is_public"],
    permission_classes=[IsOwner]
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("System: Connecting to Database...")
    
    # Automated Index Syncing
    print(f"System: Syncing indexes for {len(REGISTERED_COMPONENTS)} components...")
    for component in REGISTERED_COMPONENTS:
        if hasattr(component, "sync_indexes"):
            await component.sync_indexes()
    
    print("System: Online and Ready.")
    
    yield
    
    # Shutdown
    print("System: Shutting down...")
    client.close()

# App Definition
app = FastAPI(
    title="Modular Backbone Framework",
    lifespan=lifespan
)

# Register Routers
# We can also automate this if we wanted, but explicit is better for control
app.include_router(auth.router)
app.include_router(blog.router)
app.include_router(note.router)
app.include_router(playlist.router)

@app.get("/")
def home():
    return {
        "status": "online", 
        "version": "v11 (Automated & Simplified)",
        "docs": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8006, reload=True)
