from typing import List, Optional, Any
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
            IndexModel([("name", ASCENDING)], unique=True)
        ]


class Product(BackboneDocument):
    name: Name = Field(description="The name of the product")
    price: str = Field(description="Display price string, e.g. ₹1499")
    price_value: Optional[float] = Field(default=0.0, description="Numeric price for calculations")
    img: Thumbnail = Field(default=None, json_schema_extra={"upload": False})
    images: Optional[List[Link[Attachment]]] = Field(
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



class OrderItem(BackboneDocument):
    order_id: Optional[str] = Field(default=None, description="Internal ID of the parent order")
    product: Optional[Link[Product]] = Field(default=None, description="Link to the current product document")
    
    # Snapshots (to preserve history even if product changes or is deleted)
    name: str = Field(description="Snapshot: Name of the product at time of order")
    price: float = Field(description="Snapshot: Price of the product at time of order")
    image: Optional[str] = Field(default=None, description="Snapshot: Main image URL at time of order")
    
    quantity: int = Field(default=1, description="Quantity ordered")
    subtotal: float = Field(default=0.0, description="Snapshot: quantity * price")

    @pydantic.field_validator('price', mode='before')
    @classmethod
    def parse_price(cls, v: Any) -> float:
        if isinstance(v, str):
            import re
            numeric_str = re.sub(r'[^\d.]', '', v)
            return float(numeric_str) if numeric_str else 0.0
        return v or 0.0

    class Settings:
        name = "order_items"
        indexes = [
            IndexModel([("order_id", ASCENDING)]),
        ]


class Order(BackboneDocument):
    customer_name: Name = Field(description="Full name of the customer")
    customer_email: str = Field(description="Email address of the customer")

    @pydantic.field_validator('customer_email')
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower().strip() if v else v

    customer_phone: Optional[str] = Field(default=None, description="Contact phone number")
    shipping_address: Text = Field(description="Full shipping address (street, city, state, pincode)")
    city: Optional[str] = Field(default=None, description="City for shipping")
    state: Optional[str] = Field(default=None, description="State for shipping")
    pincode: Optional[str] = Field(default=None, description="Postal code")
    
    # Relationship to OrderItem
    items: List[Link[OrderItem]] = Field(default_factory=list, description="Linked order items")
    
    total_amount: float = Field(default=0.0, description="Grand total of the order")
    status: str = Field(
        default="pending",
        description="Order status: pending | processing | shipped | delivered | cancelled",
    )
    
    # Payment Reference
    payment_id: Optional[str] = Field(default=None, description="UPI / gateway transaction ID")
    payment_status: str = Field(
        default="pending_verification",
        description="Payment status: pending_verification | verified | failed",
    )
    notes: Optional[str] = Field(default=None, description="Internal or customer notes")

    class Settings:
        name = "orders"
        indexes = [
            IndexModel([("customer_email", ASCENDING)], unique=False),
            IndexModel([("created_at", DESCENDING)], unique=False),
            IndexModel([("status", ASCENDING)], unique=False),
            IndexModel([("payment_status", ASCENDING)], unique=False),
        ]


class Payment(BackboneDocument):
    order: Link[Order] = Field(description="Reference to the order")
    amount: float = Field(description="Amount paid")
    currency: str = Field(default="INR")
    method: str = Field(description="Payment method: UPI, Razorpay, COD, etc.")
    transaction_id: Optional[str] = Field(default=None, description="Gateway transaction ID")
    status: str = Field(default="pending", description="pending | success | failed")
    gateway_response: Optional[dict] = Field(default=None, description="Raw response from payment gateway")

    class Settings:
        name = "payments"
        indexes = [
            IndexModel([("transaction_id", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
        ]


class CartItem(BackboneDocument):
    cart_id: Optional[str] = Field(default=None, description="Internal ID of the parent cart")
    product: Link[Product] = Field(description="Link to the product")
    quantity: int = Field(default=1)
    
    # We store a snapshot of name/price even in cart for quick display
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


class Cart(BackboneDocument):
    session_id: str = Field(description="Anonymous session ID stored in browser, or user ID")
    items: List[Link[CartItem]] = Field(default_factory=list, description="Linked cart items")
    total_amount: float = Field(default=0.0, description="Total amount in cart")

    class Settings:
        name = "carts"
        indexes = [
            IndexModel([("session_id", ASCENDING)], unique=True)
        ]


# Resolve forward references
Category.model_rebuild()
Product.model_rebuild()
OrderItem.model_rebuild()
Order.model_rebuild()
Payment.model_rebuild()
CartItem.model_rebuild()
Cart.model_rebuild()

