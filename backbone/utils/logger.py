import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional
import asyncio

class DatabaseLoggingHandler(logging.Handler):
    """
    Custom logging handler that asynchronously stores logs in MongoDB.
    """
    def __init__(self, level=logging.NOTSET):
        super().__init__(level)

    def emit(self, record):
        try:
            # Create the log entry dictionary
            log_data = {
                "level": record.levelname,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
                "created_at": datetime.fromtimestamp(record.created),
            }
            
            if record.exc_info:
                log_data["exception"] = logging.formatException(record.exc_info)
            
            if hasattr(record, "extra_info"):
                log_data["extra"] = record.extra_info

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._save_to_db(log_data))
            except RuntimeError:
                pass
        except Exception:
            self.handleError(record)

    async def _save_to_db(self, log_data: dict):
        try:
            from ..core.models import LogEntry
            await LogEntry(**log_data).insert()
        except Exception as e:
            # print(f"Failed to save log to DB: {e}")
            pass

def setup_logger(name: str, log_file: str = "app.log", level=logging.INFO):
    """
    Configures a logger with File, Console, and MongoDB handlers.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    # Console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(console_handler)

    # File
    if log_file:
        os.makedirs("logs", exist_ok=True)
        file_path = os.path.join("logs", log_file)
        file_handler = logging.FileHandler(file_path)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
        ))
        logger.addHandler(file_handler)

    # MongoDB
    db_handler = DatabaseLoggingHandler()
    logger.addHandler(db_handler)

    return logger

logger = setup_logger("backbone_app")
