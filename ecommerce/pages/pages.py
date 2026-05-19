"""
ecommerce.pages.pages
~~~~~~~~~~~~~~~~~~~~~

All HTML pages in one place.

Add a view class below, then add one entry to ``PAGE_ROUTES`` — the router mounts automatically.
Same pattern as ``backbone/auth/pages.py``.
"""

from __future__ import annotations

import math
import re
from typing import Any

from fastapi import APIRouter, Request

from backbone.core.config import BackboneConfig
from backbone.core.permissions import AllowAny
from backbone.generic.views import GenericTemplateView
from ecommerce.schemas.content import Contact
from ecommerce.schemas.shop import Order, Product

# ── Views ─────────────────────────────────────────────────────────────────────


class UserGuideView(GenericTemplateView):
    template_name = "pages/user_guide.html"
    page_name = "User Guide"
    page_description = "Backbone FastAPI developer guide and framework reference."
    admin_category = "Documentation"
    permission_classes = [AllowAny]

    async def get_context_data(
        self, request: Request, user: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        settings = BackboneConfig.get_instance().config
        base_url = str(request.base_url).rstrip("/")
        return {
            "site_name": getattr(settings, "SITE_NAME", "Backbone"),
            "api_base_url": f"{base_url}/api",
        }


class ContactListView(GenericTemplateView):
    template_name = "pages/contacts_list.html"
    page_name = "Contacts"
    page_description = "Contact form submissions."
    admin_category = "Project Management"
    permission_classes = [AllowAny]

    async def get_context_data(
        self, request: Request, user: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        query_text = (request.query_params.get("q") or "").strip()
        page = max(1, int(request.query_params.get("page") or 1))
        page_size = 50

        mongo_query: dict[str, Any] = {"is_deleted": False}
        if query_text:
            escaped = re.escape(query_text)
            mongo_query["$or"] = [
                {"name": {"$regex": escaped, "$options": "i"}},
                {"email": {"$regex": escaped, "$options": "i"}},
                {"subject": {"$regex": escaped, "$options": "i"}},
                {"message": {"$regex": escaped, "$options": "i"}},
            ]

        total = await Contact.find(mongo_query).count()
        total_pages = max(1, math.ceil(total / page_size))
        if page > total_pages:
            page = total_pages

        contacts = (
            await Contact.find(mongo_query)
            .sort("-created_at")
            .skip((page - 1) * page_size)
            .limit(page_size)
            .to_list()
        )

        rows = [
            {
                "name": c.name,
                "email": c.email,
                "subject": c.subject or "—",
                "message": c.message,
                "created_at": c.created_at.strftime("%d %b %Y") if c.created_at else "—",
            }
            for c in contacts
        ]

        return {
            "contacts": rows,
            "query": query_text,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "has_previous": page > 1,
            "has_next": page < total_pages,
            "previous_page": page - 1,
            "next_page": page + 1,
        }


class ProductListView(GenericTemplateView):
    template_name = "pages/products_list.html"
    page_name = "Products"
    page_description = "All products."
    admin_category = "Project Management"
    permission_classes = [AllowAny]

    async def get_context_data(
        self, request: Request, user: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        products = [
            {
                "name": str(p.name),
                "price": p.price or "—",
                "stock": p.stock,
                "tag": p.tag or "—",
            }
            for p in await Product.find_all().to_list()
        ]
        return {"products": products}


class OrderListView(GenericTemplateView):
    template_name = "pages/orders_list.html"
    page_name = "Orders"
    page_description = "All orders."
    admin_category = "Project Management"
    permission_classes = [AllowAny]

    async def get_context_data(
        self, request: Request, user: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        orders = []
        for order in await Order.find_all().sort("-created_at").to_list():
            created = order.created_at.strftime("%d %b %Y, %H:%M") if order.created_at else "—"
            orders.append(
                {
                    "id": str(order.id),
                    "customer_name": str(order.customer_name),
                    "customer_email": order.customer_email,
                    "status": order.status,
                    "payment_status": order.payment_status,
                    "total_amount": order.total_amount,
                    "items_count": len(order.items or []),
                    "created_at": created,
                }
            )
        return {"orders": orders}


# ── Routes (add new pages here only) ────────────────────────────────────────

# Do not use /admin/.../... — admin CRUD uses /admin/{model}/{pk} and will steal the URL.
PAGE_ROUTES: list[dict[str, Any]] = [
    {"path": "/pages/user-guide", "view": UserGuideView, "tags": ["Pages"]},
    {"path": "/contacts", "view": ContactListView, "tags": ["Pages"]},
    {"path": "/pages/products", "view": ProductListView, "tags": ["Pages"]},
    {"path": "/pages/orders", "view": OrderListView, "tags": ["Pages"]},
]


def build_pages_router() -> APIRouter:
    router = APIRouter(tags=["Pages"])
    for route in PAGE_ROUTES:
        view_cls: type[GenericTemplateView] = route["view"]
        path = route["path"]
        router.include_router(
            view_cls.as_router(
                path,
                tags=route.get("tags", ["Pages"]),
                admin_path=path,
                **route.get("router_kwargs", {}),
            )
        )
    return router


router = build_pages_router()
