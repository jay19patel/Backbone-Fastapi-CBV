from typing import List, Any, Optional, Type
from fastapi import FastAPI
from .repository import BeanieRepository
from .models import User, Session, LogEntry
from .database import init_database
from pydantic_settings import BaseSettings
from contextlib import asynccontextmanager

from motor.motor_asyncio import AsyncIOMotorClient
import redis.asyncio as redis

class Settings(BaseSettings):
    secret_key: str = "your_super_secret_key_here"  # Override in production
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    ENVIRONMENT: str = "production"
    
    # Defaults for DB
    MONGODB_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "backbone_app"

    # Cache Settings
    CACHE_ENABLED: bool = False
    REDIS_URL: str = "redis://localhost:6379/0"

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "develop"

    @property
    def cookie_settings(self) -> dict:
        if self.is_development:
            return {"secure": False, "httponly": True, "samesite": "lax"}
        return {"secure": True, "httponly": True, "samesite": "strict"}

settings = Settings()

class BackboneConfig:
    """
    Configuration helper for Backbone.
    Sets up the global database context and manages application lifespan.
    """
    def __init__(
        self, 
        app: FastAPI, 
        config: Any, 
        repository_class: Type[BeanieRepository] = BeanieRepository,
        document_models: List[Any] = None
    ):
        self.app = app
        self.config = config
        self.document_models = document_models or [User, Session, LogEntry]
        
        # Determine Default Repository
        self.repository_class = repository_class
        
        # MongoDB Client
        self.mongo_client = AsyncIOMotorClient(self.config.MONGODB_URL)
        self.database = self.mongo_client[self.config.DATABASE_NAME]

        # Redis Client (Optional)
        self.redis_client = None
        if getattr(self.config, "CACHE_ENABLED", False):
            self.redis_client = redis.from_url(self.config.REDIS_URL, decode_responses=True)

        # Attach to app state for access in views
        self.app.state.backbone_config = self
        
        # Attach Lifespan
        self.app.router.lifespan_context = self.lifespan

    @property
    def is_development(self) -> bool:
        return getattr(self.config, "ENVIRONMENT", "production") == "develop"

    @property
    def cookie_settings(self) -> dict:
        if self.is_development:
            return {"secure": False, "httponly": True, "samesite": "lax"}
        return {"secure": True, "httponly": True, "samesite": "strict"}

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        # Startup
        print("System: Connecting to MongoDB (Beanie)...")
        await init_database(
            client=self.mongo_client,
            database_name=self.config.DATABASE_NAME,
            document_models=[m for m in self.document_models if hasattr(m, "Settings")]
        )
        print("System: Beanie Initialized.")

        print("System: Online and Ready.")
        
        yield
        
        # Shutdown
        print("System: Shutting down...")
