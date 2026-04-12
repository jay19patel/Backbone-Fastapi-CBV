"""
backend/tests/seed.py
─────────────────────
Run this once to seed the database via the API:
    cd backend
    .venv/bin/python tests/seed.py

This script sends data through the official API endpoints, ensuring 
that all media processing (thumbnails, etc.) and hooks are triggered.

Requires:
  • Backend server running on http://127.0.0.1:8000
"""

import asyncio
import sys
import os
import httpx
import json
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────
BASE_URL = "http://127.0.0.1:8000/api"
IMAGES_DIR = Path(__file__).parent / "images"

CATEGORIES = [
    {
        "name": "Woolen Fashion",
        "img_path": "cat_fashion.png",
        "color": "bg-orange-50",
        "description": "Stay cozy and stylish with our handcrafted woolen apparel.",
    },
    {
        "name": "Creative Keychains",
        "img_path": "cat_accessories.png",
        "color": "bg-blue-50",
        "description": "Unique and adorable keychains to personalize your style.",
    },
    {
        "name": "Handmade Decor",
        "img_path": "cat_decor.png",
        "color": "bg-slate-50",
        "description": "Bring warmth to your home with our knitted decorations.",
    },
]

PRODUCTS = [
    {
        "name": "Soulful Tote",
        "price": "₹1499",
        "price_value": 1499.0,
        "img_path": "1.jpeg",
        "gallery_paths": ["1.jpeg", "4.jpeg", "6.jpeg"],
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
        "img_path": "2.jpeg",
        "gallery_paths": ["2.jpeg", "5.jpeg", "8.jpeg"],
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
        "img_path": "3.jpeg",
        "gallery_paths": ["3.jpeg", "1.jpeg", "7.jpeg"],
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
        "img_path": "4.jpeg",
        "gallery_paths": ["4.jpeg", "2.jpeg", "5.jpeg"],
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
        "img_path": "5.jpeg",
        "gallery_paths": ["5.jpeg", "2.jpeg", "8.jpeg"],
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
        "img_path": "6.jpeg",
        "gallery_paths": ["6.jpeg", "1.jpeg", "7.jpeg"],
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
        "img_path": "7.jpeg",
        "gallery_paths": ["7.jpeg", "3.jpeg", "6.jpeg"],
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
        "img_path": "8.jpeg",
        "gallery_paths": ["8.jpeg", "5.jpeg", "3.jpeg"],
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
        "img_path": "3.jpeg",
        "gallery_paths": ["3.jpeg", "1.jpeg", "8.jpeg"],
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
        "img_path": "2.jpeg",
        "gallery_paths": ["2.jpeg", "5.jpeg", "3.jpeg"],
        "tag": "Cute",
        "category_name": "Handmade Decor",
        "stock": 35,
        "description": "A knitted mini cactus that never needs watering! Comes in a cute little ceramic-look knitted pot.",
        "details": "Miniature size (4 inches), Perfect for desk, Includes knitted soil detail",
    },
]

class APISeeder:
    def __init__(self):
        # Increase timeout for slow image processing on the server
        self.client = httpx.AsyncClient(timeout=60.0, follow_redirects=True)
        self.cat_map = {} # name -> id
        self.attachment_map = {} # filename -> attachment_obj

    async def close(self):
        await self.client.aclose()

    async def check_connectivity(self):
        try:
            resp = await self.client.get(BASE_URL.replace("/api", "") + "/")
            if resp.status_code == 200:
                print(f"  OK: Server is reachable at {BASE_URL}")
                return True
            else:
                print(f"  \u26a0\ufe0f Warning: Server returned {resp.status_code}")
                return False
        except Exception as e:
            print(f"  Error: Could not connect to API: {e}")
            return False

    async def upload_image(self, filename: str) -> dict:
        if filename in self.attachment_map:
            return self.attachment_map[filename]

        file_path = IMAGES_DIR / filename
        if not file_path.exists():
            print(f"    \u26a0\ufe0f Warning: Image {filename} not found in {IMAGES_DIR}")
            return None

        with open(file_path, "rb") as f:
            files = {"file": (filename, f, "image/jpeg")}
            resp = await self.client.post(f"{BASE_URL}/media/upload", files=files)
            
        if resp.status_code == 200:
            data = resp.json()
            if "id" in data:
                self.attachment_map[filename] = data["id"]
                return data["id"]
            else:
                print(f"    Error: Upload successful but 'id' missing in response: {data}")
                return None
        else:
            print(f"    Error: Failed to upload {filename}: {resp.text}")
            return None

    async def seed_categories(self):
        print("\n[Categories] Seeding Categories")
        print("-" * 30)
        
        # Get existing categories to avoid duplicates
        try:
            existing_resp = await self.client.get(f"{BASE_URL}/categories/")
            existing = {c["name"]: c["id"] for c in existing_resp.json().get("results", [])}
        except Exception as e:
            print(f"  Warning: Could not fetch existing categories: {e}")
            existing = {}

        for data in CATEGORIES:
            name = data["name"]
            if name in existing:
                print(f"  Skip existing category: {name}")
                self.cat_map[name] = existing[name]
                continue

            print(f"  Creating category: {name}...", end="", flush=True)
            attachment = await self.upload_image(data["img_path"])
            
            payload = {
                "name": name,
                "img": attachment,
                "color": data["color"],
                "description": data["description"]
            }
            
            resp = await self.client.post(f"{BASE_URL}/categories/", json=payload)
            if resp.status_code in [200, 201]:
                resp_data = resp.json()
                cat_id = resp_data.get("id") or resp_data.get("_id")
                if cat_id:
                    self.cat_map[name] = cat_id
                    print(" OK")
                else:
                    print(f" failed: 'id' or '_id' missing in response. Body: {resp.text}")
            else:
                print(f" failed: {resp.status_code} - {resp.text}")

    async def seed_products(self):
        print("\n[Products] Seeding Products")
        print("-" * 30)

        # Get existing products
        try:
            existing_resp = await self.client.get(f"{BASE_URL}/products/")
            existing_names = {p["name"] for p in existing_resp.json().get("results", [])}
        except Exception as e:
            print(f"  Warning: Could not fetch existing products: {e}")
            existing_names = set()

        for data in PRODUCTS:
            name = data["name"]
            if name in existing_names:
                print(f"  Skip existing product: {name}")
                continue

            print(f"  Creating product: {name}...", end="", flush=True)
            
            # Resolve Image
            main_attachment = await self.upload_image(data["img_path"])
            
            # Resolve Gallery
            gallery = []
            for g_path in data.get("gallery_paths", []):
                att = await self.upload_image(g_path)
                if att: gallery.append(att)

            payload = {
                "name": name,
                "price": data["price"],
                "price_value": data["price_value"],
                "img": main_attachment,
                "images": gallery,
                "tag": data["tag"],
                "category_id": self.cat_map.get(data["category_name"]),
                "stock": data["stock"],
                "description": data["description"],
                "details": data["details"]
            }

            resp = await self.client.post(f"{BASE_URL}/products/", json=payload)
            if resp.status_code in [200, 201]:
                print(" OK")
            else:
                print(f" failed: {resp.text}")

async def main():
    print("\nSoul Craft Studio \u2014 API-Based Seeder")
    print("=" * 45)

    seeder = APISeeder()
    
    if not await seeder.check_connectivity():
        print("\nError: Ensure the backend server is running on http://127.0.0.1:8000")
        await seeder.close()
        return

    # Optional: Cleanup existing seeded data to ensure images are re-processed
    print("\n[Cleanup] Removing existing seeded records to ensure perfect state...")
    for data in CATEGORIES:
        # Exact match search
        search_resp = await seeder.client.get(f"{BASE_URL}/categories/", params={"search": data['name']})
        if search_resp.status_code == 200:
            for item in search_resp.json().get("results", []):
                if item["name"] == data["name"]:
                    print(f"  Cleaning up category: {item['name']}")
                    await seeder.client.delete(f"{BASE_URL}/categories/{item['id']}/")
    
    for data in PRODUCTS:
        search_resp = await seeder.client.get(f"{BASE_URL}/products/", params={"search": data['name']})
        if search_resp.status_code == 200:
            for item in search_resp.json().get("results", []):
                if item["name"] == data["name"]:
                    print(f"  Cleaning up product: {item['name']}")
                    await seeder.client.delete(f"{BASE_URL}/products/{item['id']}/")

    await seeder.seed_categories()
    await seeder.seed_products()

    await seeder.close()
    print("\n\u2705 Seeding complete!\n")

if __name__ == "__main__":
    asyncio.run(main())
