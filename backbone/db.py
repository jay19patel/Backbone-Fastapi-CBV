from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from pymongo.errors import DuplicateKeyError

from .core.models import Store


class BackboneDB:
    """
    Singleton key/value storage backed by one MongoDB document.
    Usage:
        await backbone.db.set("api_key", "value")
        value = await backbone.db.get("api_key")
    """

    def __init__(self, scope: str = "global") -> None:
        self.scope = scope

    @staticmethod
    def _validate_key(key: str) -> None:
        if not key or not key.strip():
            raise ValueError("Store key cannot be empty.")
        if "." in key or key.startswith("$"):
            raise ValueError("Store key cannot contain '.' and cannot start with '$'.")

    async def _ensure_store(self) -> Store:
        store = await Store.find_one(Store.scope == self.scope)
        if store:
            return store

        now = datetime.now(timezone.utc)
        try:
            store = Store(scope=self.scope, values={}, created_at=now, updated_at=now)
            await store.insert()
            return store
        except DuplicateKeyError:
            # Another request created it concurrently.
            pass

        store = await Store.find_one(Store.scope == self.scope)
        if not store:
            raise RuntimeError("Failed to initialize Backbone singleton store.")
        return store

    async def get(self, key: str, default: Any = None) -> Any:
        self._validate_key(key)
        store = await self._ensure_store()
        return store.values.get(key, default)

    async def set(self, key: str, value: Any) -> Any:
        self._validate_key(key)
        await self._ensure_store()
        now = datetime.now(timezone.utc)
        collection = Store.get_pymongo_collection()
        await collection.update_one(
            {"scope": self.scope},
            {"$set": {f"values.{key}": value, "updated_at": now}},
            upsert=False,
        )
        return value

    async def update(self, mapping: Dict[str, Any]) -> Dict[str, Any]:
        if not mapping:
            return {}
        for key in mapping.keys():
            self._validate_key(key)

        await self._ensure_store()
        now = datetime.now(timezone.utc)
        set_payload: Dict[str, Any] = {"updated_at": now}
        for key, value in mapping.items():
            set_payload[f"values.{key}"] = value

        collection = Store.get_pymongo_collection()
        await collection.update_one(
            {"scope": self.scope},
            {"$set": set_payload},
            upsert=False,
        )
        return mapping

    async def delete(self, key: str) -> bool:
        self._validate_key(key)
        await self._ensure_store()
        now = datetime.now(timezone.utc)
        collection = Store.get_pymongo_collection()
        result = await collection.update_one(
            {"scope": self.scope},
            {"$unset": {f"values.{key}": ""}, "$set": {"updated_at": now}},
            upsert=False,
        )
        return result.modified_count > 0

    async def all(self) -> Dict[str, Any]:
        store = await self._ensure_store()
        return dict(store.values or {})


db = BackboneDB()
