import asyncio
import httpx
import random
import time
from typing import List, Optional
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
import os

BASE_URL = "http://127.0.0.1:8000"

# Configuration
NUM_USERS = 10
TOTAL_BLOGS_PER_USER = 10  # 10 users * 10 blogs = 100 total blogs
TOTAL_PLAYLISTS_PER_USER = 2 # 10 users * 2 playlists = 20 total playlists
CONCURRENT_REQUESTS = 5

IMAGE_PATH = "bg.jpg" # Required for blogs
PROFILE_IMAGE_PATH = "profile.jpg" # Required for users

async def upload_image(client: httpx.AsyncClient, token: str, file_path: str, collection: str = None, doc_id: str = None, field: str = None) -> Optional[str]:
    try:
        filename = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            files = {"file": (filename, f, "image/jpeg")}
            data = {}
            if collection: data["collection_name"] = collection
            if doc_id: data["document_id"] = doc_id
            if field: data["field_name"] = field
            
            headers = {"Authorization": f"Bearer {token}"}
            resp = await client.post(f"{BASE_URL}/api/media/upload/image", files=files, data=data, headers=headers)
            if resp.status_code == 200:
                resp_data = resp.json()
                attachment_id = resp_data.get("id")
                print(f"Upload initiated for {filename}. Attachment ID: {attachment_id}")
                return attachment_id
            else:
                print(f"Failed to upload {filename}: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"Error uploading {file_path}: {e}")
    return None

async def update_user_profile(client: httpx.AsyncClient, token: str, user_id: str, attachment_id: str):
    headers = {"Authorization": f"Bearer {token}"}
    try:
        # Since field is Link[Attachment], we pass the attachment ID
        resp = await client.patch(f"{BASE_URL}/api/user/{user_id}", json={"profile_image": attachment_id}, headers=headers)
        if resp.status_code == 200:
            print(f"User {user_id} profile updated with attachment link.")
        else:
            print(f"Failed to update user profile: {resp.text}")
    except Exception as e:
        print(f"Error updating user: {e}")

async def register_user(client: httpx.AsyncClient, i: int) -> dict:
    ts = int(time.time())
    user_data = {
        "email": f"user{i}_{ts}@test.com",
        "password": "password123",
        "full_name": f"Test User {i}",
        "headline": f"Top Author Level {i}",
        "bio": f"I am a passionate writer testing this out."
    }
    try:
        print(f"Registering User {i}...")
        resp = await client.post(f"{BASE_URL}/auth/register", json=user_data)
        if resp.status_code == 201:
            login_resp = await client.post(f"{BASE_URL}/auth/login", json={"email": user_data["email"], "password": user_data["password"]})
            return login_resp.json()
        elif resp.status_code == 400:
             login_resp = await client.post(f"{BASE_URL}/auth/login", json={"email": user_data["email"], "password": user_data["password"]})
             if login_resp.status_code == 200:
                 return login_resp.json()
        print(f"Failed to register user {i}: {resp.text}")
    except Exception as e:
        print(f"Error user {i}: {e}")
    return None

async def create_category(client: httpx.AsyncClient, token: str, i: int) -> str:
    headers = {"Authorization": f"Bearer {token}"}
    ts = int(time.time() * 1000)
    # 1. Create Parent Category
    parent_data = {"name": f"Main Category {i}", "slug": f"main-cat-{i}-{ts}"}
    try:
        resp = await client.post(f"{BASE_URL}/api/blogs/categories/", json=parent_data, headers=headers)
        if resp.status_code == 201:
             data = resp.json()
             parent_id = data.get("id") or data.get("_id")
             # 2. Create Sub Category
             sub_data = {"name": f"Sub Category {i}", "slug": f"sub-cat-{ts+1}"}
             sub_resp = await client.post(f"{BASE_URL}/api/blogs/categories/", json=sub_data, headers=headers)
             if sub_resp.status_code == 201:
                 sub_data_resp = sub_resp.json()
                 cat_id = sub_data_resp.get("id") or sub_data_resp.get("_id")
                 print(f"Sub-category created: {cat_id}")
                 return cat_id
             return parent_id
        else:
            print(f"Failed to create category: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"Error creating category: {e}")
    return None 

async def create_blogs(client: httpx.AsyncClient, token: str, user_id: str, num_blogs: int, category_id: str, image_url: str) -> List[str]:
    headers = {"Authorization": f"Bearer {token}"}
    
    sem = asyncio.Semaphore(CONCURRENT_REQUESTS)

    async def _create_one(idx):
        async with sem:
            now_iso = datetime.now(timezone.utc).isoformat()
            blog_data = {
                "title": f"Blog Post {idx} by User {user_id}",
                "subtitle": f"An engaging subtitle for blog post {idx} to test the API thoroughly.",
                "slug": f"blog-post-{user_id}-{idx}-{int(time.time())}-{random.randint(1000, 9999)}",
                "excerpt": f"This is an excerpt summarizing the key takeaways for blog post {idx}.",
                "introduction": "Welcome to this dummy blog post. We are generating lots of dummy text to make it realistic.",
                "sections": [
                    {
                        "type": "paragraph",
                        "content": f"This is the first main section of blog {idx}. Here is some detailed content to flesh out the body. " * 3
                    },
                    {
                        "type": "image",
                        "url": image_url,
                        "caption": "A cool dummy image for this section"
                    },
                    {
                        "type": "paragraph",
                        "content": "Another paragraph with more details to ensure we cover all required lengths. " * 3
                    }
                ],
                "conclusion": "In conclusion, this setup should perfectly populate the blog with all necessary real-world fields.",
                "author": str(user_id),
                "category": category_id if category_id else None,
                "thumbnail": image_url,
                "isPublished": True,
                "publishedDate": now_iso,
                "embedding": [random.uniform(0, 1) for _ in range(10)]
            }
            try:
                resp = await client.post(f"{BASE_URL}/api/blogs/", json=blog_data, headers=headers)
                if resp.status_code == 201:
                    data = resp.json()
                    return data.get("_id") or data.get("id")
                return None
            except Exception as e:
                return None

    print(f"User {user_id} starting {num_blogs} blogs creation...")
    tasks = [_create_one(i) for i in range(num_blogs)]
    results = await asyncio.gather(*tasks)
    created_ids = [r for r in results if r]
    return created_ids

async def create_playlists(client: httpx.AsyncClient, token: str, user_id: str, num_playlists: int, blog_ids: List[str], image_url: str):
    headers = {"Authorization": f"Bearer {token}"}
    
    sem = asyncio.Semaphore(CONCURRENT_REQUESTS)

    async def _create_one(idx):
        async with sem:
            playlist_blogs = random.sample(blog_ids, min(len(blog_ids), 3))
            
            playlist_data = {
                "name": f"Playlist {idx} by {user_id}",
                "slug": f"playlist-{user_id}-{idx}-{random.randint(1000, 9999)}",
                "description": "My awesome playlist of blogs.",
                "thumbnail": image_url,
                "blogs": playlist_blogs,
                "owner": str(user_id)
            }
            try:
                resp = await client.post(f"{BASE_URL}/api/playlists/", json=playlist_data, headers=headers)
                if resp.status_code == 201:
                    data = resp.json()
                    return data.get("_id") or data.get("id")
                return None
            except Exception as e:
                return None

    print(f"User {user_id} starting {num_playlists} playlists creation...")
    tasks = [_create_one(i) for i in range(num_playlists)]
    results = await asyncio.gather(*tasks)
    created_ids = [r for r in results if r]
    return created_ids

async def user_worker(i: int):
    async with httpx.AsyncClient(timeout=60.0) as client:
        # 1. Auth & Register
        auth_data = await register_user(client, i)
        if not auth_data:
            return
        
        token = auth_data["access_token"]
        
        # Get User ID
        headers = {"Authorization": f"Bearer {token}"}
        me_resp = await client.get(f"{BASE_URL}/auth/me", headers=headers)
        if me_resp.status_code != 200:
            print(f"Failed to get me: {me_resp.text}")
            return
        real_user_id = me_resp.json()["_id"]
        
        # 2. Upload Profile Image
        print(f"User {i} uploading profile image...")
        prof_att_id = await upload_image(client, token, PROFILE_IMAGE_PATH, collection="users", doc_id=real_user_id, field="profile_image")
        if prof_att_id:
            await update_user_profile(client, token, real_user_id, prof_att_id)
            
        # 3. Upload Blog Image
        print(f"User {i} uploading blog background image...")
        image_att_id = await upload_image(client, token, IMAGE_PATH, collection="blogs", field="thumbnail")
        if not image_att_id:
            return
            
        # 4. Content Creation
        cat_id = await create_category(client, token, i)
        blog_ids = await create_blogs(client, token, real_user_id, TOTAL_BLOGS_PER_USER, cat_id, image_att_id)
        if blog_ids:
             await create_playlists(client, token, real_user_id, TOTAL_PLAYLISTS_PER_USER, blog_ids, image_att_id)

async def clear_database():
    try:
        client = AsyncIOMotorClient("mongodb://localhost:27017")
        await client.drop_database("backbone_app")
        print("Database 'backbone_app' cleared successfully.")
    except Exception as e:
        print(f"Error clearing database: {e}")


async def main():
    print(f"Starting Content Generation:")
    if not os.path.exists(IMAGE_PATH) or not os.path.exists(PROFILE_IMAGE_PATH):
        print(f"Error: {IMAGE_PATH} or {PROFILE_IMAGE_PATH} not found.")
        return

    await clear_database()
    tasks = [user_worker(i) for i in range(NUM_USERS)]
    
    start_time = time.time()
    await asyncio.gather(*tasks)
    end_time = time.time()
    
    print(f"\n--- Total Generation Time: {end_time - start_time:.2f}s ---")

if __name__ == "__main__":
    asyncio.run(main())
