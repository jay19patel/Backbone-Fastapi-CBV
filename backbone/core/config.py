from typing import List, Any, Optional, Type
from fastapi import FastAPI
from .repository import BeanieRepository
from .database import init_database
from ..common.services import CacheService, TaskQueue, TaskWorker
from ..admin.router import router as admin_router
from ..admin.site import admin_site
from ..auth.router import AuthRouter
from motor.motor_asyncio import AsyncIOMotorClient
import redis.asyncio as redis
import asyncio
import logging
import os
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from .settings import Settings, settings

from contextlib import asynccontextmanager

logger = logging.getLogger("backbone.config")

class BackboneConfig:
    """
    Configuration helper for Backbone.
    Sets up the global database context and manages application lifespan.
    """
    _instance: Optional["BackboneConfig"] = None

    @classmethod
    def get_instance(cls) -> "BackboneConfig":
        """Get the current BackboneConfig instance."""
        if cls._instance is None:
            raise RuntimeError("BackboneConfig has not been initialized.")
        return cls._instance

    def __init__(
        self, 
        app: FastAPI, 
        config: Any, 
        repository_class: Type[BeanieRepository] = BeanieRepository,
        document_models: List[Any] = None
    ):
        self.app = app
        self.config = config
        if hasattr(self.config, "validate_runtime"):
            self.config.validate_runtime()
        
        # Default Core Models
        from .models import (
            User,
            Session,
            LogEntry,
            Task,
            Attachment,
            PasswordResetToken,
            Email,
            Store,
        )
        core_models = [
            User,
            Session,
            LogEntry,
            Task,
            Attachment,
            PasswordResetToken,
            Email,
            Store,
        ]
        
        # Ensures core models are loaded first to safely resolve Beanie links
        self.document_models = core_models.copy()
        if document_models:
            for model in document_models:
                if model not in self.document_models:
                    self.document_models.append(model)
        
        # Determine Default Repository
        self.repository_class = repository_class
        
        # MongoDB Client
        self.mongo_client = AsyncIOMotorClient(self.config.MONGODB_URL)
        self.database = self.mongo_client[self.config.DATABASE_NAME]

        # Cache Service
        from ..common.services import CacheService, cache
        self.redis_client = None
        self.cache_service = cache  # Use the global instance
        if getattr(self.config, "CACHE_ENABLED", False):
            self.redis_client = redis.from_url(self.config.REDIS_URL, decode_responses=True)
            self.cache_service.redis = self.redis_client
            self.cache_service.enabled = True

        # Task Queue
        self.task_queue = TaskQueue(self.redis_client)
        self.internal_task_queue = TaskQueue(self.redis_client, queue_name="backbone_internal_tasks")

        # Auth Router
        self.auth_router = AuthRouter(config=self.config, prefix="/api/auth")

        # Cloudinary Setup — SDK reads CLOUDINARY_URL from os.environ
        cloudinary_url = getattr(self.config, "CLOUDINARY_URL", "")
        if cloudinary_url:
            os.environ["CLOUDINARY_URL"] = cloudinary_url
            import cloudinary
            cloudinary.config()  # Auto-reads from os.environ

        # Store Class Instance
        BackboneConfig._instance = self

        # Attach to app state for access in views
        self.app.state.backbone_config = self
        
        # ----------------------------------------------------------------------
        # Middlewares (CORS & Base URL)
        # ----------------------------------------------------------------------
        self._setup_middlewares()
        
        # Attach Lifespan
        self.app.router.lifespan_context = self.lifespan

        # Include Admin Router
        self.app.include_router(admin_router)

        # Include Auth Router
        self.app.include_router(self.auth_router.router)
        
        
        # ----------------------------------------------------------------------
        # Media & Static Files Setup (only in development — serverless is read-only)
        # ----------------------------------------------------------------------
        if self.config.ENVIRONMENT != "production":
            self.media_path = Path("media")
            self.media_path.mkdir(parents=True, exist_ok=True)
            self.app.mount("/media", StaticFiles(directory=str(self.media_path)), name="media")
        
        self._register_exception_handlers()

        # Register Models with Admin Site
        # Register Models with Admin Site
        from .models import (
            User,
            Session,
            LogEntry,
            Task,
            Attachment,
            PasswordResetToken,
            Email,
            Store,
        )
        core_models_set = {
            User,
            Session,
            LogEntry,
            Task,
            Attachment,
            PasswordResetToken,
            Email,
            Store,
        }
        
        for model in self.document_models:
            category = "Core Models" if model in core_models_set else "Custom Models"
            admin_site.register(model, category=category)

    def _register_exception_handlers(self):
        from starlette.exceptions import HTTPException as StarletteHTTPException
        from fastapi.responses import JSONResponse
        from fastapi import Request
        import traceback
        from .models import LogEntry

        @self.app.exception_handler(StarletteHTTPException)
        async def http_exception_handler(request: Request, exc: StarletteHTTPException):
            level = "warning" if exc.status_code < 500 else "error"
            try:
                if exc.status_code >= 400:
                    await LogEntry(
                        level=level,
                        message=str(exc.detail),
                        extra={"status_code": exc.status_code, "url": str(request.url), "method": request.method},
                        module="http_exception_handler"
                    ).insert()
            except Exception as log_exc:
                logger.warning("Failed to log HTTP exception: %s", log_exc)
            
            headers = getattr(exc, "headers", None)
            if headers:
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=headers)
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

        @self.app.exception_handler(Exception)
        async def global_exception_handler(request: Request, exc: Exception):
            logger.exception("Unhandled application exception")
            try:
                await LogEntry(
                    level="error",
                    message=str(exc),
                    exception=traceback.format_exc(),
                    extra={"url": str(request.url), "method": request.method},
                    module="global_exception_handler"
                ).insert()
            except Exception as log_exc:
                logger.warning("Failed to log global exception: %s", log_exc)
            return JSONResponse({"detail": "Internal Server Error"}, status_code=500)

        from ..common.exceptions import BackboneException

        @self.app.exception_handler(BackboneException)
        async def backbone_exception_handler(request: Request, exc: BackboneException):
            """
            Handle custom Backbone exceptions and return structured JSON responses.
            """
            content = {
                "detail": exc.detail or exc.message,
                "error_code": exc.error_code or "UNKNOWN_ERROR"
            }
            # Log the error if it's a 500
            if exc.status_code >= 500:
                try:
                    await LogEntry(
                        level="error",
                        message=exc.message,
                        extra={"status_code": exc.status_code, "error_code": exc.error_code, "url": str(request.url)},
                        module="backbone_exception_handler"
                    ).insert()
                except Exception as log_exc:
                    logger.warning("Failed to log backbone exception: %s", log_exc)
            
            return JSONResponse(content=content, status_code=exc.status_code)

    def _setup_middlewares(self):
        from fastapi.middleware.cors import CORSMiddleware
        from .url_utils import DynamicBaseURLMiddleware
        
        # Extract CORS origins securely from global settings if available
        cors_origins_list = getattr(self.config, "cors_origins_list", [])
        if not cors_origins_list:
            # Fallback if property doesn't exist
            origins_str = getattr(self.config, "CORS_ALLOWED_ORIGINS", "")
            cors_origins_list = [origin.strip() for origin in origins_str.split(",") if origin.strip()]
            
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins_list or ["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        self.app.add_middleware(DynamicBaseURLMiddleware)

    @property
    def is_development(self) -> bool:
        return getattr(self.config, "ENVIRONMENT", "production") == "develop"

    @property
    def cookie_settings(self) -> dict:
        if hasattr(self.config, "cookie_settings"):
            return self.config.cookie_settings
        if self.is_development:
            return {"secure": False, "httponly": True, "samesite": "lax"}
        return {"secure": True, "httponly": True, "samesite": "strict"}

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        # Startup
        logger.info("Connecting to MongoDB and initializing Beanie")
        await init_database(
            client=self.mongo_client,
            database_name=self.config.DATABASE_NAME,
            document_models=[m for m in self.document_models if hasattr(m, "Settings")]
        )
        logger.info("Beanie initialized")

        # Start Task Workers
        if self.task_queue.enabled:
            worker_count = getattr(self.config, "WORKER_COUNT", 1)
            logger.info("Starting %s task worker(s)", worker_count)
            for i in range(worker_count):
                worker = TaskWorker(self.task_queue, worker_name=f"Worker-{i+1}")
                asyncio.create_task(worker.run())

            internal_worker_count = getattr(self.config, "INTERNAL_WORKER_COUNT", 1)
            logger.info("Starting %s internal task worker(s)", internal_worker_count)
            for i in range(internal_worker_count):
                worker = TaskWorker(self.internal_task_queue, worker_name=f"Internal-Worker-{i+1}")
                asyncio.create_task(worker.run())

        logger.info("Application online and ready")
        
        yield
        
        # Shutdown
        logger.info("Application shutting down")
