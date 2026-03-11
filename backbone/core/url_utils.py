"""
Dynamic base URL resolution using contextvars.

A middleware sets the base URL from the incoming request on each request.
Serializers and any code that needs the base URL can call `get_media_url(path)`
without hardcoding the host.
"""
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Holds the base URL for the current request, e.g. "http://127.0.0.1:8000"
_base_url_var: ContextVar[str] = ContextVar("base_url", default="")


def _build_base_url(request: Request) -> str:
    """Build `scheme://host` from the incoming request."""
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
    return f"{scheme}://{host}"


class DynamicBaseURLMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that stores the request's base URL
    in a context variable so that serializers can access it.
    """
    async def dispatch(self, request: Request, call_next):
        _base_url_var.set(_build_base_url(request))
        response = await call_next(request)
        return response


def get_base_url() -> str:
    """
    Return the base URL for the current request.
    Returns an empty string if called outside a request context.
    """
    return _base_url_var.get("")


def get_media_url(path: str) -> str:
    """
    Given a relative media path like `/media/uploads/pic.jpg`,
    return the full URL like `http://host:port/media/uploads/pic.jpg`.
    """
    if not path:
        return path
    if path.startswith(("http://", "https://")):
        return path  # already absolute
    return f"{get_base_url()}{path}"
