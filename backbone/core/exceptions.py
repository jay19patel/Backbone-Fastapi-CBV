from fastapi import HTTPException
from typing import Any, Dict, Optional

class APIException(HTTPException):
    """
    Base class for all custom API exceptions.
    Subclasses should provide `status_code` and `detail` defaults.
    """
    status_code: int = 500
    default_detail: str = "A server error occurred."
    default_code: str = "error"

    def __init__(
        self,
        detail: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        code: Optional[str] = None
    ):
        if detail is None:
            detail = self.default_detail
        self.code = code or self.default_code
        super().__init__(status_code=self.status_code, detail=detail, headers=headers)


class ValidationError(APIException):
    status_code = 400
    default_detail = "Invalid input."
    default_code = "invalid"


class ParseError(APIException):
    status_code = 400
    default_detail = "Malformed request."
    default_code = "parse_error"


class AuthenticationFailed(APIException):
    status_code = 401
    default_detail = "Incorrect authentication credentials."
    default_code = "authentication_failed"


class NotAuthenticated(APIException):
    status_code = 401
    default_detail = "Authentication credentials were not provided."
    default_code = "not_authenticated"


class PermissionDenied(APIException):
    status_code = 403
    default_detail = "You do not have permission to perform this action."
    default_code = "permission_denied"


class NotFound(APIException):
    status_code = 404
    default_detail = "Not found."
    default_code = "not_found"


class MethodNotAllowed(APIException):
    status_code = 405
    default_detail = "Method not allowed."
    default_code = "method_not_allowed"


class NotAcceptable(APIException):
    status_code = 406
    default_detail = "Could not satisfy the request Accept header."
    default_code = "not_acceptable"


class UnsupportedMediaType(APIException):
    status_code = 415
    default_detail = "Unsupported media type in request."
    default_code = "unsupported_media_type"


class Throttled(APIException):
    status_code = 429
    default_detail = "Request was throttled."
    default_code = "throttled"
    
    def __init__(self, wait: Optional[int] = None, detail: Optional[str] = None, headers: Optional[Dict[str, str]] = None):
        if detail is None:
            detail = self.default_detail
            if wait is not None:
                detail = f"Request was throttled. Expected available in {wait} seconds."
        self.wait = wait
        super().__init__(detail=detail, headers=headers)
