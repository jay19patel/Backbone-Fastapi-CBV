import asyncio
import httpx
import random
import time
import os
from typing import List, Optional
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = "http://127.0.0.1:8000"

NUM_USERS = 50
BLOGS_PER_USER = 50
CONCURRENT_REQUESTS = 3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_PATH = os.path.join(BASE_DIR, "blog.png")
PROFILE_IMAGE_PATH = os.path.join(BASE_DIR, "profile.png")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def upload_image(
    client: httpx.AsyncClient,
    token: str,
    file_path: str = None,
    url: str = None,
    collection: str = None,
    doc_id: str = None,
    field: str = None,
) -> Optional[str]:
    f = None
    try:
        data = {}
        if collection:
            data["collection_name"] = collection
        if doc_id:
            data["document_id"] = doc_id
        if field:
            data["field_name"] = field

        headers = {"Authorization": f"Bearer {token}"}

        if file_path:
            f = open(file_path, "rb")
            files = {"file": (os.path.basename(file_path), f, "image/jpeg")}
            resp = await client.post(f"{BASE_URL}/api/media/upload", files=files, data=data, headers=headers)
        elif url:
            data["url"] = url
            resp = await client.post(f"{BASE_URL}/api/media/upload", data=data, headers=headers)
        else:
            return None

        if resp.status_code == 200:
            att_id = resp.json().get("id")
            print(f"  ✔ Uploaded → attachment id: {att_id}")
            return att_id
        else:
            print(f"  ✘ Upload failed {resp.status_code}: {resp.text[:120]}")
    except Exception as e:
        print(f"  ✘ Upload error: {e}")
    finally:
        if f:
            f.close()
    return None


async def register_and_login(client: httpx.AsyncClient, i: int) -> Optional[dict]:
    ts = int(time.time())
    email = f"user{i}_{ts}@test.com"
    payload = {"email": email, "password": "password123", "full_name": f"Test User {i}"}

    print(f"\n[User {i}] Registering {email}...")
    resp = await client.post(f"{BASE_URL}/api/auth/register", json=payload)

    if resp.status_code not in (201, 400):
        print(f"  ✘ Register failed: {resp.text}")
        return None

    login = await client.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "password123"})
    if login.status_code != 200:
        print(f"  ✘ Login failed: {login.text}")
        return None

    auth = login.json()
    print(f"  ✔ Logged in. Token: {auth['access_token'][:20]}...")
    return auth


async def get_me(client: httpx.AsyncClient, token: str) -> Optional[dict]:
    resp = await client.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    if resp.status_code == 200:
        return resp.json()
    print(f"  ✘ /me failed: {resp.text}")
    return None


async def create_category(client: httpx.AsyncClient, token: str, idx: int) -> Optional[str]:
    ts = int(time.time() * 1000)
    headers = {"Authorization": f"Bearer {token}"}
    data = {"name": f"Category {idx} ({ts})", "slug": f"cat-{idx}-{ts}"}

    resp = await client.post(f"{BASE_URL}/api/blogs/categories/", json=data, headers=headers)
    if resp.status_code == 201:
        cat = resp.json()
        cat_id = cat.get("id") or cat.get("_id")
        print(f"  ✔ Category created: {data['name']} → {cat_id}")
        return cat_id
    print(f"  ✘ Category failed {resp.status_code}: {resp.text[:120]}")
    return None


async def create_blogs(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    user_name: str,
    cat_id: Optional[str],
    thumb_id: Optional[str],
    section_img_id: Optional[str],
) -> List[str]:
    headers = {"Authorization": f"Bearer {token}"}
    sem = asyncio.Semaphore(CONCURRENT_REQUESTS)
    topics = ["Python Patterns", "FastAPI Deep Dive", "AsyncIO Guide", "MongoDB with Beanie", "REST API Design"]

    async def _one(idx: int) -> Optional[str]:
        async with sem:
            topic = random.choice(topics)
            ts = int(time.time() * 1000) + idx
            slug = f"blog-{user_id[:8]}-{idx}-{ts}"
            body = {
                "title": f"Mastering {topic} — Part {idx + 1} by {user_name}",
                "subtitle": "A practical, hands-on guide with real-world examples",
                "slug": slug,
                "excerpt": f"Deep-dive into {topic}. Learn best practices and build production-ready code.",
                "introduction": "This guide covers everything from first principles to advanced patterns.",
                "sections": [
                    {"type": "text", "title": "Why This Matters", "content": f"Understanding {topic} is essential for modern backend development."},
                    {"type": "bullets", "title": "Key Concepts", "items": ["Type hints", "Async/await", "Dependency injection", "Pydantic models"]},
                    {"type": "code", "title": "Quick Example", "language": "python",
                     "content": "from fastapi import FastAPI\napp = FastAPI()\n\n@app.get('/')\nasync def root():\n    return {'message': 'Hello World'}"},
                    {"type": "image", "title": "Architecture", "attachment": section_img_id, "caption": "System overview"},
                    {"type": "note", "title": "Pro Tip", "content": "Always write tests alongside your code."},
                ],
                "conclusion": "Apply these concepts in your next project and level up your engineering skills.",
                "author": user_id,
                "category": cat_id,
                "thumbnail": thumb_id,
                "isPublished": True,
                "publishedDate": datetime.now(timezone.utc).isoformat(),
            }
            resp = await client.post(f"{BASE_URL}/api/blogs/", json=body, headers=headers)
            if resp.status_code == 201:
                d = resp.json()
                bid = d.get("id") or d.get("_id")
                print(f"  ✔ Blog created: {body['title'][:60]}… → {bid}")
                return bid
            print(f"  ✘ Blog {idx} failed {resp.status_code}: {resp.text[:120]}")
            return None

    results = await asyncio.gather(*[_one(i) for i in range(BLOGS_PER_USER)])
    return [r for r in results if r]


async def test_blog_list(client: httpx.AsyncClient):
    """Verify list endpoint and basic pagination."""
    resp = await client.get(f"{BASE_URL}/api/blogs/?page=1&page_size=5")
    assert resp.status_code == 200, f"Blog list failed: {resp.text}"
    data = resp.json()
    assert "results" in data, "Missing 'results' key in paginated response"
    assert "total" in data, "Missing 'total' key in paginated response"
    print(f"\n[Test] Blog list OK — total: {data['total']}, returned: {len(data['results'])}")


async def test_blog_detail(client: httpx.AsyncClient, slug: str):
    """Verify detail endpoint returns correct fields."""
    resp = await client.get(f"{BASE_URL}/api/blogs/{slug}")
    assert resp.status_code == 200, f"Blog detail failed for slug={slug}: {resp.text}"
    data = resp.json()
    for key in ["id", "title", "slug", "author", "sections"]:
        assert key in data, f"Missing key '{key}' in blog detail"
    print(f"[Test] Blog detail OK — slug: {data['slug']}, sections: {len(data.get('sections', []))}")


async def test_category_list(client: httpx.AsyncClient):
    resp = await client.get(f"{BASE_URL}/api/blogs/categories/?page=1&page_size=5")
    assert resp.status_code == 200, f"Category list failed: {resp.text}"
    data = resp.json()
    print(f"[Test] Category list OK — total: {data.get('total')}")


async def user_worker(i: int) -> List[str]:
    """One full user flow: register → upload → create category → create blogs."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        auth = await register_and_login(client, i)
        if not auth:
            return []

        token = auth["access_token"]
        me = await get_me(client, token)
        if not me:
            return []

        uid = me.get("id") or me.get("_id")
        uname = me.get("full_name", f"User {i}")

        # Upload profile image
        prof_id = await upload_image(client, token, PROFILE_IMAGE_PATH, collection="users", doc_id=uid, field="profile_image")

        # Upload blog thumbnail
        thumb_id = await upload_image(client, token, IMAGE_PATH, collection="blogs", field="thumbnail")

        # Upload section image (via picsum URL)
        section_url = f"https://picsum.photos/seed/{random.randint(1, 99999)}/800/600"
        section_img_id = await upload_image(client, token, url=section_url, collection="blogs", field="content")

        # Create category + blogs
        cat_id = await create_category(client, token, i)
        slugs_raw = await create_blogs(client, token, uid, uname, cat_id, thumb_id, section_img_id)
        return slugs_raw


async def clear_database():
    from backbone.core.settings import settings
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    await client.drop_database(settings.DATABASE_NAME)
    print(f"[DB] Dropped database '{settings.DATABASE_NAME}'")


async def main():
    print("=" * 60)
    print("  Backbone FastAPI — Blog Seed & Test Runner")
    print("=" * 60)

    # Check required files
    missing = [p for p in [IMAGE_PATH, PROFILE_IMAGE_PATH] if not os.path.exists(p)]
    if missing:
        print(f"[ERROR] Missing image files: {missing}")
        return

    await clear_database()

    # Run all user workers concurrently
    all_slugs: List[str] = []
    results = await asyncio.gather(*[user_worker(i) for i in range(NUM_USERS)])
    for slugs in results:
        all_slugs.extend(slugs)

    print(f"\n[Seed] Done. Created {len(all_slugs)} blogs across {NUM_USERS} users.")

    # --- API Tests ---
    print("\n--- Running API Tests ---")
    async with httpx.AsyncClient(timeout=30.0) as client:
        await test_blog_list(client)
        await test_category_list(client)
        if all_slugs:
            # Test detail using one of the created blog slugs
            slug = all_slugs[0]
            resp = await client.get(f"{BASE_URL}/api/blogs/?page=1&page_size=1")
            if resp.status_code == 200:
                results_list = resp.json().get("results", [])
                if results_list:
                    real_slug = results_list[0].get("slug") or results_list[0].get("id")
                    if real_slug:
                        await test_blog_detail(client, real_slug)

    print("\n✅ All tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
