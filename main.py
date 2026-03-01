import asyncio
from fastapi import FastAPI, Request, Depends
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
from schema import BlogSchema, BlogCategory
from backbone.core.models import User, Session, LogEntry
from backbone.core.rate_limit import RateLimit

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

# App Definition
app = FastAPI(title="Modular Backbone Framework")

# --------------------------------------------------------------------------
# Backbone Global Configuration
# --------------------------------------------------------------------------
BackboneConfig(
    app=app, 
    config=config, 
    document_models=[BlogSchema, BlogCategory]
)

# 4. Blog Categories (Simple CRUD)
blog_category_crud = GenericCrud(
    schema=BlogCategory,
    prefix="/blog-categories",
    tags=["Blog Categories"],
    search_fields=["name"],
    # permission_classes=[IsOwner] 
)

# 5. Blogs (With Optimization & Population)
blog_crud = GenericCrud(
    schema=BlogSchema,
    prefix="/blogs",
    tags=["Blogs"],
    search_fields=["title", "content"],
    list_fields=["title", "categories", "author", "created_by", "created_at"], # Show 'author' (linked), manual fields
    fetch_links=True,
    permission_classes=[AllowAny],
    rate_limit=Depends(RateLimit(calls=50, window=60))
)



async def long_process_task():
    print("Starting custom long process...")
    await asyncio.sleep(30)
    print("Completed custom long process.")

@app.post("/custom-long-process", tags=["Background Tasks"])
async def trigger_long_process():
    task_id = await background_task(long_process_task)
    return {"message": "Long process task enqueued", "task_id": str(task_id)}

# Register Routers
app.include_router(blog_category_crud.router)
app.include_router(blog_crud.router)

@app.get("/")
async def root():
    return {"message": "Backbone Framework: MongoDB-Only Edition"}
