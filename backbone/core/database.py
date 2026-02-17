from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from typing import List, Type, Any, Union
from beanie import Document

async def init_database(client: AsyncIOMotorClient, database_name: str, document_models: List[Union[Type[Document], str, Any]]):
    """
    Initialize Beanie with the given motor client and document models.
    """
    await init_beanie(
        database=client[database_name],
        document_models=document_models
    )
