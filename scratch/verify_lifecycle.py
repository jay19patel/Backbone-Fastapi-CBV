
import asyncio
import os
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from schemas.shop import Order, OrderItem, Product, Category, Cart, CartItem
from backbone.core.models import Attachment, User
from api.shop import OrderView, CartView
from fastapi import Request
from unittest.mock import MagicMock

async def test_cart_order_lifecycle():
    # 1. Initialize Beanie
    client = AsyncIOMotorClient(os.getenv("MONGODB_URL", "mongodb://127.0.0.1:27017"))
    db = client["EShop"]
    await init_beanie(database=db, document_models=[Order, Product, Category, Attachment, User, Cart, CartItem])

    import time
    session_id = f"test_session_{int(time.time())}"
    
    # 2. Create products
    p1 = Product(name="Production Product 1", price="₹500", price_value=500.0, stock=20)
    await p1.insert()
    
    # 3. Create a Cart via CartView
    cart_view = CartView()
    # Mock request
    req = MagicMock(spec=Request)
    req.app.state.backbone_config.database = db
    await cart_view.resolve_context(req)
    
    cart_data = {
        "session_id": session_id,
        "items": [
            {"product": str(p1.id), "quantity": 3, "name": p1.name, "price": p1.price_value}
        ]
    }
    
    # Initial Create
    print("--- Creating Cart ---")
    cart_prep = await cart_view.before_create(cart_data, None)
    cart = await cart_view.perform_create(cart_prep)
    cart = await cart_view.after_create(cart, None)
    
    print(f"Cart created: {cart.id}, is_ordered: {cart.is_ordered}")
    
    # Verify CartItems have cart_id
    for item_link in cart.items:
        from beanie import Link
        item = await item_link.fetch() if isinstance(item_link, Link) else item_link
        print(f"CartItem ID: {item.id}, cart_id: {item.cart_id}")

    # 4. Create an Order from this Cart
    order_view = OrderView()
    await order_view.resolve_context(req)
    
    order_data = {
        "customer_name": "Production Buyer",
        "customer_email": "buyer@example.com",
        "shipping_address": "123 Main St, Tech City, 123456",
        "cart_id": str(cart.id),
        "items": [
            {"product_id": str(p1.id), "quantity": 3}
        ]
    }
    
    print("\n--- Creating Order from Cart ---")
    order_prep = await order_view.before_create(order_data, None)
    order = await order_view.perform_create(order_prep)
    order = await order_view.after_create(order, None)
    
    print(f"Order created: {order.id}, total: {order.total_amount}")
    
    # 5. Verify results
    # Re-fetch Cart
    updated_cart = await Cart.get(cart.id)
    print(f"Updated Cart Status -> is_ordered: {updated_cart.is_ordered}, order_id: {updated_cart.order_id}")
    
    # Re-fetch OrderItems (EMBEDDED)
    for item in order.items:
        print(f"OrderItem: {item.name}, quantity: {item.quantity}, subtotal: {item.subtotal}")
        
    # Verify Stock
    updated_p1 = await Product.get(p1.id)
    print(f"Updated Product Stock: {updated_p1.stock} (expected 17)")

    # Cleanup
    # No need to delete OrderItems separately as they are embedded in Order
    await CartItem.find(CartItem.cart_id == str(cart.id)).delete()
    await p1.delete()
    await order.delete()
    await cart.delete()
    print("\nTest completed & cleaned up.")

if __name__ == "__main__":
    asyncio.run(test_cart_order_lifecycle())
