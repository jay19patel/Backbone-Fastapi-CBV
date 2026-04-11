import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backbone import (
    BackboneConfig,
    on_create,
    on_update,
    on_delete,
    on_field_change,
    log as backbone_log,
)
from backbone.core.settings import Settings

class ProjectSettings(Settings):
    """
    Project-specific settings. Inherits all defaults from Backbone core Settings.
    You can add custom config variables here which will automatically show up 
    in your Admin "Store" or be used anywhere!
    """
    pass

settings = ProjectSettings()

# Schemas
from schemas.shop import Category, Product, Order
from schemas.content import FAQ, Testimonial, Contact

# Routers
from api.users import router as users_router
from api.shop import router as shop_router
from backbone.core.media_router import router as media_router
from api.content import router as content_router
from pages.contact import router as pages_router
from backbone.auth.pages import router as auth_pages_router
from pages.admin_pages import (
    StoreTestView, 
    ContactFormTestView, 
    AdminProductListView, 
    AdminOrderManagementView
)


# --------------------------------------------------------------------------
# Application Setup
# --------------------------------------------------------------------------
app = FastAPI(title="Soul Craft Studio — Backbone Backend")

# Allowed CORS origins — add production frontend URL here when deploying
_extra_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    *_extra_origins,
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


models_to_register = [
    Category,
    Product,
    Order,
    FAQ,
    Testimonial,
    Contact,
]

# Custom Admin Pages (Must be registered before BackboneConfig to avoid greedy route conflicts)
app.include_router(StoreTestView.as_router("/admin/pages/store-test", tags=["Admin Pages"]))
app.include_router(ContactFormTestView.as_router("/admin/pages/contact-form", tags=["Admin Pages"]))
app.include_router(AdminProductListView.as_router("/admin/pages/products", tags=["Admin Pages"]))
app.include_router(AdminOrderManagementView.as_router("/admin/pages/orders", tags=["Admin Pages"]))

BackboneConfig(
    app=app,
    config=settings,
    document_models=models_to_register,
)


# --------------------------------------------------------------------------
# Shop Hooks (Order model)
# --------------------------------------------------------------------------
def _order_payload(instance: Order) -> dict:
    return {
        "id": str(getattr(instance, "id", "") or ""),
        "customer": getattr(instance, "customer_name", None),
        "total": getattr(instance, "total_amount", None),
        "status": getattr(instance, "status", None),
        "items_count": len(getattr(instance, "items", [])),
    }


@on_create(Order)
async def order_on_create_hook(instance: Order, **kwargs):
    backbone_log(
        "Order placed: on_create",
        hook="on_create",
        model="Order",
        payload=_order_payload(instance),
    )


@on_update(Order)
async def order_on_update_hook(instance: Order, changed_fields=None, **kwargs):
    backbone_log(
        "Order updated: on_update",
        hook="on_update",
        model="Order",
        payload=_order_payload(instance),
        changed_fields=list((changed_fields or {}).keys()),
    )


@on_delete(Order)
async def order_on_delete_hook(instance: Order, **kwargs):
    backbone_log(
        "Order deleted: on_delete",
        hook="on_delete",
        model="Order",
        payload=_order_payload(instance),
    )


@on_field_change(Order, fields=["status", "total_amount"])
async def order_on_field_change_hook(instance: Order, changed_fields=None, matched_fields=None, **kwargs):
    backbone_log(
        "Order status or total changed: on_field_change",
        hook="on_field_change",
        model="Order",
        payload=_order_payload(instance),
        matched_fields=matched_fields or [],
        changed_fields=list((changed_fields or {}).keys()),
    )


# --------------------------------------------------------------------------
# Register Routers
# --------------------------------------------------------------------------
app.include_router(users_router, prefix="/api")
app.include_router(shop_router, prefix="/api")
app.include_router(media_router, prefix="/api")
app.include_router(content_router, prefix="/api")
app.include_router(pages_router, prefix="/pages")
app.include_router(auth_pages_router, prefix="/pages")


@app.get("/")
async def root():
    return {"message": "Soul Craft Studio (Khushi Website) Backbone Backend"}
