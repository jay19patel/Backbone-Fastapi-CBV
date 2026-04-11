"""
api/users.py
------------
Users API — thin wrapper around Backbone's built-in AuthRouter.
The full auth endpoints (register, login, logout, /me, refresh)
are all provided by backbone.auth.router.AuthRouter and are
registered here via a dedicated FastAPI router.
"""

from fastapi import APIRouter
from backbone.auth.router import AuthRouter
from backbone.core.settings import settings

# Mount backbone's full auth router under /auth
_auth = AuthRouter(config=settings, prefix="/auth", tags=["Auth"])
router = APIRouter()
router.include_router(_auth.router)
