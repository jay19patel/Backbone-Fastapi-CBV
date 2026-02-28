import asyncio
import httpx
import random
import time
from typing import List
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = "http://127.0.0.1:8000"

# Configuration
NUM_USERS = 5
TOTAL_BLOGS_PER_USER = 500  # Total 500 blogs
CONCURRENT_REQUESTS = 50     # Batch size for concurrency

async def register_user(client: httpx.AsyncClient, i: int) -> dict:
    ts = int(time.time())
    user_data = {
        "email": f"user{i}_{ts}@test.com",
        "username": f"user{i}_{ts}",
        "password": "password123",
        "full_name": f"Test User {i}"
    }
    try:
        # Try login first to perform idempotent run
        login_resp = await client.post(f"{BASE_URL}/auth/login", json={"email": user_data["email"], "password": user_data["password"]})
        if login_resp.status_code == 200:
            print(f"User {i} logged in.")
            return login_resp.json()
            
        print(f"Registering User {i}...")
        resp = await client.post(f"{BASE_URL}/auth/register", json=user_data)
        if resp.status_code == 201:
            # Login after register
            login_resp = await client.post(f"{BASE_URL}/auth/login", json={"email": user_data["email"], "password": user_data["password"]})
            return login_resp.json()
        elif resp.status_code == 400:
             print(f"User {i} already exists (400). Logging in...")
             login_resp = await client.post(f"{BASE_URL}/auth/login", json={"email": user_data["email"], "password": user_data["password"]})
             if login_resp.status_code == 200:
                 return login_resp.json()
                 
        print(f"Failed to register user {i}: {resp.text}")
    except Exception as e:
        print(f"Error user {i}: {e}")
    return None

async def create_category(client: httpx.AsyncClient, token: str, i: int) -> str:
    headers = {"Authorization": f"Bearer {token}"}
    cat_data = {"name": f"Category {i}", "slug": f"cat-{i}-{random.randint(1000, 9999)}"}
    try:
        resp = await client.post(f"{BASE_URL}/blog-categories/", json=cat_data, headers=headers)
        if resp.status_code == 201:
             return resp.json().get("_id") or resp.json().get("id")
    except:
        pass
    return None 

async def create_blogs(client: httpx.AsyncClient, token: str, user_id: str, num_blogs: int, category_id: str) -> List[str]:
    headers = {"Authorization": f"Bearer {token}"}
    
    # Semaphore for concurrency control
    sem = asyncio.Semaphore(CONCURRENT_REQUESTS)

    async def _create_one(idx):
        async with sem:
            blog_data = {
                "title": f"Blog Post {idx} by User {user_id}",
                "content": f"This is some realistic content for blog post {idx}. " * 10,
                "categories": [category_id] if category_id else [],
                "author": str(user_id),
                "tags": [f"tag{idx}", "test", "load"]
            }
            try:
                # We need to pass author ID.
                # Let's fix user_worker to capture ID.
                resp = await client.post(f"{BASE_URL}/blogs/", json=blog_data, headers=headers)
                if resp.status_code == 201:
                    data = resp.json()
                    return data.get("_id") or data.get("id")
                # Print error for first few failures
                if idx < 5:
                    print(f"Blog create failed {idx}: {resp.status_code} - {resp.text}")
                return None
            except Exception as e:
                print(f"Req Error: {e}")
                return None

    print(f"User {user_id} starting {num_blogs} blogs creation...")
    start = time.time()
    
    tasks = [_create_one(i) for i in range(num_blogs)]
    results = await asyncio.gather(*tasks)
    created_ids = [r for r in results if r]
    
    end = time.time()
    print(f"User {user_id} finished. Created: {len(created_ids)}/{num_blogs}. Time: {end-start:.2f}s")
    return created_ids

async def read_blogs(client: httpx.AsyncClient, token: str):
    # READ All
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = await client.get(f"{BASE_URL}/blogs/", headers=headers)
        if resp.status_code == 200:
            count = len(resp.json())
            print(f"Successfully fetched {count} blogs via GET overall.")
    except Exception as e:
        print(f"Error fetching blogs: {e}")

async def test_crud_single_blog(client: httpx.AsyncClient, token: str, blog_id: str):
    headers = {"Authorization": f"Bearer {token}"}
    
    # READ Single
    try:
        resp = await client.get(f"{BASE_URL}/blogs/{blog_id}", headers=headers)
        if resp.status_code == 200:
            print(f"Successfully picked single blog {blog_id} via GET.")
        else:
            print(f"Failed to read single blog: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"Error reading single blog: {e}")

    # UPDATE Single
    try:
        update_data = {"title": f"Updated Blog Title {random.randint(100, 999)}"}
        resp = await client.patch(f"{BASE_URL}/blogs/{blog_id}", json=update_data, headers=headers)
        if resp.status_code == 200:
            print(f"Successfully updated single blog {blog_id} via PATCH.")
        else:
            print(f"Failed to update single blog: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"Error updating single blog: {e}")

    # DELETE Single
    try:
        resp = await client.delete(f"{BASE_URL}/blogs/{blog_id}", headers=headers)
        if resp.status_code in [200, 204]:
            print(f"Successfully deleted single blog {blog_id} via DELETE.")
        else:
            print(f"Failed to delete single blog: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"Error deleting single blog: {e}")

async def user_worker(i: int):
    async with httpx.AsyncClient(timeout=60.0) as client:
        # 1. Auth
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
        
        # 2. Get/Create Category
        cat_id = await create_category(client, token, i)
        
        # 3. Create Blogs
        created_ids = await create_blogs(client, token, real_user_id, TOTAL_BLOGS_PER_USER, cat_id)

        # 4. READ All blogs (GET)
        await read_blogs(client, token)

        # 5. READ, UPDATE, DELETE a single blog if we created any
        if created_ids:
            target_id = created_ids[0]
            await test_crud_single_blog(client, token, target_id)

async def clear_database():
    try:
        client = AsyncIOMotorClient("mongodb://localhost:27017")
        await client.drop_database("backbone_app")
        print("Database 'backbone_app' cleared successfully.")
    except Exception as e:
        print(f"Error clearing database: {e}")

async def test_long_process(client: httpx.AsyncClient):
    try:
        resp = await client.post(f"{BASE_URL}/custom-long-process")
        if resp.status_code == 200:
            print(f"Triggered custom long process: {resp.json()}")
        else:
            print(f"Failed to trigger long process: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"Error triggering long process: {e}")

async def main():
    print(f"Starting Load Test: {NUM_USERS} users, {TOTAL_BLOGS_PER_USER} blogs each.")
    print("Ensure the server is running on localhost:8000")
    
    await clear_database()

    async with httpx.AsyncClient(timeout=60.0) as client:
        await test_long_process(client)
    
    tasks = [user_worker(i) for i in range(NUM_USERS)]
    
    start_time = time.time()
    await asyncio.gather(*tasks)
    end_time = time.time()
    
    print(f"\n--- Total Load Test Time: {end_time - start_time:.2f}s ---")

if __name__ == "__main__":
    asyncio.run(main())
