import re
from typing import Any
from fastapi import APIRouter

from backbone.generic.views import GenericCrudView
from backbone.core.permissions import AllowAny
from schemas.shop import Category, Product, Order, Cart


class CategoryView(GenericCrudView):
    schema = Category
    search_fields = ["name"]
    list_fields = ["id", "name", "img", "color", "description", "created_at"]
    fetch_links = True
    permission_classes = [AllowAny]


class ProductView(GenericCrudView):
    schema = Product
    search_fields = ["name", "tag", "description"]
    list_fields = [
        "id", "name", "price", "price_value", "img", "images",
        "tag", "stock", "category_id", "description", "details", "created_at",
    ]
    filter_fields = ["category_id", "tag", "stock"]
    fetch_links = True
    permission_classes = [AllowAny]


class OrderView(GenericCrudView):
    schema = Order
    search_fields = ["customer_name", "customer_email", "status", "payment_id"]
    list_fields = [
        "id", "customer_name", "customer_email", "customer_phone",
        "shipping_address", "city", "state", "pincode",
        "items", "total_amount", "status", "payment_id", "payment_status",
        "notes", "created_at",
    ]
    filter_fields = ["customer_email", "status", "payment_status"]
    permission_classes = [AllowAny]

    async def filter_queryset(self, query: dict, request: Any) -> dict:
        query = await super().filter_queryset(query, request)
        # Handle case-insensitive email filtering
        if "customer_email" in query and isinstance(query["customer_email"], str):
            email = query["customer_email"].lower().strip()
            query["customer_email"] = {"$regex": f"^{re.escape(email)}$", "$options": "i"}
        return query



class CartView(GenericCrudView):
    schema = Cart
    search_fields = ["session_id"]
    list_fields = ["id", "session_id", "items", "total_amount", "created_at"]
    filter_fields = ["session_id"]
    permission_classes = [AllowAny]


router = APIRouter()
router.include_router(CategoryView.as_router("/categories", tags=["Shop — Categories"]))
router.include_router(ProductView.as_router("/products", tags=["Shop — Products"]))
router.include_router(OrderView.as_router("/orders", tags=["Shop — Orders"]))
router.include_router(CartView.as_router("/carts", tags=["Shop — Carts"]))

