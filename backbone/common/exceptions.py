from typing import Any


class BackboneException(Exception):
    """Base exception for all Backbone related errors."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        detail: Any | None = None,
        error_code: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail or message
        self.error_code = error_code


class NotFoundException(BackboneException):
    """Raised when a resource is not found."""

    def __init__(self, message: str = "Resource not found", detail: Any | None = None):
        super().__init__(message, status_code=404, detail=detail, error_code="NOT_FOUND")


class ValidationException(BackboneException):
    """Raised when data validation fails."""

    def __init__(self, message: str = "Validation failed", detail: Any | None = None):
        super().__init__(message, status_code=400, detail=detail, error_code="VALIDATION_ERROR")


class AuthenticationException(BackboneException):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Authentication failed", detail: Any | None = None):
        super().__init__(message, status_code=401, detail=detail, error_code="UNAUTHENTICATED")


class PermissionException(BackboneException):
    """Raised when a user doesn't have permission."""

    def __init__(self, message: str = "Permission denied", detail: Any | None = None):
        super().__init__(message, status_code=403, detail=detail, error_code="PERMISSION_DENIED")


class ServiceException(BackboneException):
    """Raised when an internal service or external integration fails."""

    def __init__(self, message: str = "Internal service error", detail: Any | None = None):
        super().__init__(message, status_code=500, detail=detail, error_code="SERVICE_ERROR")
