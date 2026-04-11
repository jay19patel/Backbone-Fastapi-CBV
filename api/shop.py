import re
from typing import Any, List, Dict
from fastapi import APIRouter, HTTPException
from beanie import Link, PydanticObjectId

from backbone.generic.views import GenericCrudView
from backbone.core.permissions import AllowAny
from backbone.common.utils import log_exceptions
from schemas.shop import Category, Product, Order, OrderItem, Cart, CartItem, Payment


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
    fetch_links = True
    permission_classes = [AllowAny]

    async def filter_queryset(self, query: dict, request: Any) -> dict:
        query = await super().filter_queryset(query, request)
        if "customer_email" in query and isinstance(query["customer_email"], str):
            email = query["customer_email"].lower().strip()
            query["customer_email"] = {"$regex": f"^{re.escape(email)}$", "$options": "i"}
        return query

    @log_exceptions
    async def before_create(self, data: Dict[str, Any], user: Any) -> Dict[str, Any]:
        """
        Handle order item snapshot creation and validation before order is saved.
        """
        raw_items = data.pop("items", [])
        if not raw_items:
            raise HTTPException(status_code=400, detail="Order must contain at least one item.")

        processed_item_links = []
        total_amount = 0.0

        for item in raw_items:
            # item could be a dict or a CartItem link if coming from frontend cart
            pid = item.get("product_id") or item.get("product", {}).get("id")
            if not pid: continue

            product = await Product.get(pid)
            if not product:
                raise HTTPException(status_code=404, detail=f"Product {pid} not found.")
            
            if product.stock < item.get("quantity", 1):
                raise HTTPException(status_code=400, detail=f"Insufficient stock for {product.name}.")

            # Create OrderItem snapshot
            order_item = OrderItem(
                product=product,
                name=product.name,
                price=product.price_value or 0.0,
                image=product.img,
                quantity=item.get("quantity", 1),
                subtotal=(product.price_value or 0.0) * item.get("quantity", 1)
            )
            await order_item.insert()
            processed_item_links.append(order_item)
            total_amount += order_item.subtotal

            # Decrement inventory
            product.stock -= order_item.quantity
            await product.save()

        data["items"] = processed_item_links
        data["total_amount"] = total_amount
        return data


class CartView(GenericCrudView):
    schema = Cart
    search_fields = ["session_id"]
    list_fields = ["id", "session_id", "items", "total_amount", "created_at"]
    filter_fields = ["session_id"]
    fetch_links = True
    permission_classes = [AllowAny]

    @log_exceptions
    async def before_create(self, data: Dict[str, Any], user: Any) -> Dict[str, Any]:
        """
        Handle cart item creation and linking.
        """
        raw_items = data.pop("items", [])
        processed_item_links = []
        total_amount = 0.0

        for item in raw_items:
            pid = item.get("product_id") or item.get("product", {}).get("id")
            if not pid: continue

            product = await Product.get(pid)
            if not product: continue

            cart_item = CartItem(
                product=product,
                name=product.name,
                price=product.price_value or 0.0,
                image=product.img,
                quantity=item.get("quantity", 1)
            )
            await cart_item.insert()
            processed_item_links.append(cart_item)
            total_amount += cart_item.price * cart_item.quantity

        data["items"] = processed_item_links
        data["total_amount"] = total_amount
        return data


class PaymentView(GenericCrudView):
    schema = Payment
    list_fields = ["id", "order", "amount", "method", "status", "transaction_id", "created_at"]
    filter_fields = ["status", "method"]
    fetch_links = True
    permission_classes = [AllowAny]


router = APIRouter()
router.include_router(CategoryView.as_router("/categories", tags=["Shop — Categories"]))
router.include_router(ProductView.as_router("/products", tags=["Shop — Products"]))
router.include_router(OrderView.as_router("/orders", tags=["Shop — Orders"]))
router.include_router(CartView.as_router("/carts", tags=["Shop — Carts"]))
router.include_router(PaymentView.as_router("/payments", tags=["Shop — Payments"]))

