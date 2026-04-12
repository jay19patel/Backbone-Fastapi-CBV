from datetime import datetime
from typing import List, Optional, Any, Union
from pydantic import Field, BaseModel
import pydantic
from pymongo import IndexModel, ASCENDING, DESCENDING
from backbone.core.models import BackboneDocument, Attachment
from backbone.core.fields import Text, Name, Thumbnail
from beanie import Link


class Category(BackboneDocument):
    name: Name = Field(description="The name of the category (e.g. Woolen Fashion)")
    img: Thumbnail = None
    color: Optional[str] = Field(default=None, description="CSS color associated with category")
    description: Optional[str] = Field(default=None, description="Short description of the category")

    class Settings:
        name = "categories"
        indexes = [
            IndexModel(
                [("name", ASCENDING)],
                unique=True,
                partialFilterExpression={"is_deleted": {"$eq": False}},
                name="unique_active_category_name"
            )
        ]


class Product(BackboneDocument):
    name: Name = Field(description="The name of the product")
    price: str = Field(description="Display price string, e.g. ₹1499")
    price_value: Optional[float] = Field(default=0.0, description="Numeric price for calculations")
    img: Thumbnail = Field(default=None, json_schema_extra={"upload": False})
    images: Optional[List[Union[str, Link[Attachment]]]] = Field(
        default_factory=list,
        description="Additional gallery images",
        json_schema_extra={"upload": False}
    )
    tag: Optional[str] = Field(default=None, description="Special tag: Handmade, New, Bestseller, etc.")
    category_id: Optional[str] = Field(default=None, description="Reference to Category ID")
    stock: int = Field(default=10, description="Items available in stock")
    description: Optional[str] = Field(default=None, description="Full product description")
    details: Optional[str] = Field(default=None, description="Comma-separated specification details")

    class Settings:
        name = "products"
        indexes = [
            IndexModel([("name", ASCENDING)], unique=False),
            IndexModel([("tag", ASCENDING)], unique=False),
            IndexModel([("category_id", ASCENDING)], unique=False),
        ]

    @pydantic.field_serializer('images', when_used='json')
    def serialize_images(self, images: Optional[List[Any]]):
        from backbone.core.fields import serialize_attachment
        if not images: return []
        return [serialize_attachment(i) for i in images]


# ---------------------------------------------------------------------------
# CartItem — separate document linked to a Cart
# ---------------------------------------------------------------------------
class CartItem(BackboneDocument):
    cart_id: Optional[str] = Field(default=None, description="Internal ID of the parent cart")
    product: Link[Product] = Field(description="Link to the product")
    quantity: int = Field(default=1)

    # Snapshot at time of adding to cart
    name: str = Field(description="Snapshot: Name of product")
    price: float = Field(description="Snapshot: Price of product")
    image: Optional[str] = Field(default=None)

    @pydantic.field_validator('price', mode='before')
    @classmethod
    def parse_price(cls, v: Any) -> float:
        if isinstance(v, str):
            import re
            numeric_str = re.sub(r'[^\d.]', '', v)
            return float(numeric_str) if numeric_str else 0.0
        return v or 0.0

    class Settings:
        name = "cart_items"
        indexes = [
            IndexModel([("cart_id", ASCENDING)]),
        ]


# ---------------------------------------------------------------------------
# Cart — one active cart per user or session
# ---------------------------------------------------------------------------
class Cart(BackboneDocument):
    # Identity: prefer user_id for logged-in users, fall back to session_id
    user_id: Optional[str] = Field(default=None, description="Logged-in user ID (primary key for auth'd carts)")
    session_id: Optional[str] = Field(default=None, description="Anonymous session ID for guest carts")

    items: List[Link[CartItem]] = Field(default_factory=list, description="Linked cart items")
    total_amount: float = Field(default=0.0, description="Total amount in cart")

    # Lifecycle status
    is_ordered: bool = Field(default=False, description="True if this cart has been converted to an order")
    order_id: Optional[str] = Field(default=None, description="ID of the resulting order")

    class Settings:
        name = "carts"
        indexes = [
            # Quick lookup by user or session
            IndexModel([("user_id", ASCENDING)], name="user_id_index"),
            IndexModel([("session_id", ASCENDING)], name="session_id_index"),
            # Uniqueness: one active cart per user
            IndexModel(
                [("user_id", ASCENDING)],
                unique=True,
                partialFilterExpression={"is_ordered": {"$eq": False}, "user_id": {"$ne": None}},
                name="unique_active_cart_per_user"
            ),
            # Uniqueness: one active cart per session (guest)
            IndexModel(
                [("session_id", ASCENDING)],
                unique=True,
                partialFilterExpression={"is_ordered": {"$eq": False}, "session_id": {"$ne": None}, "user_id": {"$eq": None}},
                name="unique_active_cart_per_session"
            ),
        ]


# ---------------------------------------------------------------------------
# OrderItem — embedded snapshot inside Order (not a separate collection)
# ---------------------------------------------------------------------------
class OrderItem(BaseModel):
    """Embedded snapshot of a cart item at the moment of purchase."""
    # Optional soft-link back to the product (may become stale)
    product_id: Optional[str] = Field(default=None, description="Product ID at time of order")

    # Cart item reference for audit trail
    cart_item_id: Optional[str] = Field(default=None, description="Original CartItem document ID")

    # Immutable snapshots
    name: str = Field(description="Product name at time of order")
    price: float = Field(description="Unit price at time of order")
    image: Optional[str] = Field(default=None, description="Product image URL at time of order")
    quantity: int = Field(default=1)
    subtotal: float = Field(default=0.0, description="price × quantity")

    @pydantic.field_validator('price', mode='before')
    @classmethod
    def parse_price(cls, v: Any) -> float:
        if isinstance(v, str):
            import re
            numeric_str = re.sub(r'[^\d.]', '', v)
            return float(numeric_str) if numeric_str else 0.0
        return v or 0.0


# ---------------------------------------------------------------------------
# Order
# ---------------------------------------------------------------------------
class Order(BackboneDocument):
    # Customer info
    customer_name: Name = Field(description="Full name of the customer")
    customer_email: str = Field(description="Email address of the customer")
    customer_phone: Optional[str] = Field(default=None)

    @pydantic.field_validator('customer_email')
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower().strip() if v else v

    # Shipping
    shipping_address: Text = Field(description="Full shipping address")
    city: Optional[str] = Field(default=None)
    state: Optional[str] = Field(default=None)
    pincode: Optional[str] = Field(default=None)

    # Items (embedded snapshots — always visible, never orphaned)
    items: List[OrderItem] = Field(default_factory=list, description="Snapshot of ordered items")

    total_amount: float = Field(default=0.0)
    status: str = Field(
        default="pending",
        description="pending | processing | shipped | delivered | cancelled",
    )

    # Payment tracking
    payment_status: str = Field(
        default="pending",
        description="pending | received | verified | failed"
    )
    payment_id: Optional[str] = Field(default=None, description="UPI/transaction ID submitted by customer")
    payment: Optional[Link["Payment"]] = Field(default=None, description="Link to Payment document")

    # Source cart
    cart_id: Optional[str] = Field(default=None, description="Source Cart ID")
    notes: Optional[str] = Field(default=None)

    class Settings:
        name = "orders"
        indexes = [
            IndexModel([("customer_email", ASCENDING)], unique=False),
            IndexModel([("cart_id", ASCENDING)], unique=False),
            IndexModel([("created_at", DESCENDING)], unique=False),
            IndexModel([("status", ASCENDING)], unique=False),
            IndexModel([("payment_status", ASCENDING)], unique=False),
        ]


# ---------------------------------------------------------------------------
# Payment — linked to Order, tracks full payment lifecycle with dates
# ---------------------------------------------------------------------------
class Payment(BackboneDocument):
    order: Link[Order] = Field(description="Reference to the order")
    amount: float = Field(description="Amount paid")
    currency: str = Field(default="INR")
    method: str = Field(default="UPI", description="Payment method: UPI, Razorpay, COD, etc.")
    transaction_id: Optional[str] = Field(default=None, description="Customer-submitted UPI/transaction ID")
    screenshot_url: Optional[str] = Field(default=None, description="Optional payment screenshot URL")

    # Status lifecycle
    status: str = Field(default="pending", description="pending | received | verified | failed")

    # Timestamps for admin lifecycle tracking
    submitted_at: Optional[datetime] = Field(default=None, description="When customer submitted payment details")
    received_at: Optional[datetime] = Field(default=None, description="When admin marks payment as received")
    confirmed_at: Optional[datetime] = Field(default=None, description="When admin confirms/verifies payment")

    gateway_response: Optional[dict] = Field(default=None, description="Raw gateway response if applicable")

    class Settings:
        name = "payments"
        indexes = [
            IndexModel([("transaction_id", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
            IndexModel([("order", ASCENDING)]),
        ]


# ---------------------------------------------------------------------------
# Resolve forward references for circular links
# ---------------------------------------------------------------------------
Category.model_rebuild()
Product.model_rebuild()
CartItem.model_rebuild()
Cart.model_rebuild()
OrderItem.model_rebuild()
Order.model_rebuild()
Payment.model_rebuild()
