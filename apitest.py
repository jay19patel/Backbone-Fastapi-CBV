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
TOTAL_BLOGS_PER_USER = 3  # Reduced for faster seeding
TOTAL_PLAYLISTS_PER_USER = 10 # 5 users * 2 playlists = 10 total playlists
CONCURRENT_REQUESTS = 2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_PATH = os.path.join(BASE_DIR, "blog.png") # Required for blogs
PROFILE_IMAGE_PATH = os.path.join(BASE_DIR, "profile.png") # Required for users
PLAYLIST_IMAGE_PATH = os.path.join(BASE_DIR, "playlist.png") # Required for playlists

async def upload_image(client: httpx.AsyncClient, token: str, file_path: str = None, url: str = None, collection: str = None, doc_id: str = None, field: str = None) -> Optional[str]:
    f = None
    try:
        files = None
        data = {}
        if collection: data["collection_name"] = collection
        if doc_id: data["document_id"] = doc_id
        if field: data["field_name"] = field
        
        if file_path:
            filename = os.path.basename(file_path)
            f = open(file_path, "rb")
            files = {"file": (filename, f, "image/jpeg")}
            method_desc = f"file {filename}"
        elif url:
            data["url"] = url
            method_desc = f"url {url}"
        else:
            return None
            
        headers = {"Authorization": f"Bearer {token}"}
        resp = await client.post(f"{BASE_URL}/api/media/upload", files=files, data=data, headers=headers)
        
        if resp.status_code == 200:
            resp_data = resp.json()
            attachment_id = resp_data.get("id")
            print(f"Upload initiated for {method_desc}. Attachment ID: {attachment_id}")
            return attachment_id
        else:
            print(f"Failed to upload {method_desc}: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"Error uploading: {e}")
    finally:
        if f: f.close()
    return None

async def update_user_profile(client: httpx.AsyncClient, token: str, user_id: str, attachment_id: str):
    headers = {"Authorization": f"Bearer {token}"}
    try:
        # Since field is Link[Attachment], we pass the attachment ID
        resp = await client.patch(f"{BASE_URL}/api/users/{user_id}", json={"profile_image": attachment_id}, headers=headers)
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
        resp = await client.post(f"{BASE_URL}/api/auth/register", json=user_data)
        if resp.status_code == 201:
            login_resp = await client.post(f"{BASE_URL}/api/auth/login", json={"email": user_data["email"], "password": user_data["password"]})
            return login_resp.json()
        elif resp.status_code == 400:
             login_resp = await client.post(f"{BASE_URL}/api/auth/login", json={"email": user_data["email"], "password": user_data["password"]})
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
    parent_data = {"name": f"Programming {i}", "slug": f"programming-cat-{i}-{ts}"}
    try:
        resp = await client.post(f"{BASE_URL}/api/blogs/categories/", json=parent_data, headers=headers)
        if resp.status_code == 201:
             data = resp.json()
             parent_id = data.get("id") or data.get("_id")
             # 2. Create Sub Category
             sub_data = {"name": f"Python {i}", "slug": f"python-cat-{ts+1}"}
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

async def create_blogs(client: httpx.AsyncClient, token: str, user_id: str, num_blogs: int, category_id: str, thumbnail_att_id: str, section_att_id: str, user_name: str) -> List[str]:
    headers = {"Authorization": f"Bearer {token}"}
    
    sem = asyncio.Semaphore(CONCURRENT_REQUESTS)

    async def _create_one(idx):
        async with sem:
            now_iso = datetime.now(timezone.utc).isoformat()
            
            topics = ["Python Pattern", "FastAPI Guide", "AsyncIO Mastery", "Data Science Base", "Machine Learning 101"]
            topic = random.choice(topics)
            
            blog_data = {
                "title": f"Master {topic} {idx}: Complete Guide - {user_name}",
                "subtitle": "From beginner to advanced - learn fast with real-world examples",
                "slug": f"blog-post-{user_id}-{idx}-{int(time.time())}-{random.randint(1000, 9999)}",
                "excerpt": f"Discover the power of {topic}. Learn syntax, best practices, and advanced concepts to build robust applications.",
                "introduction": "Programming has become one of the most popular skills in the world, powering everything from web applications to data science. This comprehensive guide will take you through advanced concepts.",
                "sections": [
                    {
                        "title": "Why Learn This in 2025?",
                        "type": "text",
                        "content": "Its simplicity and versatility make it an ideal language for beginners and professionals alike. Clean syntax, extensive libraries, and strong community support."
                    },
                    {
                        "title": "Essential Concepts",
                        "type": "bullets",
                        "items": [
                            "Variables, data types, and operators",
                            "Control flow (if/else, loops)",
                            "Functions and lambda expressions",
                            "Object-oriented programming (OOP)"
                        ]
                    },
                    {
                        "title": "Example: Building a REST API",
                        "type": "code",
                        "language": "python",
                        "content": "from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/')\nasync def root():\n    return {'message': 'Welcome to API'}"
                    },
                    {
                        "title": "Architecture Diagram",
                        "type": "image",
                        "attachment": section_att_id,  # Attachment ID (string)
                        "caption": "Architecture overview diagram"
                    },
                    {
                        "title": "Important Note",
                        "type": "note",
                        "content": "Practice is key to mastering programming. Write code daily, work on projects, and contribute to open-source."
                    }
                ],
                "conclusion": "It is a powerful and versatile language that opens doors to numerous career opportunities. Start coding today!",
                "author": str(user_id),
                "category": category_id if category_id else None,
                "thumbnail": thumbnail_att_id,  # Attachment ID for thumbnail
                "isPublished": True,
                "publishedDate": now_iso,
                "embedding": [random.uniform(0, 1) for _ in range(10)]
            }
            try:
                resp = await client.post(f"{BASE_URL}/api/blogs/", json=blog_data, headers=headers)
                if resp.status_code == 201:
                    data = resp.json()
                    return data.get("_id") or data.get("id")
                else:
                    print(f"Failed to create blog {idx}: {resp.status_code} - {resp.text[:200]}")
                return None
            except Exception as e:
                print(f"Error creating blog {idx}: {e}")
                return None

    print(f"User {user_name} starting {num_blogs} blogs creation...")
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
                "name": f"Playlist {idx} by User {user_id}",
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
        user_name = f"Test User {i}"
        
        # Get User ID
        headers = {"Authorization": f"Bearer {token}"}
        me_resp = await client.get(f"{BASE_URL}/api/auth/me", headers=headers)
        if me_resp.status_code != 200:
            print(f"Failed to get me: {me_resp.text}")
            return
        me_data = me_resp.json()
        real_user_id = me_data.get("id") or me_data.get("_id")
        
        # 2. Upload Profile Image
        print(f"User {i} uploading profile image...")
        prof_att_id = await upload_image(client, token, PROFILE_IMAGE_PATH, collection="users", doc_id=real_user_id, field="profile_image")
        if prof_att_id:
            await update_user_profile(client, token, real_user_id, prof_att_id)
            
        # 3. Upload Blog Image
        print(f"User {i} uploading blog background image...")
        image_att_id = await upload_image(client, token, IMAGE_PATH, collection="blogs", field="thumbnail")
        if not image_att_id:
            print(f"User {i} missing blog image attachment id. Proceeding anyway but image might fail.")
            
        # 4. Upload Playlist Image
        print(f"User {i} uploading playlist image...")
        playlist_att_id = await upload_image(client, token, file_path=PLAYLIST_IMAGE_PATH, collection="playlists", field="thumbnail")
        
        # 4.5. Upload separate image for blog content sections
        print(f"User {i} uploading section image for blog content...")
        random_url = f"https://picsum.photos/seed/{random.randint(1, 100000)}/800/600"
        url_att_id = await upload_image(client, token, url=random_url, collection="blogs", field="content")
        
        # 5. Content Creation
        cat_id = await create_category(client, token, i)
        # thumbnail_att_id = main blog thumbnail, section_att_id = image section attachment
        blog_ids = await create_blogs(client, token, real_user_id, TOTAL_BLOGS_PER_USER, cat_id, image_att_id, url_att_id, user_name)
        if blog_ids:
             await create_playlists(client, token, real_user_id, TOTAL_PLAYLISTS_PER_USER, blog_ids, playlist_att_id)

async def create_faqs():
    faqs = [
        {"question": "How do I create a blog?", "answer": "Simply sign up and click the 'Write' button in the dashboard. You can use our AI assistant to help you draft your thoughts!"},
        {"question": "Is BlogerMenia free to use?", "answer": "Yes, BlogerMenia is completely free for all creators and readers. We believe in democratizing knowledge sharing."},
        {"question": "Can I edit my blogs after publishing?", "answer": "Absolutely! You can edit, update, or delete your blogs anytime from your profile dashboard."},
        {"question": "How do I make my playlists popular?", "answer": "Add high-quality, relevant blogs to your playlists and share them on social media to reach more readers."},
        {"question": "What are featured blogs?", "answer": "Featured blogs are high-quality posts hand-picked by our editors for their exceptional content and relevance."},
        {"question": "How does the AI assistant work?", "answer": "Our AI uses advanced natural language processing to help you generate outlines, suggest titles, and even draft entire sections based on your ideas."},
        {"question": "Can I follow other creators?", "answer": "Yes! You can visit any creator's profile to see all their published blogs and playlists."},
        {"question": "Is my data secure on BlogerMenia?", "answer": "We take data privacy and security very seriously. Your personal information is encrypted and never shared with third parties."}
    ]
    async with httpx.AsyncClient() as client:
        for faq in faqs:
            resp = await client.post(f"{BASE_URL}/api/faqs/", json=faq)
            if resp.status_code != 201:
                print(f"Failed to create FAQ: {resp.text}")
    print(f"{len(faqs)} FAQs created.")

async def create_testimonials():
    testimonials = [
        {"author": "Sarah Jenkins", "content": "BlogerMenia has completely transformed how I share my thoughts. The platform is intuitive and the community is supportive.", "designation": "Content Creator"},
        {"author": "David Miller", "content": "The best blogging platform I've used. The editor is powerful yet simple, and managing my posts is a breeze.", "designation": "Tech Blogger"},
        {"author": "Emily Chen", "content": "I love the clean design and how easy it is to connect with readers. Highly recommended for anyone starting a blog.", "designation": "Travel Writer"},
        {"author": "Michael Ross", "content": "The playlist feature is a game changer for organizing my tutorial series. My readers love the structured learning paths!", "designation": "Software Engineer"},
        {"author": "James Wilson", "content": "The AI writing assistant is incredibly helpful. it helps me overcome writer's block and get my ideas down faster than ever.", "designation": "Freelance Writer"},
        {"author": "Elena Rodriguez", "content": "I've tried many platforms, but BlogerMenia feels like home. The interface is beautiful and everything just works.", "designation": "Lifestyle Blogger"}
    ]
    async with httpx.AsyncClient() as client:
        for test in testimonials:
            resp = await client.post(f"{BASE_URL}/api/testimonials/", json=test)
            if resp.status_code != 201:
                print(f"Failed to create testimonial: {resp.text}")
    print(f"{len(testimonials)} Testimonials created.")

async def create_contact_messages():
    messages = [
        {"name": "Alice Smith", "email": "alice@example.com", "subject": "General Inquiry", "message": "I'm interested in learning more about your platform's features. Do you have a roadmap for upcoming updates?"},
        {"name": "Bob Johnson", "email": "bob@testmail.com", "subject": "Feature Request", "message": "I would love to see a dark mode option for the blog editor. It would make writing much easier at night."},
        {"name": "Charlie Brown", "email": "charlie@company.org", "subject": "Partnership Opportunity", "message": "I represent a group of writers who are interested in a collective partnership with BlogerMenia. Who can we talk to about this?"},
        {"name": "Diana Prince", "email": "diana@justice.com", "subject": "Bug Report", "message": "I noticed a small layout issue on mobile devices when viewing certain playlists. Just wanted to let you know!"}
    ]
    async with httpx.AsyncClient() as client:
        for msg in messages:
            # Note: The endpoint in content.py is /content/contact/
            resp = await client.post(f"{BASE_URL}/api/content/contact/", json=msg)
            if resp.status_code != 201:
                print(f"Failed to create contact message: {resp.text}")
    print(f"{len(messages)} Contact Messages created.")

async def clear_database():
    try:
        from backbone.core.settings import settings
        client = AsyncIOMotorClient(settings.MONGODB_URL)
        await client.drop_database(settings.DATABASE_NAME)
        print(f"Database '{settings.DATABASE_NAME}' cleared successfully.")
    except Exception as e:
        print(f"Error clearing database: {e}")

async def main():
    print(f"Starting Content Generation:")
    missing_files = []
    for fp in [IMAGE_PATH, PROFILE_IMAGE_PATH, PLAYLIST_IMAGE_PATH]:
        if not os.path.exists(fp):
            missing_files.append(fp)
    if missing_files:
        print(f"Error: following files not found: {missing_files}")
        return

    await clear_database()
    tasks = [user_worker(i) for i in range(NUM_USERS)]
    
    start_time = time.time()
    await asyncio.gather(*tasks)
    end_time = time.time()

    await create_faqs()
    await create_testimonials()
    await create_contact_messages()
    
    print(f"\n--- Total Generation Time: {end_time - start_time:.2f}s ---")

if __name__ == "__main__":
    asyncio.run(main())
