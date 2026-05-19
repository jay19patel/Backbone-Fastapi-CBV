"""
tests/seed.py — Seed catalog + commerce flow via the live API.

Usage (server must be running on http://127.0.0.1:8000):
    python tests/seed.py

Creates:
  • Categories & products (with images)
  • Guest cart + CartItem documents (active cart)
  • Orders from carts → embedded OrderItem snapshots
  • Payment documents linked to each order
"""

from __future__ import annotations

import asyncio
import mimetypes
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

API_ROOT = "http://127.0.0.1:8000"
BASE_URL = f"{API_ROOT}/api"
IMAGES_DIR = Path(__file__).parent / "images"


def extract_resource_id(document: dict[str, Any] | None, label: str = "resource") -> str:
    """Read ``id`` or ``_id`` from an API JSON object (Backbone may return either)."""
    if not document:
        raise RuntimeError(f"Empty API response for {label}")
    resource_id = document.get("id") or document.get("_id")
    if resource_id is None:
        keys = ", ".join(sorted(document.keys()))
        raise RuntimeError(f"API response for {label} has no id/_id (keys: {keys})")
    return str(resource_id)


# ── Seed identity (used for cleanup + demo orders) ────────────────────────────
SEED_CUSTOMER = {
    "customer_name": "Priya Sharma",
    "customer_email": "demo.seed@soulcraft.test",
    "customer_phone": "+91-9876543210",
    "shipping_address": "12 Craft Lane, Navrangpura",
    "city": "Ahmedabad",
    "state": "Gujarat",
    "pincode": "380009",
}

SEED_SESSION_ACTIVE = "seed-demo-active-cart"
SEED_SESSION_ORDER_PENDING = "seed-demo-order-pending"
SEED_SESSION_ORDER_PAID = "seed-demo-order-paid"

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
        "description": "A spacious and stylish tote bag, handcrafted with premium wool.",
        "details": "100% Cotton Wool, Hand-knitted, Size: 14x16 inches",
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
        "description": "A cute knitted charm for your keys or bag.",
        "details": "Premium Yarn, Stainless steel ring",
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
        "description": "A soft knitted heart for home decoration or gifting.",
        "details": "Soft Wool, Washable, Size: 5x5 inches",
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
        "description": "A versatile pouch for your essentials.",
        "details": "Zip closure, Hand-knitted pattern",
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
        "description": "A tiny knitted mascot for your backpack.",
        "details": "Handcrafted, Hypoallergenic stuffing",
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
        "description": "An elegant hand-knitted scarf.",
        "details": "Merino Wool Blend, Extra long",
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
        "description": "Warm mittens for winter.",
        "details": "Double layered wool",
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
        "description": "A large fluffy cloud plushie.",
        "details": "Super soft synthetic wool, 18 inches",
    },
]

# Cart line items reference product name + quantity
ACTIVE_CART_ITEMS = [
    {"product_name": "Soulful Tote", "quantity": 1},
    {"product_name": "Knitted Charm", "quantity": 2},
]

ORDER_PENDING_CART_ITEMS = [
    {"product_name": "Woolen Heart", "quantity": 1},
    {"product_name": "Crafty Pouch", "quantity": 1},
]

ORDER_PAID_CART_ITEMS = [
    {"product_name": "Artist Scarf", "quantity": 1},
    {"product_name": "Cozy Mittens", "quantity": 2},
]


class APISeeder:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(timeout=90.0, follow_redirects=True)
        self.cat_map: dict[str, str] = {}
        self.product_map: dict[str, str] = {}
        self.attachment_map: dict[str, str] = {}

    async def close(self) -> None:
        await self.client.aclose()

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    async def check_connectivity(self) -> bool:
        try:
            response = await self.client.get(f"{API_ROOT}/health")
            if response.status_code == 200:
                print(f"  OK: API reachable at {API_ROOT}")
                return True
            print(f"  Warning: health returned {response.status_code}")
            return False
        except httpx.HTTPError as error:
            print(f"  Error: cannot reach API — {error}")
            return False

    async def list_all(
        self, resource: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        params = dict(params or {})
        all_rows: list[dict[str, Any]] = []
        page = 1
        while True:
            response = await self.client.get(
                f"{BASE_URL}/{resource}/",
                params={**params, "page": page, "page_size": 100},
            )
            if response.status_code != 200:
                print(
                    f"  Warning: list {resource} failed ({response.status_code}): {response.text[:200]}"
                )
                break
            payload = response.json()
            all_rows.extend(payload.get("results", []))
            if page >= payload.get("total_pages", 1):
                break
            page += 1
        return all_rows

    async def delete_resource(self, resource: str, resource_id: str) -> bool:
        response = await self.client.delete(f"{BASE_URL}/{resource}/{resource_id}/")
        return response.status_code in (200, 204)

    # ── Media & catalog ───────────────────────────────────────────────────────

    async def upload_image(self, filename: str) -> str | None:
        if filename in self.attachment_map:
            return self.attachment_map[filename]

        file_path = IMAGES_DIR / filename
        if not file_path.exists():
            print(f"    Warning: missing image {filename}")
            return None

        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        with open(file_path, "rb") as file_handle:
            response = await self.client.post(
                f"{BASE_URL}/media/upload",
                files={"file": (filename, file_handle, mime_type)},
            )

        if response.status_code != 200:
            print(f"    Error uploading {filename}: {response.text[:200]}")
            return None

        data = response.json()
        attachment_id = data.get("id")
        if not attachment_id:
            print(f"    Error: upload OK but no id for {filename}")
            return None

        self.attachment_map[filename] = attachment_id
        return attachment_id

    async def load_product_map(self) -> dict[str, str]:
        rows = await self.list_all("products")
        self.product_map = {
            row["name"]: extract_resource_id(row, "product")
            for row in rows
            if row.get("name") and (row.get("id") or row.get("_id"))
        }
        return self.product_map

    async def restore_catalog_stock(self) -> None:
        """Reset stock so repeat seed runs do not fail on depleted inventory."""
        await self.load_product_map()
        for product_data in PRODUCTS:
            product_id = self.product_map.get(product_data["name"])
            if not product_id:
                continue
            response = await self.client.patch(
                f"{BASE_URL}/products/{product_id}/",
                json={"stock": product_data["stock"]},
            )
            if response.status_code not in (200, 201):
                print(f"  Warning: could not reset stock for {product_data['name']}")

    async def seed_categories(self) -> None:
        print("\n[1/5] Categories")
        print("-" * 40)
        existing = {
            row["name"]: extract_resource_id(row, "category")
            for row in await self.list_all("categories")
            if row.get("name") and (row.get("id") or row.get("_id"))
        }

        for data in CATEGORIES:
            name = data["name"]
            if name in existing:
                self.cat_map[name] = existing[name]
                print(f"  exists: {name}")
                continue

            print(f"  create: {name} ...", end="", flush=True)
            attachment_id = await self.upload_image(data["img_path"])
            response = await self.client.post(
                f"{BASE_URL}/categories/",
                json={
                    "name": name,
                    "img": attachment_id,
                    "color": data["color"],
                    "description": data["description"],
                },
            )
            if response.status_code in (200, 201):
                category_id = extract_resource_id(response.json(), "category")
                self.cat_map[name] = category_id
                print(" OK")
            else:
                print(f" FAIL ({response.status_code})")

    async def seed_products(self) -> None:
        print("\n[2/5] Products")
        print("-" * 40)
        existing_names = {row["name"] for row in await self.list_all("products") if row.get("name")}

        for data in PRODUCTS:
            name = data["name"]
            if name in existing_names:
                print(f"  exists: {name}")
                continue

            print(f"  create: {name} ...", end="", flush=True)
            main_image = await self.upload_image(data["img_path"])
            gallery = []
            for gallery_path in data.get("gallery_paths", []):
                attachment_id = await self.upload_image(gallery_path)
                if attachment_id:
                    gallery.append(attachment_id)

            response = await self.client.post(
                f"{BASE_URL}/products/",
                json={
                    "name": name,
                    "price": data["price"],
                    "price_value": data["price_value"],
                    "img": main_image,
                    "images": gallery,
                    "tag": data["tag"],
                    "category_id": self.cat_map.get(data["category_name"]),
                    "stock": data["stock"],
                    "description": data["description"],
                    "details": data["details"],
                },
            )
            print(" OK" if response.status_code in (200, 201) else f" FAIL — {response.text[:120]}")

        await self.load_product_map()
        if len(self.product_map) < 3:
            print("  Error: not enough products in DB to seed carts/orders.")
            sys.exit(1)

    # ── Commerce cleanup ────────────────────────────────────────────────────────

    async def cleanup_commerce_data(self) -> None:
        print("\n[Cleanup] Previous seed carts / orders / payments")
        print("-" * 40)

        seed_email = SEED_CUSTOMER["customer_email"].lower()
        orders = await self.list_all("orders", {"customer_email": seed_email})
        payment_ids: set[str] = set()

        for order in orders:
            payment = order.get("payment")
            if isinstance(payment, dict) and (payment.get("id") or payment.get("_id")):
                payment_ids.add(extract_resource_id(payment, "payment"))
            elif isinstance(payment, str):
                payment_ids.add(payment)

            order_id = order.get("id") or order.get("_id")
            if order_id and await self.delete_resource("orders", str(order_id)):
                print(f"  deleted order {order_id[:8]}…")

        for payment_row in await self.list_all("payments"):
            payment_id = payment_row.get("id") or payment_row.get("_id")
            transaction_id = payment_row.get("transaction_id") or ""
            if payment_id and (
                str(payment_id) in payment_ids or transaction_id.startswith("UPI-SEED-")
            ):
                if await self.delete_resource("payments", str(payment_id)):
                    print(f"  deleted payment {payment_id[:8]}…")

        seed_sessions = {
            SEED_SESSION_ACTIVE,
            SEED_SESSION_ORDER_PENDING,
            SEED_SESSION_ORDER_PAID,
        }
        for session_id in seed_sessions:
            carts = await self.list_all("carts", {"search": session_id, "page_size": 100})
            for cart in carts:
                if cart.get("session_id") != session_id:
                    continue
                cart_id = cart.get("id") or cart.get("_id")
                if not cart_id:
                    continue
                cart_id = str(cart_id)
                # Release unique session index (soft-deleted carts still matched old index)
                await self.client.patch(
                    f"{BASE_URL}/carts/{cart_id}/",
                    json={"is_ordered": True, "order_id": "seed-cleanup"},
                )
                if await self.delete_resource("carts", cart_id):
                    print(f"  removed cart {session_id}")

        await self.restore_catalog_stock()

    # ── Cart + order seeding ────────────────────────────────────────────────────

    def _product_catalog_by_name(self) -> dict[str, dict[str, Any]]:
        return {row["name"]: row for row in PRODUCTS}

    def _resolve_cart_items(self, line_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Build cart line payloads accepted by Cart create schema (CartItem fields)."""
        catalog = self._product_catalog_by_name()
        resolved: list[dict[str, Any]] = []
        for line in line_items:
            product_name = line["product_name"]
            product_id = self.product_map.get(product_name)
            catalog_row = catalog.get(product_name)
            if not product_id or not catalog_row:
                raise ValueError(f"Product not found for cart line: {product_name}")
            resolved.append(
                {
                    "product": product_id,
                    "name": product_name,
                    "price": catalog_row["price_value"],
                    "quantity": line["quantity"],
                }
            )
        return resolved

    async def create_cart(
        self, session_id: str, line_items: list[dict[str, Any]]
    ) -> dict[str, Any]:
        payload = {
            "session_id": session_id,
            "items": self._resolve_cart_items(line_items),
        }
        response = await self.client.post(f"{BASE_URL}/carts/", json=payload)
        if response.status_code not in (200, 201):
            raise RuntimeError(f"Cart create failed ({response.status_code}): {response.text}")

        cart = response.json()
        try:
            cart_id = extract_resource_id(cart, f"cart:{session_id}")
        except RuntimeError:
            cart_id = None

        if cart_id:
            detail = await self.client.get(f"{BASE_URL}/carts/{cart_id}/")
            if detail.status_code == 200:
                cart = detail.json()
                cart_id = extract_resource_id(cart, f"cart:{session_id}")
        else:
            for row in await self.list_all("carts", {"search": session_id}):
                if row.get("session_id") == session_id:
                    cart = row
                    cart_id = extract_resource_id(cart, f"cart:{session_id}")
                    break
            else:
                raise RuntimeError(
                    f"Cart created for {session_id} but no id in response; "
                    f"keys={sorted(cart.keys())}"
                )

        cart["id"] = cart_id
        item_count = len(cart.get("items") or [])
        if item_count == 0:
            raise RuntimeError(
                f"Cart {session_id} has no CartItem rows — check CartView after_create hook."
            )

        print(
            f"  cart {session_id}: {item_count} item(s), total ₹{cart.get('total_amount', 0):.2f}"
        )
        return cart

    async def create_order_from_cart(
        self,
        cart_id: str,
        *,
        payment_id: str | None = None,
        status: str = "pending",
        notes: str = "",
    ) -> dict[str, Any]:
        payload = {
            **SEED_CUSTOMER,
            "cart_id": cart_id,
            "status": status,
            "notes": notes,
        }
        if payment_id:
            payload["payment_id"] = payment_id

        response = await self.client.post(f"{BASE_URL}/orders/", json=payload)
        if response.status_code not in (200, 201):
            raise RuntimeError(f"Order create failed ({response.status_code}): {response.text}")

        order = response.json()
        order_id = extract_resource_id(order, "order")
        detail = await self.client.get(f"{BASE_URL}/orders/{order_id}/")
        if detail.status_code == 200:
            order = detail.json()
            order_id = extract_resource_id(order, "order")
        order["id"] = order_id

        embedded_items = order.get("items") or []
        if not embedded_items:
            raise RuntimeError("Order has no embedded OrderItem snapshots.")

        payment_ref = order.get("payment")
        if isinstance(payment_ref, dict):
            payment_doc_id = payment_ref.get("id") or payment_ref.get("_id")
        else:
            payment_doc_id = payment_ref

        print(
            f"  order {str(order_id)[:8]}…: {len(embedded_items)} line(s), "
            f"total ₹{order.get('total_amount', 0):.2f}, "
            f"payment_status={order.get('payment_status')}"
        )
        for line in embedded_items:
            print(
                f"    • {line.get('name')} × {line.get('quantity')} "
                f"@ ₹{line.get('price')} = ₹{line.get('subtotal', 0):.2f}"
            )

        if payment_doc_id:
            print(f"    payment doc: {str(payment_doc_id)[:8]}…")
        else:
            print("    warning: no Payment document linked on order")

        order["_payment_doc_id"] = payment_doc_id
        return order

    async def verify_payment(self, payment_doc_id: str, transaction_id: str) -> None:
        now = datetime.now(UTC).isoformat()
        response = await self.client.patch(
            f"{BASE_URL}/payments/{payment_doc_id}/",
            json={
                "status": "verified",
                "transaction_id": transaction_id,
                "received_at": now,
                "confirmed_at": now,
            },
        )
        if response.status_code not in (200, 201):
            print(f"  Warning: payment verify failed: {response.text[:200]}")
            return
        print(f"  payment {payment_doc_id[:8]}… marked verified")

    async def seed_commerce_flow(self) -> None:
        print("\n[3/5] Active cart (guest) + CartItems")
        print("-" * 40)
        await self.create_cart(SEED_SESSION_ACTIVE, ACTIVE_CART_ITEMS)

        print("\n[4/5] Order from cart → OrderItems (embedded) + Payment (pending)")
        print("-" * 40)
        pending_cart = await self.create_cart(SEED_SESSION_ORDER_PENDING, ORDER_PENDING_CART_ITEMS)
        pending_order = await self.create_order_from_cart(
            extract_resource_id(pending_cart, "pending_cart"),
            notes="Seed order — awaiting customer UPI payment",
        )

        print("\n[5/5] Order from cart → verified Payment")
        print("-" * 40)
        paid_cart = await self.create_cart(SEED_SESSION_ORDER_PAID, ORDER_PAID_CART_ITEMS)
        transaction_id = "UPI-SEED-20260519-001"
        paid_order = await self.create_order_from_cart(
            extract_resource_id(paid_cart, "paid_cart"),
            payment_id=transaction_id,
            status="processing",
            notes="Seed order — payment submitted and verified",
        )
        payment_doc_id = paid_order.get("_payment_doc_id")
        if payment_doc_id:
            await self.verify_payment(payment_doc_id, transaction_id)

        print("\n[Summary]")
        print("-" * 40)
        print(f"  Active cart session:     {SEED_SESSION_ACTIVE}")
        print(f"  Pending order session:   {SEED_SESSION_ORDER_PENDING}")
        print(f"  Paid order session:      {SEED_SESSION_ORDER_PAID}")
        print(f"  Demo customer email:     {SEED_CUSTOMER['customer_email']}")
        print(f"  Pending order id:        {pending_order.get('id')}")
        print(f"  Paid order id:           {paid_order.get('id')}")


async def main() -> None:
    print("\nSoul Craft Studio — API Seeder")
    print("=" * 45)

    seeder = APISeeder()
    if not await seeder.check_connectivity():
        print("\nStart the API first:  docker compose up   (or uvicorn main:app --reload)")
        await seeder.close()
        sys.exit(1)

    try:
        await seeder.cleanup_commerce_data()
        await seeder.seed_categories()
        await seeder.seed_products()
        await seeder.seed_commerce_flow()
    except (RuntimeError, ValueError) as error:
        print(f"\nSeeding failed: {error}")
        sys.exit(1)
    finally:
        await seeder.close()

    print("\nSeeding complete.\n")


if __name__ == "__main__":
    asyncio.run(main())
