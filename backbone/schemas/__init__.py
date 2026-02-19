from pydantic import BaseModel, Field, EmailStr, ConfigDict
from datetime import datetime
from typing import Optional, List, Any, Generic, TypeVar, Union
from bson import ObjectId

T = TypeVar('T')

from typing import Annotated, Any
from pydantic import GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema

from beanie import PydanticObjectId

# Pydantic v2 Serialization helper for ObjectIds
from pydantic import PlainSerializer
from typing_extensions import Annotated

SerializableObjectId = Annotated[
    Union[PydanticObjectId, ObjectId, str],
    PlainSerializer(lambda x: str(x), return_type=str),
]

class UserOut(BaseModel):
    """
    User representation for public/response usage.
    """
    id: Optional[Union[PydanticObjectId, int, str]] = Field(alias="_id", default=None)
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

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True
    )

class LoginSchema(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RegisterSchema(BaseModel):
    email: EmailStr
    username: str
    password: str
    full_name: str
