"""
backend/tests/seed.py
─────────────────────
Run this once to seed the database with all sample data:
    cd backend
    .venv/bin/python tests/seed.py

It creates:
  • 3 Categories
  • 10 Products  (linked to their categories)
  • 5 Testimonials
  • 2 sample Orders  (each with 2 OrderItems)

Safe to re-run — skips documents that already exist (matched by name/email).
"""

import asyncio
import sys
import os

# ── Make sure backend/ is on the path ─────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

from backbone.core.settings import settings
from backbone.core.models import Attachment
from schemas.shop import Category, Product, Order, OrderItem
from schemas.content import Testimonial


# ═══════════════════════════════════════════════════════════════════════════
# SEED DATA
# ═══════════════════════════════════════════════════════════════════════════

CATEGORIES = [
    {
        "name": "Woolen Fashion",
        "img": "/images/cat_fashion.png",
        "color": "bg-orange-50",
        "description": "Stay cozy and stylish with our handcrafted woolen apparel.",
    },
    {
        "name": "Creative Keychains",
        "img": "/images/cat_accessories.png",
        "color": "bg-blue-50",
        "description": "Unique and adorable keychains to personalize your style.",
    },
    {
        "name": "Handmade Decor",
        "img": "/images/cat_decor.png",
        "color": "bg-slate-50",
        "description": "Bring warmth to your home with our knitted decorations.",
    },
]

PRODUCTS = [
    {
        "name": "Soulful Tote",
        "price": "₹1499",
        "price_value": 1499.0,
        "img": "/images/1.jpeg",
        "images": ["/images/1.jpeg", "/images/4.jpeg", "/images/6.jpeg"],
        "tag": "Handmade",
        "category_name": "Woolen Fashion",
        "stock": 15,
        "description": "A spacious and stylish tote bag, handcrafted with premium wool. Perfect for daily use, combining durability with an artistic handcrafted aesthetic.",
        "details": "100% Cotton Wool, Hand-knitted, Durable inner lining, Size: 14x16 inches",
    },
    {
        "name": "Knitted Charm",
        "price": "₹899",
        "price_value": 899.0,
        "img": "/images/2.jpeg",
        "images": ["/images/2.jpeg", "/images/5.jpeg", "/images/8.jpeg"],
        "tag": "New",
        "category_name": "Creative Keychains",
        "stock": 30,
        "description": "A cute knitted charm to add character to your keys or bag. Each charm is uniquely crafted with attention to every small detail.",
        "details": "Premium Yarn, Stainless steel ring, Eco-friendly filling",
    },
    {
        "name": "Woolen Heart",
        "price": "₹599",
        "price_value": 599.0,
        "img": "/images/3.jpeg",
        "images": ["/images/3.jpeg", "/images/1.jpeg", "/images/7.jpeg"],
        "tag": "Bestseller",
        "category_name": "Handmade Decor",
        "stock": 25,
        "description": "A soft, knitted heart perfect for home decoration or gifting. It brings a touch of warmth and love to any corner of your room.",
        "details": "Soft Wool, Washable, Safe for kids, Size: 5x5 inches",
    },
    {
        "name": "Crafty Pouch",
        "price": "₹1299",
        "price_value": 1299.0,
        "img": "/images/4.jpeg",
        "images": ["/images/4.jpeg", "/images/2.jpeg", "/images/5.jpeg"],
        "tag": "Limited",
        "category_name": "Woolen Fashion",
        "stock": 8,
        "description": "A versatile pouch for your essentials, featuring intricate patterns. Ideal for carrying makeup, stationery, or your phone.",
        "details": "Zip closure, Hand-knitted pattern, Lightweight, Dimensions: 8x5 inches",
    },
    {
        "name": "Soft Mascot",
        "price": "₹799",
        "price_value": 799.0,
        "img": "/images/5.jpeg",
        "images": ["/images/5.jpeg", "/images/2.jpeg", "/images/8.jpeg"],
        "tag": "Popular",
        "category_name": "Creative Keychains",
        "stock": 20,
        "description": "A tiny knitted mascot that brings a smile wherever it goes. The perfect companion for your backpack or a sweet desk buddy.",
        "details": "Handcrafted, Hypoallergenic stuffing, Vibrant colors",
    },
    {
        "name": "Artist Scarf",
        "price": "₹1999",
        "price_value": 1999.0,
        "img": "/images/6.jpeg",
        "images": ["/images/6.jpeg", "/images/1.jpeg", "/images/7.jpeg"],
        "tag": "Premium",
        "category_name": "Woolen Fashion",
        "stock": 10,
        "description": "An elegant, hand-knitted scarf designed for comfort and style. The artist's touch is visible in the unique loop patterns.",
        "details": "Merino Wool Blend, Winter-ready, Extra long (6 feet), Hand wash only",
    },
    {
        "name": "Cozy Mittens",
        "price": "₹699",
        "price_value": 699.0,
        "img": "/images/7.jpeg",
        "images": ["/images/7.jpeg", "/images/3.jpeg", "/images/6.jpeg"],
        "tag": "New",
        "category_name": "Woolen Fashion",
        "stock": 18,
        "description": "Warm and soft mittens to keep your hands cozy during winter. Features a stretchable wrist band for a snug fit.",
        "details": "Double layered wool, Breathable material, Available in multiple colors",
    },
    {
        "name": "Cloud Plush",
        "price": "₹2499",
        "price_value": 2499.0,
        "img": "/images/8.jpeg",
        "images": ["/images/8.jpeg", "/images/5.jpeg", "/images/3.jpeg"],
        "tag": "Exclusive",
        "category_name": "Handmade Decor",
        "stock": 5,
        "description": "A large, fluffy cloud plushie that adds a touch of magic to any room. It feels like hugging a real cloud!",
        "details": "Super soft synthetic wool, Large size (18 inches), Dust resistant",
    },
    {
        "name": "Boho Wall Hanging",
        "price": "₹1799",
        "price_value": 1799.0,
        "img": "/images/3.jpeg",
        "images": ["/images/3.jpeg", "/images/1.jpeg", "/images/8.jpeg"],
        "tag": "Featured",
        "category_name": "Handmade Decor",
        "stock": 7,
        "description": "Incredibly detailed wall hanging for a bohemian interior vibe. Handcrafted with multiple yarn textures.",
        "details": "Macramé & Knit hybrid, Natural wood rod, Length: 24 inches",
    },
    {
        "name": "Mini Cactus Pot",
        "price": "₹499",
        "price_value": 499.0,
        "img": "/images/2.jpeg",
        "images": ["/images/2.jpeg", "/images/5.jpeg", "/images/3.jpeg"],
        "tag": "Cute",
        "category_name": "Handmade Decor",
        "stock": 35,
        "description": "A knitted mini cactus that never needs watering! Comes in a cute little ceramic-look knitted pot.",
        "details": "Miniature size (4 inches), Perfect for desk, Includes knitted soil detail",
    },
]

TESTIMONIALS = [
    {
        "author_name": "Aarti Sharma",
        "content": "The handcrafted woolen scarf I received is simply beautiful. The quality of the wool is incredibly soft, and you can really feel the love knitted into it!",
        "rating": 5,
        "productImage": "https://images.unsplash.com/photo-1605282722370-dcc2525aa1cc?auto=format&fit=crop&q=80&w=300",
        "user": None,
    },
    {
        "author_name": "Rohan Patel",
        "content": "I ordered a custom keychain for my wife, and she absolutely loved it. The attention to detail is stunning and it arrived perfectly packaged.",
        "rating": 5,
        "productImage": "https://images.unsplash.com/photo-1620791493630-f9fdc61df1cd?auto=format&fit=crop&q=80&w=300",
        "user": None,
    },
    {
        "author_name": "Sneha Desai",
        "content": "The woolen decor pieces completely changed the vibe of my living room! Khushi is truly an amazing artist. Will definitely buy again.",
        "rating": 5,
        "productImage": "https://images.unsplash.com/photo-1544441893-675973e31985?auto=format&fit=crop&q=80&w=300",
        "user": None,
    },
    {
        "author_name": "Vikram Singh",
        "content": "Bought the Cloud Plush as a gift for my daughter. It's incredibly warm, sustainable, and looks so incredibly cute. 10/10 recommend!",
        "rating": 5,
        "productImage": "https://images.unsplash.com/photo-1584992236310-6edddc08acff?auto=format&fit=crop&q=80&w=300",
        "user": None,
    },
    {
        "author_name": "Meera Reddy",
        "content": "Absolutely gorgeous work! The woolen tote is not only fashionable but also incredibly durable. It stands out wherever I go.",
        "rating": 5,
        "productImage": "https://images.unsplash.com/photo-1510419356345-d36d859fa21e?auto=format&fit=crop&q=80&w=300",
        "user": None,
    },
]


SAMPLE_ORDERS = [
    {
        "customer_name": "Demo Customer",
        "customer_email": "demo@soulcraftstudio.in",
        "customer_phone": "+91 90000 00001",
        "shipping_address": "12 Baker Street, Near Town Hall",
        "city": "Valsad",
        "state": "Gujarat",
        "pincode": "396001",
        "total_amount": 2398.0,
        "status": "delivered",
        "payment_id": "DEMO123456",
        "payment_status": "verified",
        "notes": "Sample seeded order",
        "items": [
            {"product_name": "Soulful Tote",  "quantity": 1, "price": 1499.0, "img": "/images/1.jpeg"},
            {"product_name": "Knitted Charm", "quantity": 1, "price": 899.0,  "img": "/images/2.jpeg"},
        ],
    },
    {
        "customer_name": "Test User",
        "customer_email": "test@soulcraftstudio.in",
        "customer_phone": "+91 90000 00002",
        "shipping_address": "45 Rose Garden Colony",
        "city": "Surat",
        "state": "Gujarat",
        "pincode": "395001",
        "total_amount": 3098.0,
        "status": "shipped",
        "payment_id": "TEST789012",
        "payment_status": "verified",
        "notes": "Sample seeded order",
        "items": [
            {"product_name": "Artist Scarf",  "quantity": 1, "price": 1999.0, "img": "/images/6.jpeg"},
            {"product_name": "Woolen Heart",  "quantity": 1, "price": 599.0,  "img": "/images/3.jpeg"},
            {"product_name": "Mini Cactus Pot","quantity": 1, "price": 499.0,  "img": "/images/2.jpeg"},
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# SEED FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════


import os
import shutil

async def process_test_image(dummy_url: str):
    if not dummy_url: return None
    from backbone.core.models import Attachment
    filename = dummy_url.split('/')[-1]
    media_url = f'/media/images/{filename}'
    att = await Attachment.find_one({'file_path': media_url})
    if att: return att
    src = os.path.join(os.path.dirname(__file__), 'images', filename)
    dest_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'media', 'images')
    os.makedirs(dest_dir, exist_ok=True)
    if os.path.exists(src):
        shutil.copy2(src, os.path.join(dest_dir, filename))
    status = 'completed'
    return await Attachment(
        filename=filename, 
        file_path=media_url, 
        content_type='image/png' if 'png' in filename else 'image/jpeg', 
        status=status).insert()

async def seed_categories() -> dict[str, str]:
    """Insert categories, return name→id map."""
    cat_id_map = {}
    created = skipped = 0

    for data in CATEGORIES:
        exists = await Category.find_one(Category.name == data["name"])
        if exists:
            cat_id_map[data["name"]] = str(exists.id)
            skipped += 1
            continue

        # Resolve attachment
        att = await process_test_image(data["img"])
        data_copy = {**data, "img": att}

        cat = Category(**data_copy)
        await cat.insert()
        cat_id_map[data["name"]] = str(cat.id)
        created += 1

    print(f"  Categories — created: {created}, skipped: {skipped}")
    return cat_id_map


async def seed_products(cat_id_map: dict[str, str]):
    created = skipped = 0

    for data in PRODUCTS:
        exists = await Product.find_one(Product.name == data["name"])
        if exists:
            skipped += 1
            continue

        product_data = {k: v for k, v in data.items() if k != "category_name" and k not in ["img", "images"]}
        product_data["category_id"] = cat_id_map.get(data["category_name"], "")

        # Resolve attachments
        product_data["img"] = await process_test_image(data["img"])
        gallery_atts = []
        for g in data.get("images", []):
            gallery_atts.append(await process_test_image(g))
        product_data["images"] = gallery_atts

        product = Product(**product_data)
        await product.insert()
        created += 1

    print(f"  Products  — created: {created}, skipped: {skipped}")


async def seed_testimonials():
    created = skipped = 0

    for data in TESTIMONIALS:
        exists = await Testimonial.find_one(Testimonial.author_name == data["author_name"])
        if exists:
            skipped += 1
            continue

        t = Testimonial(**data)
        await t.insert()
        created += 1

    print(f"  Testimonials — created: {created}, skipped: {skipped}")


async def seed_orders():
    created = skipped = 0

    for data in SAMPLE_ORDERS:
        exists = await Order.find_one(
            Order.customer_email == data["customer_email"],
            Order.notes == "Sample seeded order",
        )
        if exists:
            skipped += 1
            continue

        # Resolve product IDs for order items
        items = []
        for item_data in data["items"]:
            product = await Product.find_one(Product.name == item_data["product_name"])
            product_id = str(product.id) if product else "unknown"
            items.append(
                OrderItem(
                    product_id=product_id,
                    name=item_data["product_name"],
                    quantity=item_data["quantity"],
                    price=item_data["price"],
                    image=item_data.get("img").replace('/images/', '/media/images/') if item_data.get("img") else None,
                )
            )

        order_data = {k: v for k, v in data.items() if k != "items"}
        order = Order(**order_data, items=items)
        await order.insert()
        created += 1

    print(f"  Orders    — created: {created}, skipped: {skipped}")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    print("\n🌱 Soul Craft Studio — Database Seeder")
    print("=" * 45)

    # Connect to MongoDB
    db_url  = settings.MONGODB_URL
    db_name = settings.DATABASE_NAME
    print(f"  DB  : {db_url}  /  {db_name}")

    client = AsyncIOMotorClient(db_url)
    db     = client[db_name]

    await init_beanie(
        database=db,
        document_models=[Attachment, Category, Product, Order, Testimonial],
    )

    print("\n📦 Seeding data...")
    cat_id_map = await seed_categories()
    await seed_products(cat_id_map)
    await seed_testimonials()
    await seed_orders()

    print("\n✅ Seeding complete!\n")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
