"""backbone.contrib.auth — re-exports backbone.auth for convenience."""
from backbone.auth.router import AuthRouter
from backbone.auth.service import AuthService
__all__ = ["AuthRouter", "AuthService"]
