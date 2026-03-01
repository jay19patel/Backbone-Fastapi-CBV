from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from typing import List, Type, Any, Union
from beanie import Document
import pymongo.errors
import logging

logger = logging.getLogger("backbone")

async def init_database(client: AsyncIOMotorClient, database_name: str, document_models: List[Union[Type[Document], str, Any]]):
    """
    Initialize Beanie with the given motor client and document models.
    """
    try:
        await init_beanie(
            database=client[database_name],
            document_models=document_models
        )
    except pymongo.errors.DuplicateKeyError as e:
        logger.warning(
            f"Database Initialization Warning: An index build failed due to existing duplicate keys. "
            f"The application will continue starting, but you should resolve these duplicates. Details: {e}"
        )
