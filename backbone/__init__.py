from .generic import (
    BaseGenericView,
    GenericList,
    GenericCreate,
    GenericRetrieve,
    GenericUpdate,
    GenericDelete,
    GenericCrud,
    REGISTERED_COMPONENTS
)
from .schemas import AuditSchema, UserSchema, UserOut, PaginatedResponse, PyObjectId, SessionSchema, TokenResponse
from .db import db, get_db
from .permissions import BasePermission, AllowAny, IsAuthenticated, IsAdminUser, IsOwner, PermissionDependency
from .repositories import MongoRepository
from .interface import IDatabaseRepository
from .auth import AuthRouter
from .utils import PasswordManager, TokenManager
from .dependencies import get_current_user, get_optional_user

__all__ = [
    "BaseGenericView",
    "GenericList",
    "GenericCreate",
    "GenericRetrieve",
    "GenericUpdate",
    "GenericDelete",
    "GenericCrud",
    "AuditSchema",
    "UserSchema",
    "UserOut",
    "PaginatedResponse",
    "PyObjectId",
    "SessionSchema",
    "TokenResponse",
    "db",
    "get_db",
    "BasePermission",
    "AllowAny",
    "IsAuthenticated",
    "IsAdminUser",
    "IsOwner",
    "PermissionDependency",
    "AuthRouter",
    "PasswordManager",
    "TokenManager",
    "get_current_user",
    "get_optional_user",
    "IDatabaseRepository",
    "MongoRepository"
]
