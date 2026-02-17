from datetime import datetime
from typing import Optional
from beanie import Document, PydanticObjectId
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

    class Settings:
        is_root = True  # specific to Beanie inheritance

class User(AuditDocument):
    email: EmailStr
    full_name: str
    is_active: bool = True
    is_staff: bool = False
    hashed_password: str

    class Settings:
        name = "users"
        indexes = [
            IndexModel([("email", ASCENDING)], unique=True)
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
