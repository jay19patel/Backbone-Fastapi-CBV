from pydantic_settings import BaseSettings

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
    CACHE_TTL: int = 300
    WORKER_COUNT: int = 1

    # Rate Limiting Settings
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT_CALLS: int = 100
    RATE_LIMIT_DEFAULT_WINDOW: int = 60 # seconds
    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "develop"

    @property
    def cookie_settings(self) -> dict:
        if self.is_development:
            return {"secure": False, "httponly": True, "samesite": "lax"}
        return {"secure": True, "httponly": True, "samesite": "strict"}

settings = Settings()
