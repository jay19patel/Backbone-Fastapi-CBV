from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import Optional, List, Any, Generic, TypeVar
from datetime import datetime
from bson import ObjectId

T = TypeVar('T')

from typing import Annotated, Any
from pydantic import GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema

from beanie import PydanticObjectId

class UserOut(BaseModel):
    """
    User representation for public/response usage.
    """
    id: Optional[PydanticObjectId] = Field(alias="_id", default=None)
    email: EmailStr
    full_name: str
    is_active: bool
    is_staff: bool

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str}
    )

class PaginatedResponse(BaseModel, Generic[T]):
    total: int
    page: int
    page_size: int
    total_pages: int
    results: List[T]

class LoginSchema(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RegisterSchema(BaseModel):
    email: EmailStr
    password: str
    full_name: str
