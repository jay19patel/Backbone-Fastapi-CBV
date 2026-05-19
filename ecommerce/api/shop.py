import asyncio
import re
from datetime import UTC, datetime
from typing import Any

from beanie import Link
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pymongo import UpdateOne

from backbone.common.utils import log_exceptions
from backbone.core.fields import serialize_attachment
from backbone.core.permissions import AllowAny
from backbone.generic.views import GenericCrudView
from ecommerce.schemas.shop import Cart, CartItem, Category, Order, OrderItem, Payment, Product


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
        "id",
        "name",
        "price",
        "price_value",
        "img",
        "images",
        "tag",
        "stock",
        "category_id",
        "description",
        "details",
        "created_at",
    ]
    filter_fields = ["category_id", "tag", "stock"]
    fetch_links = True
    permission_classes = [AllowAny]


# =============================================================================
# Order View
# =============================================================================
class OrderView(GenericCrudView):
    schema = Order
    search_fields = ["customer_name", "customer_email", "status", "payment_id"]
    list_fields = [
        "id",
        "customer_name",
        "customer_email",
        "customer_phone",
        "shipping_address",
        "city",
        "state",
        "pincode",
        "items",
        "total_amount",
        "status",
        "payment_id",
        "payment_status",
        "cart_id",
        "notes",
        "created_at",
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
    async def before_create(self, data: dict[str, Any], user: Any) -> dict[str, Any]:
        """
        Build embedded OrderItem snapshots.

        Strategy:
        1. If `cart_id` is given, load items directly from the Cart's CartItem documents.
           This ensures the order reflects exactly what was in the cart.
        2. Otherwise, fall back to `items` array in the request (manual orders).
        """
        cart_id = data.get("cart_id")
        payment_id = data.pop("payment_id", None)

        processed_items: list[OrderItem] = []
        total_amount = 0.0

        if cart_id:
            # ── Strategy 1: Pull items from the Cart ──────────────────────────
            cart = await Cart.get(cart_id)
            if not cart:
                raise HTTPException(status_code=404, detail="Cart not found.")
            if cart.is_ordered:
                raise HTTPException(status_code=400, detail="This cart has already been ordered.")

            # Fetch all CartItem documents for this cart
            cart_items = await CartItem.find(CartItem.cart_id == cart_id).to_list()
            if not cart_items:
                raise HTTPException(status_code=400, detail="Cart is empty.")

            for ci in cart_items:
                # Fetch the product to validate stock and get latest image
                product = None
                if ci.product:
                    product = (
                        await ci.product.fetch() if isinstance(ci.product, Link) else ci.product
                    )

                unit_price = ci.price  # Use snapshotted price from cart
                qty = ci.quantity

                if product and product.stock < qty:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Insufficient stock for '{ci.name}'. Only {product.stock} available.",
                    )

                item_snapshot = OrderItem(
                    product_id=str(product.id) if product else None,
                    cart_item_id=str(ci.id),
                    name=ci.name,
                    price=unit_price,
                    image=ci.image or (serialize_attachment(product.img) if product else None),
                    quantity=qty,
                    subtotal=unit_price * qty,
                )
                processed_items.append(item_snapshot)
                total_amount += item_snapshot.subtotal

        else:
            # ── Strategy 2: Manual item list in payload ────────────────────────
            raw_items = data.pop("items", [])
            if not raw_items:
                raise HTTPException(status_code=400, detail="Order must contain at least one item.")

            for item in raw_items:
                pid = None
                if hasattr(item, "product_id"):
                    pid = item.product_id
                elif hasattr(item, "product"):
                    pid = item.product
                elif isinstance(item, dict):
                    pid = item.get("product_id") or item.get("product")

                if isinstance(pid, dict):
                    pid = pid.get("id") or pid.get("_id")
                if hasattr(pid, "id"):
                    pid = pid.id
                if not pid:
                    continue

                product = await Product.get(pid)
                if not product:
                    raise HTTPException(status_code=404, detail=f"Product {pid} not found.")

                qty = (
                    item.get("quantity", 1)
                    if isinstance(item, dict)
                    else getattr(item, "quantity", 1)
                )
                if product.stock < qty:
                    raise HTTPException(
                        status_code=400, detail=f"Insufficient stock for {product.name}."
                    )

                unit_price = product.price_value or 0.0
                item_snapshot = OrderItem(
                    product_id=str(product.id),
                    name=product.name,
                    price=unit_price,
                    image=serialize_attachment(product.img),
                    quantity=qty,
                    subtotal=unit_price * qty,
                )
                processed_items.append(item_snapshot)
                total_amount += item_snapshot.subtotal

        if not processed_items:
            raise HTTPException(
                status_code=400, detail="No valid items could be processed for this order."
            )

        data["items"] = processed_items
        data["total_amount"] = total_amount
        data["payment_id"] = payment_id
        data["payment_status"] = "pending"
        return data

    @log_exceptions
    async def after_create(self, instance: Order, user: Any) -> Order:
        """
        After order is saved:
        1. Decrement product stock atomically via a single bulk_write.
        2. Mark source cart as ordered.
        3. Create a linked Payment document.

        Steps 2 and 3 run concurrently via asyncio.gather for improved throughput.
        """
        order_id = str(instance.id)

        # 1. Bulk-decrement stock — single MongoDB round-trip for all items
        #    PERF: Replaces N serial fetch+save cycles with one bulk_write.
        stock_ops = [
            UpdateOne(
                {"_id": ObjectId(item.product_id), "stock": {"$gte": item.quantity}},
                {"$inc": {"stock": -item.quantity}},
            )
            for item in instance.items
            if item.product_id
        ]
        if stock_ops:
            collection = Product.get_pymongo_collection()
            result = await collection.bulk_write(stock_ops, ordered=False)
            if result.modified_count < len(stock_ops):
                import logging

                logging.getLogger("backbone.shop").warning(
                    "Order %s: %d/%d stock decrements matched — some products may have had insufficient stock.",
                    order_id,
                    result.modified_count,
                    len(stock_ops),
                )

        # 2 & 3. Run cart-mark and payment-create concurrently
        async def _mark_cart_ordered() -> None:
            cart_id = getattr(instance, "cart_id", None)
            if not cart_id:
                return
            cart = await Cart.get(cart_id)
            if cart and not cart.is_ordered:
                cart.is_ordered = True
                cart.order_id = order_id
                await cart.save()

        async def _create_payment() -> Payment:
            payment = Payment(
                order=instance,
                amount=instance.total_amount,
                currency="INR",
                method="UPI",
                transaction_id=instance.payment_id,
                status="pending",
                submitted_at=datetime.now(UTC) if instance.payment_id else None,
            )
            await payment.insert()
            return payment

        _, payment = await asyncio.gather(_mark_cart_ordered(), _create_payment())

        # 4. Link payment back to order
        instance.payment = payment
        await instance.save()

        return instance


# =============================================================================
# Cart View
# =============================================================================
class CartView(GenericCrudView):
    schema = Cart
    search_fields = ["user_id", "session_id"]
    list_fields = [
        "id",
        "user_id",
        "session_id",
        "items",
        "total_amount",
        "is_ordered",
        "created_at",
    ]
    filter_fields = ["user_id", "session_id", "is_ordered"]
    fetch_links = True
    permission_classes = [AllowAny]

    async def get_queryset(self, request: Request, user: Any) -> dict[str, Any]:
        """Only show ACTIVE (non-ordered) carts by default."""
        base = await super().get_queryset(request, user)
        return {**base, "is_ordered": False}

    @staticmethod
    def _extract_product_id(value: Any) -> str | None:
        """Normalize product reference from API payloads (id string, dict, Link, DBRef)."""
        if value is None:
            return None
        if isinstance(value, Link):
            ref = value.ref
            if ref is None:
                return None
            return str(getattr(ref, "id", ref))
        if isinstance(value, dict):
            nested = value.get("id") or value.get("_id")
            return str(nested) if nested else None
        if hasattr(value, "id") and not isinstance(value, str | int):
            return str(value.id)
        if isinstance(value, str) and value:
            return value
        return None

    async def _process_cart_items(
        self, cart_id: str | None, raw_items: list[dict[str, Any]]
    ) -> tuple:
        """Create/replace CartItem documents for the given cart."""
        # Delete existing items for this cart to ensure clean state
        if cart_id:
            await CartItem.find(CartItem.cart_id == cart_id).delete()

        processed_links = []
        total_amount = 0.0

        for item in raw_items:
            pid = None
            if hasattr(item, "product"):
                pid = item.product
            elif hasattr(item, "product_id"):
                pid = item.product_id
            elif isinstance(item, dict):
                pid = item.get("product") or item.get("product_id")

            pid = self._extract_product_id(pid)
            if not pid:
                continue

            product = await Product.get(pid)
            if not product:
                continue

            qty = (
                item.get("quantity", 1) if isinstance(item, dict) else getattr(item, "quantity", 1)
            )

            cart_item = CartItem(
                cart_id=cart_id,
                product=product,
                name=product.name,
                price=product.price_value or 0.0,
                image=serialize_attachment(product.img),
                quantity=qty,
            )
            await cart_item.insert()
            processed_links.append(cart_item)
            total_amount += cart_item.price * qty

        return processed_links, total_amount

    @log_exceptions
    async def before_create(self, data: dict[str, Any], user: Any) -> dict[str, Any]:
        """Handle cart creation — attach user_id for authenticated users."""
        raw_items = data.pop("items", [])

        if user:
            data["user_id"] = str(user.id)
            data.pop("session_id", None)  # user-linked carts don't need session_id
        else:
            # Omit user_id entirely so guest partial index ($exists: false) applies
            data.pop("user_id", None)

        # Process items in after_create once we have the cart ID
        data["items"] = []
        data["total_amount"] = 0.0
        self._pending_cart_items = raw_items
        return data

    @log_exceptions
    async def after_create(self, instance: Cart, user: Any) -> Cart:
        """Back-link CartItems to this Cart once we have its ID."""
        cart_id = str(instance.id)
        pending_items = getattr(self, "_pending_cart_items", []) or []
        self._pending_cart_items = []

        if pending_items:
            processed_links, total_amount = await self._process_cart_items(cart_id, pending_items)
            instance.items = processed_links
            instance.total_amount = total_amount
            await instance.save()

        return instance

    @log_exceptions
    async def before_update(
        self, instance: Cart, data: dict[str, Any], user: Any
    ) -> dict[str, Any]:
        """Handle cart item updates."""
        if "items" in data:
            raw_items = data.pop("items", [])
            cart_id = str(getattr(instance, "id", None) or "")
            processed_links, total_amount = await self._process_cart_items(cart_id, raw_items)
            data["items"] = processed_links
            data["total_amount"] = total_amount
        return data


# =============================================================================
# Payment View
# =============================================================================
class PaymentView(GenericCrudView):
    schema = Payment
    list_fields = [
        "id",
        "order",
        "amount",
        "currency",
        "method",
        "transaction_id",
        "status",
        "submitted_at",
        "received_at",
        "confirmed_at",
        "created_at",
    ]
    filter_fields = ["status", "method"]
    fetch_links = True
    permission_classes = [AllowAny]


router = APIRouter()
router.include_router(CategoryView.as_router("/categories", tags=["Shop — Categories"]))
router.include_router(ProductView.as_router("/products", tags=["Shop — Products"]))
router.include_router(OrderView.as_router("/orders", tags=["Shop — Orders"]))
router.include_router(CartView.as_router("/carts", tags=["Shop — Carts"]))
router.include_router(PaymentView.as_router("/payments", tags=["Shop — Payments"]))
