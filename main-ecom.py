"""
main.py — Soul Craft Studio, Backbone Backend
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Entry point. Responsibilities here are strictly:
  1. Settings instantiation
  2. Schema registration
  3. Router registration
  4. Framework bootstrap (BackboneConfig)

Business logic lives in:
  - api/          — view hooks (stock, cart, payment)
  - services/     — application-layer hooks (emails, audit logs)
"""

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from backbone import BackboneConfig
from backbone.core.settings import Settings


class ProjectSettings(Settings):
    """
    Project-specific settings. Inherits all defaults from Backbone core Settings.
    Add custom config variables here — they will auto-appear in the Admin Store.
    """


settings = ProjectSettings()

# ── Schema Imports ───────────────────────────────────────────────────────────
from backbone.auth.pages import router as auth_pages_router
from backbone.core.media_router import router as media_router
from ecommerce.api.content import router as content_router
from ecommerce.api.shop import router as shop_router

# ── Router Imports ───────────────────────────────────────────────────────────
from ecommerce.api.users import router as users_router
from ecommerce.pages import pages_router
from ecommerce.schemas.content import FAQ, Contact, Testimonial
from ecommerce.schemas.shop import Cart, CartItem, Category, Order, OrderItem, Payment, Product

# ── Signal Hooks ─────────────────────────────────────────────────────────────
# Import triggers hook registration via register_order_hooks() at module load.
from ecommerce.services.order_hooks import register_order_hooks

register_order_hooks()

# ── Application Setup ────────────────────────────────────────────────────────
app = FastAPI(
    title="Soul Craft Studio — Backbone Backend",
    description="Production API powered by Backbone FastAPI CBV framework.",
    version="1.0.0",
)

# HTML list pages + legacy redirects must register before admin CRUD routes
app.include_router(pages_router)


@app.get("/admin/pages/products", include_in_schema=False)
async def redirect_admin_products_page():
    return RedirectResponse(url="/pages/products", status_code=307)


@app.get("/admin/pages/orders", include_in_schema=False)
async def redirect_admin_orders_page():
    return RedirectResponse(url="/pages/orders", status_code=307)


@app.get("/about-backbone", include_in_schema=False)
async def redirect_about_backbone_page():
    return RedirectResponse(url="/pages/user-guide/", status_code=307)


models_to_register = [
    Category,
    Product,
    Order,
    OrderItem,
    Cart,
    CartItem,
    Payment,
    FAQ,
    Testimonial,
    Contact,
]

# ── Framework Bootstrap ───────────────────────────────────────────────────────
BackboneConfig(
    app=app,
    config=settings,
    document_models=models_to_register,
)

# Auth + framework HTML — under /pages/user-guide, /pages/reset-password, ...
app.include_router(auth_pages_router, prefix="/pages")

# ── API Routers ───────────────────────────────────────────────────────────────
app.include_router(users_router, prefix="/api")
app.include_router(shop_router, prefix="/api")
app.include_router(media_router, prefix="/api")
app.include_router(content_router, prefix="/api")


# ── System Endpoints ──────────────────────────────────────────────────────────


@app.get("/", tags=["System"])
async def root() -> dict:
    return {"message": "Soul Craft Studio Backbone Backend", "status": "online"}


@app.get("/health", tags=["System"])
async def health() -> dict:
    """Liveness probe endpoint. Returns 200 when the process is alive."""
    return {"status": "ok"}
