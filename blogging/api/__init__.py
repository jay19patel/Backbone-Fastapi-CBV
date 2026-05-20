"""
blogging/api
~~~~~~~~~~~~

API routers exposure for the Blogging module.
Exposes category/post, playlist, and custom user routes.
"""

from blogging.api.blog import router as blog_router
from blogging.api.playlist import router as playlist_router
from blogging.api.users import router as users_router

__all__ = ["blog_router", "playlist_router", "users_router"]
