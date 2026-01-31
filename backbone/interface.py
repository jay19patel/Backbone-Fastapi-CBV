from pydantic import BaseModel
from typing import TypeVar, Generic, List, Optional, Any, Dict, Type
from abc import ABC, abstractmethod

T = TypeVar("T")

class IDatabaseRepository(ABC, Generic[T]):
    @abstractmethod
    def initialize(self, schema: Type[BaseModel]):
        """Initialize the repository with schema metadata (e.g., collection/table name)."""
        pass

    @abstractmethod
    async def get_all(
        self, 
        query: Dict[str, Any], 
        skip: int = 0, 
        limit: int = 10, 
        sort: Optional[Any] = None, 
        projection: Optional[Dict[str, int]] = None
    ) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def get_one(self, filter_query: Dict[str, Any], projection: Optional[Dict[str, int]] = None) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def update(self, filter_query: Dict[str, Any], data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def delete(self, filter_query: Dict[str, Any], soft: bool = True) -> bool:
        pass

    @abstractmethod
    async def count(self, query: Dict[str, Any]) -> int:
        pass