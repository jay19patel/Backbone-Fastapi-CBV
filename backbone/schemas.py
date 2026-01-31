from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import Optional, List, Any, Generic, TypeVar
from datetime import datetime
from bson import ObjectId

T = TypeVar('T')

from typing import Annotated, Any
from pydantic import GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema

class PyObjectId(ObjectId):
    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: Any
    ) -> core_schema.CoreSchema:
        return core_schema.json_or_python_schema(
            json_schema=core_schema.str_schema(),
            python_schema=core_schema.union_schema([
                core_schema.is_instance_schema(ObjectId),
                core_schema.str_schema(),
            ]),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: str(x)
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, _core_schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return handler(core_schema.str_schema())

class AuditSchema(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str}
    )

class UserSchema(AuditSchema):
    email: EmailStr
    full_name: str
    is_active: bool = True
    is_staff: bool = False
    hashed_password: str

    class Meta:
        collection_name = "users"
        indexes = [
            {"fields": ["email"], "unique": True}
        ]

class UserOut(BaseModel):
    """
    User representation for public/response usage.
    """
    id: str = Field(alias="_id")
    email: EmailStr
    full_name: str
    is_active: bool
    is_staff: bool

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True
    )

class PaginatedResponse(BaseModel, Generic[T]):
    total: int
    page: int
    page_size: int
    total_pages: int
    results: List[T]

class SessionSchema(AuditSchema):
    user_id: str
    refresh_token: str
    is_active: bool = True
    expires_at: datetime
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None

    class Meta:
        collection_name = "sessions"
        indexes = [
            {"fields": ["user_id"], "unique": False},
            {"fields": ["refresh_token"], "unique": True}
        ]

class LoginSchema(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
