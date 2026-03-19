"""backbone.contrib.admin — re-exports backbone.admin for convenience."""
from backbone.admin.router import router
from backbone.admin.site import admin_site
__all__ = ["router", "admin_site"]
