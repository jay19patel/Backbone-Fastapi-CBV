from datetime import datetime
from typing import Optional, List, Dict, Any, Type
from .signals import signals
from beanie import Document, PydanticObjectId, Insert, Replace, Save, Delete, Update, before_event, after_event
from pydantic import Field, EmailStr
from pymongo import IndexModel, ASCENDING, DESCENDING

class AuditDocument(Document):
    """
    Base Document with audit fields (created_at, updated_at, soft delete).
    """
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self._initial_state = self.model_dump()
        except:
            self._initial_state = {}

    def has_changed(self, field: str) -> bool:
        """Check if a specific field has changed since initialization."""
        return self._initial_state.get(field) != getattr(self, field)

    @after_event(Insert)
    async def _emit_post_create(self):
        await signals.post_create.emit(self)

    @before_event(Replace, Save, Update)
    async def before_update_state(self):
        pass

    @after_event(Replace, Save, Update)
    async def _emit_post_update(self):
        # Detect field changes
        current_state = self.model_dump()
        changed_fields = {}
        
        for field, value in current_state.items():
            if field in self._initial_state and self._initial_state[field] != value:
                changed_fields[field] = (self._initial_state[field], value)
        
        if changed_fields:
            await signals.on_field_change.emit(self, changed_fields=changed_fields)
        
        await signals.post_update.emit(self, changed_fields=changed_fields)

        # Update initial state after replacement/save
        self._initial_state = current_state

    @after_event(Delete)
    async def _emit_post_delete(self):
        await signals.post_delete.emit(self)

    class Settings:
        pass

class EventDocument(AuditDocument):
    """
    Base Document that supports event hooks and state tracking.
    Now inherits hooks from AuditDocument.
    """
    class Settings:
        pass

class User(AuditDocument):
    username: str
    email: EmailStr
    full_name: str
    is_active: bool = True
    is_staff: bool = False
    is_superuser: bool = False
    hashed_password: str

    class Settings:
        name = "users"
        indexes = [
            IndexModel([("email", ASCENDING)], unique=True),
            IndexModel([("username", ASCENDING)], unique=True)
        ]

class Session(AuditDocument):
    user_id: str
    refresh_token: str
    is_active: bool = True
    expires_at: datetime
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None

    class Settings:
        name = "sessions"
        indexes = [
            IndexModel([("user_id", ASCENDING)]),
            IndexModel([("refresh_token", ASCENDING)], unique=True)
        ]

class LogEntry(AuditDocument):
    level: str
    message: str
    module: Optional[str] = None
    function: Optional[str] = None
    line: Optional[int] = None
    exception: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None

    class Settings:
        name = "logs"
        indexes = [
            IndexModel([("level", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)])
        ]
