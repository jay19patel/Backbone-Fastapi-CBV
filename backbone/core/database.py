import logging
from typing import Any

import pymongo.errors
from beanie import Document, init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger("backbone")


async def init_database(
    client: AsyncIOMotorClient,
    database_name: str,
    document_models: list[type[Document] | str | Any],
) -> None:
    """
    Initialize Beanie with the Motor async client.
    Beanie is pinned to 2.0.1 — Beanie 2.1+ expects PyMongo async instead of Motor.
    """
    try:
        await init_beanie(
            database=client[database_name],
            document_models=document_models,
        )
    except pymongo.errors.DuplicateKeyError as e:
        logger.warning(
            "Database Initialization Warning: An index build failed due to existing "
            "duplicate keys. The application will continue starting, but you should "
            "resolve these duplicates. Details: %s",
            e,
        )
