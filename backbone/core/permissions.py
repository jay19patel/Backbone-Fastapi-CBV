from fastapi import Request, HTTPException, status, Depends
from typing import List, Optional, Type, Callable, Any
from ..schemas import UserOut
from .dependencies import get_optional_user, get_current_user
from .models import AuditDocument

class BasePermission:
    def __init__(self, request: Request, user: Optional[UserOut] = None):
        self.request = request
        self.user = user

    async def has_permission(self) -> bool:
        return True

    async def has_object_permission(self, obj: dict) -> bool:
        return True

class AllowAny(BasePermission):
    async def has_permission(self) -> bool:
        return True

class IsAuthenticated(BasePermission):
    async def has_permission(self) -> bool:
        if not self.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication credentials were not provided."
            )
        return True

class IsAdminUser(BasePermission):
    async def has_permission(self) -> bool:
        if not self.user or not self.user.is_staff:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action."
            )
        return True

class IsOwner(BasePermission):
    async def has_permission(self) -> bool:
        if not self.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required for owner-based access."
            )
        return True

    async def has_object_permission(self, obj: Any) -> bool:
        # obj is a Beanie Document
        creator_id = getattr(obj, "created_by", None)
        return self.user and str(creator_id) == str(self.user.id)

def PermissionDependency(permission_classes: List[Type[BasePermission]], use_auth: bool = True):
    """
    Factory that returns a dependency function to check permissions with Pydantic user context.
    """
    async def permission_checker(
        request: Request, 
        user: Optional[UserOut] = Depends(get_current_user if use_auth else get_optional_user)
    ):
        for p_class in permission_classes:
            p_inst = p_class(request, user)
            if not await p_inst.has_permission():
                raise HTTPException(status_code=403, detail="Permission denied")
        return user
    return permission_checker
