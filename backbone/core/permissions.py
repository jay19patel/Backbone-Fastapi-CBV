"""
backbone.core.permissions
~~~~~~~~~~~~~~~~~~~~~~~~~~

Permission system for Backbone views.

Provides:
    • ``BasePermission`` — abstract base for all permissions
    • ``AllowAny``, ``IsAuthenticated``, ``IsAdminUser``, ``IsOwner``
    • ``PermissionDependency`` — FastAPI dependency factory that **auto-derives**
      whether authentication is required from the permission classes.
    • Composable operators: ``IsAuthenticated & IsOwner``, ``IsAdminUser | IsOwner``

Design decisions:
    • The ``use_auth`` flag is **eliminated**.  ``PermissionDependency``
      inspects whether any permission class inherits from one of the
      ``AUTH_REQUIRING_PERMISSIONS`` and automatically chooses between
      ``get_current_user`` and ``get_optional_user``.
    • Permission classes are composable via ``&`` and ``|`` operators
      using metaclass-based operator overloading.
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional, Sequence, Type, Union

from fastapi import Depends, HTTPException, Request, status

from ..schemas import UserOut
from .dependencies import get_current_user, get_optional_user


# ── Permission Composition Operators ────────────────────────────────────────

class AND:
    """Combine two permissions with logical AND."""

    def __init__(
        self,
        request: Request,
        user: Optional[UserOut],
        op1_inst: Any,
        op2_inst: Any,
    ) -> None:
        self.op1_inst = op1_inst
        self.op2_inst = op2_inst

    async def has_permission(self) -> bool:
        """Both operands must grant permission."""
        return (await self.op1_inst.has_permission()) and (await self.op2_inst.has_permission())

    async def has_object_permission(self, obj: Any) -> bool:
        """Both operands must grant object-level permission."""
        return (await self.op1_inst.has_object_permission(obj)) and (
            await self.op2_inst.has_object_permission(obj)
        )


class OR:
    """Combine two permissions with logical OR."""

    def __init__(
        self,
        request: Request,
        user: Optional[UserOut],
        op1_inst: Any,
        op2_inst: Any,
    ) -> None:
        self.op1_inst = op1_inst
        self.op2_inst = op2_inst

    async def has_permission(self) -> bool:
        """Either operand may grant permission."""
        return (await self.op1_inst.has_permission()) or (await self.op2_inst.has_permission())

    async def has_object_permission(self, obj: Any) -> bool:
        """Either operand may grant object-level permission."""
        return (await self.op1_inst.has_object_permission(obj)) or (
            await self.op2_inst.has_object_permission(obj)
        )


class OperandHolder:
    """
    Holds two permission operands and lazily constructs their composition.

    Supports further chaining via ``&`` and ``|``.
    """

    def __init__(
        self,
        operator_class: type,
        op1_class: type,
        op2_class: type,
    ) -> None:
        self.operator_class = operator_class
        self.op1_class = op1_class
        self.op2_class = op2_class

    def __call__(
        self,
        request: Request,
        user: Optional[UserOut] = None,
    ) -> Any:
        """Instantiate and compose both operands."""
        op1_inst = self.op1_class(request, user)
        op2_inst = self.op2_class(request, user)
        return self.operator_class(request, user, op1_inst, op2_inst)

    def __and__(self, other: Any) -> OperandHolder:
        return OperandHolder(AND, self, other)

    def __or__(self, other: Any) -> OperandHolder:
        return OperandHolder(OR, self, other)


class BasePermissionMetaclass(type):
    """Metaclass enabling ``&`` and ``|`` operators on permission *classes*."""

    def __and__(cls, other: Any) -> OperandHolder:
        return OperandHolder(AND, cls, other)

    def __or__(cls, other: Any) -> OperandHolder:
        return OperandHolder(OR, cls, other)


# ── Base Permission ────────────────────────────────────────────────────────

class BasePermission(metaclass=BasePermissionMetaclass):
    """
    Abstract base class for all Backbone permissions.

    Every permission must implement:
        • ``has_permission()`` — called before the view logic
        • ``has_object_permission(obj)`` — called for object-level checks

    Both default to ``True`` (allow all).

    Example::

        class IsPublished(BasePermission):
            async def has_object_permission(self, obj):
                return obj.get("is_published", False)
    """

    def __init__(
        self,
        request: Request,
        user: Optional[UserOut] = None,
    ) -> None:
        self.request = request
        self.user = user

    async def has_permission(self) -> bool:
        """
        View-level permission check.  Called before any DB access.

        Returns:
            ``True`` to allow, ``False`` or raise to deny.
        """
        return True

    async def has_object_permission(self, obj: Any) -> bool:
        """
        Object-level permission check.  Called after fetching an object.

        Args:
            obj: The fetched document (as a dict).

        Returns:
            ``True`` to allow, ``False`` or raise to deny.
        """
        return True


# ── Built-in Permissions ────────────────────────────────────────────────────

class AllowAny(BasePermission):
    """
    Grants access to all requests — authenticated or not.

    This is the default permission when none is specified.
    """

    async def has_permission(self) -> bool:
        """Always returns ``True``."""
        return True


class IsAuthenticated(BasePermission):
    """
    Grants access only to authenticated users.

    Raises:
        HTTPException(401): If no valid user is present.
    """

    async def has_permission(self) -> bool:
        """Verify that a user is authenticated."""
        if not self.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication credentials were not provided.",
            )
        return True


class IsAdminUser(BasePermission):
    """
    Grants access only to users with ``is_staff=True``.

    Raises:
        HTTPException(403): If the user is not staff.
    """

    async def has_permission(self) -> bool:
        """Verify that the user has staff privileges."""
        if not self.user or not self.user.is_staff:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return True


class IsSuperUser(BasePermission):
    """
    Grants access only to users with ``is_superuser=True``.

    Raises:
        HTTPException(403): If the user is not a superuser.
    """

    async def has_permission(self) -> bool:
        """Verify that the user has superuser privileges."""
        if not self.user or not self.user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access restricted to superusers only.",
            )
        return True



class IsOwner(BasePermission):
    """
    Grants access only to the creator of a resource.

    View-level: requires authentication.
    Object-level: checks ``created_by`` field against current user.

    Raises:
        HTTPException(401): If the user is not authenticated.
    """

    async def has_permission(self) -> bool:
        """Ensure the user is authenticated (required for ownership check)."""
        if not self.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required for owner-based access.",
            )
        return True

    async def has_object_permission(self, obj: Any) -> bool:
        """
        Check whether the current user is the object's creator.

        Args:
            obj: The document (dict or object with ``created_by`` attribute).

        Returns:
            ``True`` if the current user created the object.
        """
        creator_id = getattr(obj, "created_by", None)
        if isinstance(obj, dict):
            creator_id = obj.get("created_by", creator_id)
        return self.user is not None and str(creator_id) == str(self.user.id)


# ── Permission Constants ───────────────────────────────────────────────────

# Permissions that require an authenticated user
AUTH_REQUIRING_PERMISSIONS = (IsAuthenticated, IsOwner, IsAdminUser, IsSuperUser)


# ── Permission Dependency Factory ──────────────────────────────────────────

def _requires_authentication(
    permission_classes: Sequence[Any],
) -> bool:
    """
    Determine whether any permission class requires authentication.

    Inspects the permission class hierarchy to decide between
    ``get_current_user`` and ``get_optional_user`` dependencies.

    Args:
        permission_classes: List of permission classes or OperandHolders.

    Returns:
        ``True`` if authentication is needed.
    """
    for perm_class in permission_classes:
        # Handle OperandHolder (composed permissions)
        if isinstance(perm_class, OperandHolder):
            return True  # Composed permissions always need auth
        # Handle regular permission classes
        if isinstance(perm_class, type) and issubclass(perm_class, AUTH_REQUIRING_PERMISSIONS):
            return True
    return False


def PermissionDependency(
    permission_classes: List[Any],
) -> Callable:
    """
    Factory that returns a FastAPI ``Depends()`` function for
    permission checking.

    **Auto-derives authentication requirement** from the permission
    classes — no ``use_auth=True`` flag needed.

    If any permission class inherits from ``IsAuthenticated``,
    ``IsOwner``, or ``IsAdminUser``, the dependency uses
    ``get_current_user``; otherwise it uses ``get_optional_user``.

    Args:
        permission_classes: List of permission classes to enforce.

    Returns:
        An async dependency function suitable for ``Depends()``.

    Example::

        perm_dep = PermissionDependency([IsAuthenticated])
        # Automatically uses get_current_user

        perm_dep = PermissionDependency([AllowAny])
        # Automatically uses get_optional_user
    """
    needs_auth = _requires_authentication(permission_classes)
    user_dependency = get_current_user if needs_auth else get_optional_user

    async def permission_checker(
        request: Request,
        user: Optional[UserOut] = Depends(user_dependency),
    ) -> Optional[UserOut]:
        """Check all permissions and return the user."""
        for perm_class in permission_classes:
            perm_inst = perm_class(request, user)
            if not await perm_inst.has_permission():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Permission denied.",
                )
        return user

    return permission_checker
