import asyncio
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from functools import wraps

import jwt
from passlib.context import CryptContext

# ── Auth Utilities ──────────────────────────────────────────────────────────


class PasswordManager:
    """Handles password hashing and verification."""

    pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

    @classmethod
    def hash_password(cls, password: str) -> str:
        return cls.pwd_context.hash(password)

    @classmethod
    def verify_password(cls, plain, hashed) -> bool:
        return cls.pwd_context.verify(plain, hashed)


class TokenManager:
    """Handles JWT token creation and decoding."""

    @staticmethod
    def create_access_token(data: dict, sid: str, expires_delta: timedelta | None = None) -> str:
        from ..core.config import BackboneConfig

        settings = BackboneConfig.get_instance().config
        to_encode = data.copy()
        expire = datetime.now(UTC) + (
            expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
        )
        to_encode.update({"exp": expire, "type": "access", "sid": sid})
        return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)

    @staticmethod
    def create_refresh_token(data: dict, sid: str) -> str:
        from ..core.config import BackboneConfig

        settings = BackboneConfig.get_instance().config
        to_encode = data.copy()
        expire = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
        to_encode.update({"exp": expire, "type": "refresh", "sid": sid})
        return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)

    @staticmethod
    def create_action_token(data: dict, action: str, expires_delta: timedelta | None = None) -> str:
        from ..core.config import BackboneConfig

        settings = BackboneConfig.get_instance().config
        to_encode = data.copy()
        expire = datetime.now(UTC) + (expires_delta or timedelta(hours=24))
        to_encode.update({"exp": expire, "action": action})
        return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)

    @staticmethod
    def decode_token(token: str) -> dict | None:
        from ..core.config import BackboneConfig

        settings = BackboneConfig.get_instance().config
        try:
            return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        except Exception:
            return None

    @staticmethod
    def verify_token(token: str) -> dict | None:
        """Alias for decode_token."""
        return TokenManager.decode_token(token)


# ── Logging Utilities ───────────────────────────────────────────────────────


class DatabaseLoggingHandler(logging.Handler):
    """Custom logging handler that stores logs in MongoDB.

    Failures are swallowed intentionally — a logging handler must never raise,
    as that would break the logging framework itself. We print to stderr instead
    so failures remain visible without disrupting the app.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            log_data = {
                "level": record.levelname,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
                "created_at": datetime.fromtimestamp(record.created, tz=UTC),
            }
            if record.exc_info:
                log_data["exception"] = logging.Formatter().formatException(record.exc_info)
            # Use get_running_loop() — safe in async context only.
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._save_to_db(log_data))
            except RuntimeError:
                # No running loop (e.g. during startup scripts) — skip DB log.
                pass
        except Exception as exc:  # noqa: BLE001
            # Must not raise — print to stderr as last resort.
            print(f"[DatabaseLoggingHandler] emit error: {exc}", file=sys.stderr)

    async def _save_to_db(self, log_data: dict) -> None:
        try:
            from ..core.models import LogEntry

            await LogEntry(**log_data).insert()
        except Exception as exc:  # noqa: BLE001
            print(f"[DatabaseLoggingHandler] DB write failed: {exc}", file=sys.stderr)


def setup_logger(name: str, log_file: str = "app.log", level: int = logging.INFO) -> logging.Logger:
    """Configure a logger with Console, optional File, and MongoDB handlers."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if logger.handlers:
        return logger

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(console)

    if log_file:
        try:
            os.makedirs("logs", exist_ok=True)
            file_handler = logging.FileHandler(os.path.join("logs", log_file))
            file_handler.setFormatter(
                logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            )
            logger.addHandler(file_handler)
        except OSError as exc:
            print(f"[setup_logger] Could not create file log handler: {exc}", file=sys.stderr)

    logger.addHandler(DatabaseLoggingHandler())
    return logger


logger = setup_logger("backbone_app")


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
