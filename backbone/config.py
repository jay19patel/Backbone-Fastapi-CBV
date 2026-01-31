from typing import Any, Type
from fastapi import FastAPI
from .interface import IDatabaseRepository
from .repositories import MongoRepository
import backbone.context as context
from pydantic_settings import BaseSettings
from contextlib import asynccontextmanager

class Settings(BaseSettings):
    secret_key: str = "your_super_secret_key_here"  # Override in production
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

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
        database: Any,
        mongo_client: Any, 
        repository_class: Type[IDatabaseRepository] = MongoRepository
    ):
        self.app = app
        self.config = config
        self.mongo_client = mongo_client
        
        # Set Global Context
        context.DATABASE = database
        context.REPOSITORY_CLASS = repository_class
        
        # Attach Lifespan
        self.app.router.lifespan_context = self.lifespan

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        # Startup
        print("System: Connecting to Database...")
        
        # Automated Index Syncing
        print(f"System: Syncing indexes for {len(context.REGISTERED_COMPONENTS)} components...")
        for component in context.REGISTERED_COMPONENTS:
            if hasattr(component, "sync_indexes"):
                await component.sync_indexes()
        
        print("System: Online and Ready.")
        
        yield
        
        # Shutdown
        print("System: Shutting down...")
        self.mongo_client.close()
