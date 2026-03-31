import asyncio
import json
import os
import random
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backbone.core.settings import settings


# ---------------------------------------------------------------------------
# Test Config (edit directly here)
# ---------------------------------------------------------------------------
BASE_URL = "http://127.0.0.1:8000"
REQUEST_TIMEOUT = 90

# Heavy seed config (50 * 50 = 2500 blogs)
NUM_USERS = 1
BLOGS_PER_USER = 1
PLAYLISTS_PER_USER = 1

# Runtime concurrency controls
USER_WORKER_CONCURRENCY = 1
BLOG_CREATE_CONCURRENCY = 1

# Optional data toggles
CLEAR_DATABASE_BEFORE_RUN = True
CREATE_GLOBAL_FAQS = True
TESTIMONIAL_PROBABILITY = 0.25

# ── Blog JSON Seeding ────────────────────────────────────────────────────────
# When True: reads blog.json and creates NUM_BLOGS_FROM_JSON blogs.
# Each blog has the same content — only title changes (#1, #2, ...).
# BLOGS_PER_USER is ignored when SEED_FROM_JSON=True.
SEED_FROM_JSON = True
NUM_BLOGS_FROM_JSON = 5           # ← how many to generate
BLOG_JSON_PATH = os.path.join(CURRENT_DIR, "blog.json")
# ────────────────────────────────────────────────────────────────────────────

# Files
IMAGE_PATH = os.path.join(CURRENT_DIR, "blog.png")
PROFILE_IMAGE_PATH = os.path.join(CURRENT_DIR, "profile.png")
PLAYLIST_IMAGE_PATH = os.path.join(CURRENT_DIR, "playlist.png")


class APITestFailure(RuntimeError):
    pass


def _load_blog_json() -> dict:
    """Load blog.json template for JSON-based seeding."""
    if not os.path.exists(BLOG_JSON_PATH):
        raise APITestFailure(f"blog.json not found at: {BLOG_JSON_PATH}")
    with open(BLOG_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)

def _banner(text: str) -> None:
    print(f"\n{'=' * 78}\n{text}\n{'=' * 78}")


def _ok(text: str) -> None:
    print(f"  [OK] {text}")


def _warn(text: str) -> None:
    print(f"  [WARN] {text}")


def _fail(text: str) -> None:
    raise APITestFailure(text)


async def _assert_status(resp: httpx.Response, expected: List[int], label: str) -> None:
    if resp.status_code in expected:
        return
    _fail(f"{label} failed. status={resp.status_code}, body={resp.text[:500]}")


def _auth_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _require_assets() -> None:
    missing = [p for p in [IMAGE_PATH, PROFILE_IMAGE_PATH, PLAYLIST_IMAGE_PATH] if not os.path.exists(p)]
    if missing:
        _fail(f"Missing required test image assets: {missing}")


async def clear_database_if_enabled() -> None:
    if not CLEAR_DATABASE_BEFORE_RUN:
        _warn("Skipping DB wipe (CLEAR_DATABASE_BEFORE_RUN=False)")
        return

    _banner("Database Cleanup")
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{BASE_URL}/admin/api/wipe",
                json={
                    "email": "admin@test.com",
                    "password": "password123",
                    "create_admin_if_none": True,
                },
            )
            if resp.status_code == 200:
                _ok("Database wiped via admin API")
                return
            _warn(f"Admin wipe API failed ({resp.status_code}), using direct DB drop")
        except Exception as exc:
            _warn(f"Admin wipe API not reachable: {exc}. Using direct DB drop")

    mongo = AsyncIOMotorClient(settings.MONGODB_URL)
    try:
        await mongo.drop_database(settings.DATABASE_NAME)
        _ok(f"Dropped database directly: {settings.DATABASE_NAME}")
    finally:
        mongo.close()


async def health_check(client: httpx.AsyncClient) -> None:
    resp = await client.get(f"{BASE_URL}/")
    await _assert_status(resp, [200], "Health check")
    _ok("Server is reachable")


async def upload_image(
    client: httpx.AsyncClient,
    token: str,
    *,
    file_path: Optional[str] = None,
    url: Optional[str] = None,
    collection_name: Optional[str] = None,
    document_id: Optional[str] = None,
    field_name: Optional[str] = None,
) -> Optional[str]:
    if not file_path and not url:
        return None

    data: Dict[str, Any] = {}
    if collection_name:
        data["collection_name"] = collection_name
    if document_id:
        data["document_id"] = document_id
    if field_name:
        data["field_name"] = field_name

    headers = _auth_headers(token)

    file_handle = None
    try:
        if file_path:
            file_handle = open(file_path, "rb")
            files = {"file": (os.path.basename(file_path), file_handle, "image/png")}
            resp = await client.post(f"{BASE_URL}/api/media/upload", data=data, files=files, headers=headers)
        else:
            data["url"] = url
            resp = await client.post(f"{BASE_URL}/api/media/upload", data=data, headers=headers)

        await _assert_status(resp, [200], "Media upload")
        payload = resp.json()
        attachment_id = payload.get("id")
        if not attachment_id:
            _fail(f"Media upload response missing attachment id: {payload}")
        return str(attachment_id)
    finally:
        if file_handle:
            file_handle.close()


async def register_and_login(client: httpx.AsyncClient, run_id: str, idx: int) -> Dict[str, str]:
    email = f"apitest_{run_id}_{idx}@example.com"
    password = "password123"
    full_name = f"API Test User {idx}"

    reg = await client.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password, "full_name": full_name},
    )
    await _assert_status(reg, [201], f"Register user {idx}")

    login = await client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
    )
    await _assert_status(login, [200], f"Login user {idx}")
    token = login.json().get("access_token")
    if not token:
        _fail(f"Login missing access token for {email}")

    me = await client.get(f"{BASE_URL}/api/auth/me", headers=_auth_headers(token))
    await _assert_status(me, [200], f"/me user {idx}")
    me_json = me.json()
    user_id = str(me_json.get("id") or me_json.get("_id") or "")
    if not user_id:
        _fail(f"Could not resolve user id for {email}")

    return {
        "email": email,
        "password": password,
        "full_name": full_name,
        "token": token,
        "user_id": user_id,
    }


async def create_category(client: httpx.AsyncClient, token: str, run_id: str, idx: int, name: Optional[str] = None, slug: Optional[str] = None) -> str:
    ts = int(time.time() * 1000)
    payload = {
        "name": name or f"API Category {run_id}-{idx}-{ts}",
        "slug": slug or f"api-cat-{run_id}-{idx}-{ts}",
    }
    resp = await client.post(
        f"{BASE_URL}/api/blogs/categories/",
        json=payload,
        headers=_auth_headers(token),
    )
    await _assert_status(resp, [201], f"Create category user={idx}")
    data = resp.json()
    category_id = str(data.get("id") or data.get("_id") or "")
    if not category_id:
        _fail(f"Category id missing for user {idx}")
    return category_id


async def create_blogs(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    category_id: str,
    thumb_attachment_id: Optional[str],
    section_image_attachment_id: Optional[str],
    run_id: str,
    idx: int,
) -> Dict[str, List[str]]:
    blog_ids: List[str] = []
    blog_slugs: List[str] = []
    sem = asyncio.Semaphore(BLOG_CREATE_CONCURRENCY)

    # ── JSON-based seeding (from blog.json) ─────────────────────────────────
    if SEED_FROM_JSON:
        template = _load_blog_json()
        base_title = template["title"]
        count = NUM_BLOGS_FROM_JSON

        async def _create_from_json(blog_index: int) -> Optional[Dict[str, str]]:
            async with sem:
                title = f"{base_title}" if blog_index == 1 else f"{base_title} #{blog_index}"
                # Use a predictable slug for the first/main blog
                if blog_index == 1:
                    slug = template.get("category_slug", "tech") + "-" + template.get("title", "guide").lower().replace(":", "").replace(" ", "-")
                else:
                    slug = f"fastapi-vs-django-{run_id}-{idx}-{blog_index}-{uuid.uuid4().hex[:8]}"
                
                payload = {
                    "title": title,
                    "subtitle": template.get("subtitle", ""),
                    "slug": slug,
                    "excerpt": template.get("excerpt", ""),
                    "introduction": template.get("introduction", ""),
                    "sections": template.get("sections", []),
                    "conclusion": template.get("conclusion", ""),
                    "author": user_id,
                    "category": category_id,
                    "thumbnail": thumb_attachment_id,
                    "isPublished": True,
                    "publishedDate": datetime.now(timezone.utc).isoformat(),
                }
                resp = await client.post(
                    f"{BASE_URL}/api/blogs/",
                    json=payload,
                    headers=_auth_headers(token),
                )
                await _assert_status(resp, [201], f"Create JSON blog user={idx} blog={blog_index}")
                data = resp.json()
                blog_id = str(data.get("id") or data.get("_id") or "")
                blog_slug = str(data.get("slug") or "")
                if not blog_id or not blog_slug:
                    _fail(f"Blog response missing id/slug user={idx}, blog={blog_index}, data={data}")
                _ok(f"Blog #{blog_index}: \"{title}\"")
                return {"id": blog_id, "slug": blog_slug}

        created = await asyncio.gather(*[_create_from_json(i) for i in range(1, count + 1)])

    # ── Original random-topic seeding ────────────────────────────────────────
    else:
        topics = ["FastAPI", "Beanie", "Redis Jobs", "MongoDB", "Auth", "Playlists", "Attachments"]
        count = BLOGS_PER_USER

        async def _create_one(blog_index: int) -> Optional[Dict[str, str]]:
            async with sem:
                topic = random.choice(topics)
                slug = f"api-blog-{run_id}-{idx}-{blog_index}-{uuid.uuid4().hex[:8]}"
                payload = {
                    "title": f"{topic} Guide U{idx}B{blog_index}",
                    "subtitle": "High-volume API integration content",
                    "slug": slug,
                    "excerpt": f"Generated for run {run_id}.",
                    "introduction": "Automated blog creation for integration test.",
                    "sections": [
                        {
                            "type": "text",
                            "title": "Overview",
                            "content": f"This is generated content for topic={topic}, user={idx}, blog={blog_index}.",
                        },
                        {
                            "type": "bullets",
                            "title": "Checklist",
                            "items": ["Design schema", "Implement API", "Validate response", "Deploy safely"],
                        },
                        {
                            "type": "code",
                            "title": "Code Sample",
                            "language": "python",
                            "content": "async def ping():\n    return {'ok': True}",
                        },
                        {
                            "type": "image",
                            "title": "Attachment Section",
                            "attachment": section_image_attachment_id,
                            "caption": "Uploaded through /api/media/upload",
                        },
                        {
                            "type": "note",
                            "title": "Run Metadata",
                            "content": f"run_id={run_id}, user={idx}, blog={blog_index}",
                        },
                    ],
                    "conclusion": "Automated blog generation completed.",
                    "author": user_id,
                    "category": category_id,
                    "thumbnail": thumb_attachment_id,
                    "isPublished": True,
                    "publishedDate": datetime.now(timezone.utc).isoformat(),
                }
                resp = await client.post(
                    f"{BASE_URL}/api/blogs/",
                    json=payload,
                    headers=_auth_headers(token),
                )
                await _assert_status(resp, [201], f"Create blog user={idx} blog={blog_index}")
                data = resp.json()
                blog_id = str(data.get("id") or data.get("_id") or "")
                blog_slug = str(data.get("slug") or "")
                if not blog_id or not blog_slug:
                    _fail(f"Blog response missing id/slug user={idx}, blog={blog_index}, data={data}")
                return {"id": blog_id, "slug": blog_slug}

        created = await asyncio.gather(*[_create_one(i) for i in range(count)])

    for item in created:
        if not item:
            continue
        blog_ids.append(item["id"])
        blog_slugs.append(item["slug"])

    return {"blog_ids": blog_ids, "blog_slugs": blog_slugs}


async def create_playlists(
    client: httpx.AsyncClient,
    token: str,
    owner_id: str,
    blog_ids: List[str],
    playlist_thumb_attachment_id: Optional[str],
    run_id: str,
    idx: int,
) -> List[str]:
    playlist_ids: List[str] = []
    for i in range(PLAYLISTS_PER_USER):
        selected = random.sample(blog_ids, k=min(5, len(blog_ids))) if blog_ids else []
        payload = {
            "owner": owner_id,
            "name": f"Playlist {run_id}-{idx}-{i}",
            "slug": f"playlist-{run_id}-{idx}-{i}-{uuid.uuid4().hex[:8]}",
            "description": "Generated playlist from automated API integration test.",
            "thumbnail": playlist_thumb_attachment_id,
            "blogs": selected,
            "is_public": True,
        }
        resp = await client.post(
            f"{BASE_URL}/api/playlists/",
            json=payload,
            headers=_auth_headers(token),
        )
        await _assert_status(resp, [201], f"Create playlist user={idx} playlist={i}")
        data = resp.json()
        playlist_id = str(data.get("id") or data.get("_id") or "")
        if not playlist_id:
            _fail(f"Playlist response missing id user={idx}, playlist={i}, data={data}")
        playlist_ids.append(playlist_id)
    return playlist_ids


async def create_testimonial(client: httpx.AsyncClient, token: str, user_id: str, idx: int) -> None:
    payload = {
        "user": user_id,
        "content": f"Automated testimonial from user {idx}. The platform flow works well.",
    }
    resp = await client.post(
        f"{BASE_URL}/api/testimonials/",
        json=payload,
        headers=_auth_headers(token),
    )
    await _assert_status(resp, [201], f"Create testimonial user={idx}")


async def create_global_faqs(client: httpx.AsyncClient, token: str, run_id: str) -> None:
    faqs = [
        {"question": f"[{run_id}] How to create a blog?", "answer": "Use POST /api/blogs/ with required fields."},
        {"question": f"[{run_id}] How to upload image?", "answer": "Use POST /api/media/upload with multipart file."},
        {"question": f"[{run_id}] How to create playlist?", "answer": "Use POST /api/playlists/ with blog ids."},
        {"question": f"[{run_id}] How to use store page?", "answer": "Open /pages/store-test and submit key/value."},
    ]
    for faq in faqs:
        resp = await client.post(f"{BASE_URL}/api/faqs/", json=faq, headers=_auth_headers(token))
        await _assert_status(resp, [201], "Create FAQ")


async def verify_store_page_form(client: httpx.AsyncClient, run_id: str) -> None:
    key = f"apitest_banner_{run_id}"
    value = f"Store value from heavy run {run_id}"

    post_resp = await client.post(
        f"{BASE_URL}/pages/store-test/",
        data={"key": key, "value": value},
    )
    await _assert_status(post_resp, [200], "Store page POST")
    if value not in post_resp.text:
        _fail("Store POST page does not contain saved value")

    get_resp = await client.get(f"{BASE_URL}/pages/store-test/?key={key}")
    await _assert_status(get_resp, [200], "Store page GET")
    if value not in get_resp.text:
        _fail("Store GET page does not render saved value")


async def verify_counts_and_logs(run_id: str, run_emails: List[str]) -> None:
    mongo = AsyncIOMotorClient(settings.MONGODB_URL)
    try:
        db = mongo[settings.DATABASE_NAME]
        # Blog slug prefix differs between JSON mode and random mode
        if SEED_FROM_JSON:
            template = _load_blog_json()
            # Deterministic slug for #1 + random ones for the rest
            main_slug = template.get("category_slug", "tech") + "-" + template.get("title", "guide").lower().replace(":", "").replace(" ", "-")
            blog_slug_pattern = f"(^{main_slug}$|^fastapi-vs-django-{run_id}-)"
            expected_blogs = NUM_USERS * NUM_BLOGS_FROM_JSON
        else:
            blog_slug_pattern = f"^api-blog-{run_id}-"
            expected_blogs = NUM_USERS * BLOGS_PER_USER

        template = _load_blog_json() if SEED_FROM_JSON else {}
        custom_cat_slug = template.get("category_slug")
        
        blog_count = await db["blogs"].count_documents({"slug": {"$regex": blog_slug_pattern}})
        playlist_count = await db["playlists"].count_documents({"slug": {"$regex": f"^playlist-{run_id}-"}})
        
        if custom_cat_slug:
            category_count = await db["blog_categories"].count_documents({"slug": custom_cat_slug})
        else:
            category_count = await db["blog_categories"].count_documents({"slug": {"$regex": f"^api-cat-{run_id}-"}})

        expected_playlists = NUM_USERS * PLAYLISTS_PER_USER
        expected_categories = NUM_USERS

        if blog_count < expected_blogs:
            _fail(f"Blogs count mismatch. expected>={expected_blogs}, actual={blog_count}")
        if playlist_count < expected_playlists:
            _fail(f"Playlists count mismatch. expected>={expected_playlists}, actual={playlist_count}")
        if category_count < expected_categories:
            _fail(f"Categories count mismatch. expected>={expected_categories}, actual={category_count}")

        # Each register triggers 2 default emails (welcome + welcome pack)
        for email in run_emails:
            email_docs = await db["email_delivery_logs"].find({"to_email": email}).to_list(20)
            if len(email_docs) < 2:
                _fail(f"Email logs missing for {email}. expected>=2, actual={len(email_docs)}")

        _ok(
            f"Verified DB counts and email logs. blogs={blog_count}, playlists={playlist_count}, "
            f"categories={category_count}, users={len(run_emails)}"
        )
    finally:
        mongo.close()


async def verify_public_list_endpoints(client: httpx.AsyncClient) -> None:
    blogs = await client.get(f"{BASE_URL}/api/blogs/?page=1&page_size=10")
    await _assert_status(blogs, [200], "List blogs")
    categories = await client.get(f"{BASE_URL}/api/blogs/categories/?page=1&page_size=10")
    await _assert_status(categories, [200], "List categories")
    playlists = await client.get(f"{BASE_URL}/api/playlists/?page=1&page_size=10")
    await _assert_status(playlists, [200], "List playlists")


async def user_worker(index: int, run_id: str, sem: asyncio.Semaphore) -> Dict[str, Any]:
    async with sem:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            auth = await register_and_login(client, run_id, index)
            token = auth["token"]
            user_id = auth["user_id"]

            # Profile image attachment
            await upload_image(
                client,
                token,
                file_path=PROFILE_IMAGE_PATH,
                collection_name="users",
                document_id=user_id,
                field_name="profile_image",
            )

            # Blog attachments
            blog_thumb_id = await upload_image(
                client,
                token,
                file_path=IMAGE_PATH,
                collection_name="blogs",
                field_name="thumbnail",
            )
            blog_section_attachment_id = await upload_image(
                client,
                token,
                file_path=IMAGE_PATH,
                collection_name="blogs",
                field_name="sections",
            )

            # Playlist attachment
            playlist_thumb_id = await upload_image(
                client,
                token,
                file_path=PLAYLIST_IMAGE_PATH,
                collection_name="playlists",
                field_name="thumbnail",
            )

            template = _load_blog_json() if SEED_FROM_JSON else {}
            category_id = await create_category(
                client, 
                token, 
                run_id, 
                index,
                name=template.get("category_name"),
                slug=template.get("category_slug")
            )
            blog_data = await create_blogs(
                client,
                token=token,
                user_id=user_id,
                category_id=category_id,
                thumb_attachment_id=blog_thumb_id,
                section_image_attachment_id=blog_section_attachment_id,
                run_id=run_id,
                idx=index,
            )

            playlist_ids = await create_playlists(
                client,
                token=token,
                owner_id=user_id,
                blog_ids=blog_data["blog_ids"],
                playlist_thumb_attachment_id=playlist_thumb_id,
                run_id=run_id,
                idx=index,
            )

            if random.random() < TESTIMONIAL_PROBABILITY:
                await create_testimonial(client, token, user_id, index)

            return {
                "email": auth["email"],
                "user_id": user_id,
                "category_id": category_id,
                "blog_ids": blog_data["blog_ids"],
                "blog_slugs": blog_data["blog_slugs"],
                "playlist_ids": playlist_ids,
            }


async def main() -> None:
    _require_assets()
    run_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"

    _banner("Backbone Heavy Integration Test")
    print(f"BASE_URL={BASE_URL}")
    print(f"DATABASE={settings.DATABASE_NAME}")
    print(
        "CONFIG: "
        f"users={NUM_USERS}, blogs_per_user={BLOGS_PER_USER}, playlists_per_user={PLAYLISTS_PER_USER}, "
        f"user_concurrency={USER_WORKER_CONCURRENCY}, blog_concurrency={BLOG_CREATE_CONCURRENCY}"
    )

    await clear_database_if_enabled()

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        await health_check(client)

    worker_sem = asyncio.Semaphore(USER_WORKER_CONCURRENCY)
    results = await asyncio.gather(*[user_worker(i, run_id, worker_sem) for i in range(NUM_USERS)])

    all_emails = [r["email"] for r in results]
    total_blogs = sum(len(r["blog_ids"]) for r in results)
    total_playlists = sum(len(r["playlist_ids"]) for r in results)
    _ok(f"Seeded users={len(results)}, blogs={total_blogs}, playlists={total_playlists}")

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        if CREATE_GLOBAL_FAQS and results:
            # Create FAQs using first user's token
            first_email = results[0]["email"]
            first_auth = await client.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": first_email, "password": "password123"},
            )
            await _assert_status(first_auth, [200], "Re-login first user for FAQ creation")
            await create_global_faqs(client, first_auth.json()["access_token"], run_id)
            _ok("Global FAQs created")

        await verify_public_list_endpoints(client)
        await verify_store_page_form(client, run_id)

    await verify_counts_and_logs(run_id, all_emails)
    _banner("All Tests Passed")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except APITestFailure as exc:
        print(f"\n[FAIL] {exc}")
        raise SystemExit(1)
    except Exception as exc:
        print(f"\n[UNEXPECTED ERROR] {exc}")
        raise SystemExit(1)
