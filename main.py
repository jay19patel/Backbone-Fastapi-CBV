from fastapi import FastAPI
from contextlib import asynccontextmanager
from motor.motor_asyncio import AsyncIOMotorClient
from backbone import (
    AuthRouter, IsOwner, GenericCrud, MongoRepository
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

# Initialize Resources (Views)
# 1. Auth
auth = AuthRouter(db_instance=database)

# 2. Blog
blog = GenericCrud(
    repository=MongoRepository(database),
    schema=BlogSchema,
    prefix="/blogs",
    tags=["Blogs"],
    list_fields=["title", "author_id"],
    filter_fields=["tags"],
    permission_classes=[IsOwner]
)

# 3. Notes
note = GenericCrud(
    repository=MongoRepository(database),
    schema=NoteSchema,
    prefix="/notes",
    tags=["Notes"],
    list_fields=["title", "is_pinned"],
    search_fields=["title", "body"],
    permission_classes=[IsOwner]
)

# 4. Playlists
playlist = GenericCrud(
    repository=MongoRepository(database),
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
    
    # Sync Indexes
    await auth.sync_indexes()
    await blog.sync_indexes()
    await note.sync_indexes()
    await playlist.sync_indexes()
    
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
app.include_router(auth.router)
app.include_router(blog.router)
app.include_router(note.router)
app.include_router(playlist.router)

@app.get("/")
def home():
    return {
        "status": "online", 
        "version": "v10 (Explicit Main)",
        "docs": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)
