from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    secret_key: str = Field(
        default="your_super_secret_key_here_at_least_32_chars",
        alias="SECRET_KEY",
    )
    algorithm: str = Field(default="HS256", alias="ALGORITHM")
    access_token_expire_minutes: int = Field(default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=7, alias="REFRESH_TOKEN_EXPIRE_DAYS")
    ENVIRONMENT: str = "develop"
    
    # Defaults for DB
    MONGODB_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "backbone_app"
    SITE_NAME: str = "Soul Craft Studio"
    FRONTEND_VERIFY_URL: str = "http://localhost:3000/verify-email"
    FRONTEND_VERIFY_SUCCESS_URL: str = "http://localhost:3000/verify-success"
    FRONTEND_VERIFY_ERROR_URL: str = "http://localhost:3000/verify-error"


    # Default Admin Credentials
    ADMIN_EMAIL: str = "admin@gmail.com"
    ADMIN_PASSWORD: str = "admin"

    # Cache Settings
    CACHE_ENABLED: bool = False
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL: int = 300
    WORKER_COUNT: int = 2
    INTERNAL_WORKER_COUNT: int = 2

    # Rate Limiting Settings
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT_CALLS: int = 100
    RATE_LIMIT_DEFAULT_WINDOW: int = 60 # seconds

    # CORS Settings
    CORS_ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Google Auth Settings
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # Cloudinary Settings
    CLOUDINARY_URL: str = ""
    
    # Email Settings
    EMAIL_ENABLED: bool = True
    EMAIL_HOST: str = "smtp.gmail.com"
    EMAIL_PORT: int = 587
    EMAIL_USE_TLS: bool = True
    EMAIL_USE_SSL: bool = False
    EMAIL_USERNAME: str = ""
    EMAIL_PASSWORD: str = ""
    EMAIL_FROM_EMAIL: str = "no-reply@example.com"
    EMAIL_FROM_NAME: str = "Backbone"
    EMAIL_TIMEOUT_SECONDS: int = 30



    @property
    def cors_origins_list(self) -> list:
        return [origin.strip() for origin in self.CORS_ALLOWED_ORIGINS.split(",") if origin.strip()]

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "develop"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def cookie_settings(self) -> dict:
        if self.is_development:
            return {"secure": False, "httponly": True, "samesite": "lax"}
        return {"secure": True, "httponly": True, "samesite": "strict"}

    def validate_runtime(self) -> None:
        if self.is_production and self.secret_key == "your_super_secret_key_here_at_least_32_chars":
            raise ValueError("SECRET_KEY must be explicitly configured in production.")

settings = Settings()
