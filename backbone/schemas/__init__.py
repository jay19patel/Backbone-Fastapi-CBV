from datetime import datetime
from typing import Annotated, Any, TypeVar

from beanie import PydanticObjectId
from bson import ObjectId
from pydantic import BaseModel, ConfigDict, EmailStr, Field, PlainSerializer, field_serializer

T = TypeVar("T")

SerializableObjectId = Annotated[
    PydanticObjectId | ObjectId | str,
    PlainSerializer(lambda x: str(x), return_type=str),
]


class UserOut(BaseModel):
    """
    User representation for public/response usage.
    """

    id: PydanticObjectId | int | str | None = Field(alias="_id", default=None)
    email: EmailStr
    full_name: str
    is_active: bool
    is_staff: bool
    is_verified: bool = False
    headline: str | None = None

    bio: str | None = None
    description: str | None = None  # For frontend compatibility (aliased to bio)
    profile_image: Any | None = None
    created_at: datetime | None = None
    is_google_account: bool = False

    @field_serializer("profile_image")
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

    @model_validator(mode="after")
    def set_description(self) -> "UserOut":
        if not self.description:
            self.description = self.bio
        return self

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
    )


class UserUpdate(BaseModel):
    """
    Schema for updating user profile fields.
    """

    full_name: str | None = None
    headline: str | None = None
    bio: str | None = None
    profile_image: str | None = None


class PaginatedResponse[T](BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    results: list[T]

    model_config = ConfigDict(arbitrary_types_allowed=True, populate_by_name=True)


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
