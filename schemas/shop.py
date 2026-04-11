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
    img: Thumbnail = None
    images: Optional[List[Link[Attachment]]] = Field(default_factory=list, description="Additional gallery images")
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


class OrderItem(BaseModel):
    product_id: str
    name: str
    quantity: int
    price: float
    image: Optional[str] = None


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
    items: List[OrderItem] = Field(default_factory=list, description="List of ordered items")
    total_amount: float = Field(default=0.0, description="Grand total of the order")
    status: str = Field(
        default="pending",
        description="Order status: pending | processing | shipped | delivered | cancelled",
    )
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


# Resolve forward references
Category.model_rebuild()
Product.model_rebuild()
Order.model_rebuild()


class CartItem(BaseModel):
    product_id: str
    name: str
    quantity: int
    price: float
    image: Optional[str] = None


class Cart(BackboneDocument):
    session_id: str = Field(description="Anonymous session ID stored in browser, or user ID")
    items: List[CartItem] = Field(default_factory=list, description="Cart items")
    total_amount: float = Field(default=0.0, description="Total amount in cart")

    class Settings:
        name = "carts"
        indexes = [
            IndexModel([("session_id", ASCENDING)], unique=True)
        ]

Cart.model_rebuild()

