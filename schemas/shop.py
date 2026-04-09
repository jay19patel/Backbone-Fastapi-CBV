from typing import List, Optional
from pydantic import Field, BaseModel
from pymongo import IndexModel, ASCENDING, DESCENDING
from backbone.core.models import BackboneDocument
from backbone.core.fields import Text, Name

class Category(BackboneDocument):
    name: Name = Field(description="The name of the category (e.g. Woolen Fashion)")
    img: Optional[str] = Field(default=None, description="Image URL or Path for the category")
    color: Optional[str] = Field(default=None, description="CSS color associated with category")
    
    class Settings:
        name = "categories"
        indexes = [
            IndexModel([("name", ASCENDING)], unique=True)
        ]

class Product(BackboneDocument):
    name: Name = Field(description="The name of the product")
    price: str = Field(description="The string representation of the price, e.g. ₹1499")
    price_value: Optional[float] = Field(default=0.0, description="Numerical price value for calculations")
    img: Optional[str] = Field(default=None, description="Image URL or Path for the product")
    tag: Optional[str] = Field(default=None, description="Special tag (e.g. Handmade, New, Bestseller)")
    category_id: Optional[str] = Field(default=None, description="Reference to Category ID")
    stock: int = Field(default=10, description="Items available in stock")

    class Settings:
        name = "products"
        indexes = [
            IndexModel([("name", ASCENDING)], unique=False),
            IndexModel([("tag", ASCENDING)], unique=False)
        ]

class OrderItem(BaseModel):
    product_id: str
    name: str
    quantity: int
    price: float

class Order(BackboneDocument):
    customer_name: Name = Field(description="Name of the customer placing the order")
    customer_email: str = Field(description="Email of the customer")
    customer_phone: Optional[str] = Field(default=None, description="Phone number")
    shipping_address: Text = Field(description="Full shipping address")
    items: List[OrderItem] = Field(default_factory=list, description="List of items purchased")
    total_amount: float = Field(default=0.0, description="Total amount of the order")
    status: str = Field(default="pending", description="Order status: pending, shipped, delivered, cancelled")

    class Settings:
        name = "orders"
        indexes = [
            IndexModel([("customer_email", ASCENDING)], unique=False),
            IndexModel([("created_at", DESCENDING)], unique=False),
            IndexModel([("status", ASCENDING)], unique=False)
        ]

# Resolve forward references
Category.model_rebuild()
Product.model_rebuild()
Order.model_rebuild()
