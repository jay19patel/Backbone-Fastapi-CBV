
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie, Document, Link, PydanticObjectId
from typing import List, Optional
from pydantic import Field
import os

# Minimal models to match current state and debug
class Product(Document):
    name: str
    class Settings:
        name = "products"

class CartItem(Document):
    product: Optional[Link[Product]] = None
    product_id_raw: Optional[str] = Field(default=None, alias="product_id")
    class Settings:
        name = "cart_items"

async def debug_db():
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27017")
    db = client["EShop"]
    
    print("\n--- Inspecting carts ---")
    cursor = db["carts"].find({})
    carts = await cursor.to_list(length=100)
    for doc in carts:
        print(f"Cart ID: {doc.get('_id')} | Session: {doc.get('session_id')}")
        items = doc.get("items", [])
        print(f"  Items ({len(items)}):")
        for i, item in enumerate(items):
            print(f"    [{i}]: {item}")

    print("\n--- Summary ---")
    print(f"Found {len(carts)} carts.")

if __name__ == "__main__":
    asyncio.run(debug_db())
