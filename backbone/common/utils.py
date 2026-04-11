import jwt
import logging
import os
import asyncio
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from typing import Optional, Any
from typing import Optional, Any

# ── Auth Utilities ──────────────────────────────────────────────────────────

class PasswordManager:
    """Handles password hashing and verification."""
    pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
    @classmethod
    def hash_password(cls, password: str) -> str: return cls.pwd_context.hash(password)
    @classmethod
    def verify_password(cls, plain, hashed) -> bool: return cls.pwd_context.verify(plain, hashed)

class TokenManager:
    """Handles JWT token creation and decoding."""
    @staticmethod
    def create_access_token(data: dict, sid: str, expires_delta: Optional[timedelta] = None) -> str:
        from ..core.config import BackboneConfig
        settings = BackboneConfig.get_instance().config
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
        to_encode.update({"exp": expire, "type": "access", "sid": sid})
        return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)

    @staticmethod
    def create_refresh_token(data: dict, sid: str) -> str:
        from ..core.config import BackboneConfig
        settings = BackboneConfig.get_instance().config
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
        to_encode.update({"exp": expire, "type": "refresh", "sid": sid})
        return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)

    @staticmethod
    def decode_token(token: str) -> Optional[dict]:
        from ..core.config import BackboneConfig
        settings = BackboneConfig.get_instance().config
        try: return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        except Exception: return None

    @staticmethod
    def verify_token(token: str) -> Optional[dict]:
        """Alias for decode_token."""
        return TokenManager.decode_token(token)


# ── Logging Utilities ───────────────────────────────────────────────────────

class DatabaseLoggingHandler(logging.Handler):
    """Custom logging handler that stores logs in MongoDB."""
    def emit(self, record):
        try:
            log_data = {
                "level": record.levelname,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
                "created_at": datetime.fromtimestamp(record.created, tz=timezone.utc),
            }
            if record.exc_info: log_data["exception"] = logging.formatException(record.exc_info)
            loop = asyncio.get_event_loop()
            if loop.is_running(): loop.create_task(self._save_to_db(log_data))
        except Exception: pass

    async def _save_to_db(self, log_data: dict):
        try:
            from ..core.models import LogEntry
            await LogEntry(**log_data).insert()
        except: pass

def setup_logger(name: str, log_file: str = "app.log", level=logging.INFO):
    """Configures a logger with Console and MongoDB handlers."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if logger.handlers: return logger
    
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(console)

    if log_file:
        try:
            os.makedirs("logs", exist_ok=True)
            file_handler = logging.FileHandler(os.path.join("logs", log_file))
            file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            logger.addHandler(file_handler)
        except: pass

    logger.addHandler(DatabaseLoggingHandler())
    return logger

logger = setup_logger("backbone_app")

from functools import wraps
import traceback

def log_exceptions(func):
    """
    Decorator to automatically log exceptions to the database.
    Use this on API routes or critical background tasks.
    """
    if asyncio.iscoroutinefunction(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Exception in {func.__name__}: {str(e)}", exc_info=True)
                raise e
        return async_wrapper
    else:
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Exception in {func.__name__}: {str(e)}", exc_info=True)
                raise e
        return sync_wrapper
