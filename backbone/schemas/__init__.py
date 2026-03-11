from pydantic import BaseModel, Field, EmailStr, ConfigDict
from datetime import datetime
from typing import Optional, List, Any, Generic, TypeVar, Union
from bson import ObjectId
from pydantic import field_serializer
from beanie import Link

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
    headline: Optional[str] = None
    bio: Optional[str] = None
    description: Optional[str] = None # For frontend compatibility (aliased to bio)
    profile_image: Optional[Any] = None
    created_at: Optional[datetime] = None
    is_google_account: bool = False

    @field_serializer('profile_image')
    def serialize_profile_image(self, profile_image: Any):
        if not profile_image:
            return None
        
        from ..core.url_utils import get_media_url
        
        # If it's a Beanie Link (not fetched)
        if hasattr(profile_image, "to_ref"):
             return None
             
        path = None
        # If it's the actual Attachment object/dict
        if isinstance(profile_image, dict):
            path = profile_image.get("file_path")
        elif hasattr(profile_image, "file_path"):
            path = profile_image.file_path
        else:
            path = str(profile_image)

        if path and path.startswith("/media/"):
            return get_media_url(path)
        return path

    from pydantic import model_validator
    @model_validator(mode='after')
    def set_description(self) -> 'UserOut':
        if not self.description:
            self.description = self.bio
        return self

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str}
    )

class UserUpdate(BaseModel):
    """
    Schema for updating user profile fields.
    """
    full_name: Optional[str] = None
    headline: Optional[str] = None
    bio: Optional[str] = None
    profile_image: Optional[str] = None

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

class GoogleLoginSchema(BaseModel):
    code: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class UserResponse(BaseModel):
    id: str = Field(default_factory=lambda: str(ObjectId()), alias="_id")
    email: str
    full_name: str

class RegisterSchema(BaseModel):
    email: EmailStr
    password: str
    full_name: str
