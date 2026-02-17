import os
os.environ["DATABASE_NAME"] = "test_backbone_app"

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from main import app, config
from backbone.core.models import User, Session
from backbone.core.database import init_database
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from schema import NoteSchema

# Override Config for Testing
TEST_DATABASE_NAME = "test_backbone_app"
config.DATABASE_NAME = TEST_DATABASE_NAME

@pytest_asyncio.fixture(scope="function")
async def db_client():
    # Setup
    client = AsyncIOMotorClient(config.MONGODB_URL)
    await init_database(client, TEST_DATABASE_NAME, [User, Session, NoteSchema])
    db = client[TEST_DATABASE_NAME]
    await db["users"].delete_many({})
    await db["sessions"].delete_many({})
    await db["notes"].delete_many({})
    yield client
    # Teardown
    await db["users"].delete_many({})
    await db["sessions"].delete_many({})
    await db["notes"].delete_many({})
    client.close()

@pytest_asyncio.fixture(scope="function")
async def client(db_client):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        app.dependency_overrides = {} # Clear any overrides
        # We need to ensure the app uses the test DB. 
        # Since main.py initializes usually on startup, 
        # we might need to manually trigger init with test DB or mock it.
        # But we called init_database above with test DB name. 
        # Beanie is global, so checking if it works.
        yield ac

@pytest.mark.asyncio
async def test_auth_flow(client):
    # 1. Register
    reg_data = {
        "email": "test@example.com",
        "password": "password123",
        "full_name": "Test User"
    }
    response = await client.post("/auth/register", json=reg_data)
    assert response.status_code == 201, f"Registration failed: {response.text}"
    assert response.json()["email"] == reg_data["email"]

    # 2. Login
    login_data = {
        "email": "test@example.com",
        "password": "password123"
    }
    response = await client.post("/auth/login", json=login_data)
    assert response.status_code == 200
    tokens = response.json()
    assert "access_token" in tokens
    
    access_token = tokens["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # 3. Me
    response = await client.get("/auth/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["email"] == reg_data["email"]

    return headers

@pytest.mark.asyncio
async def test_crud_notes(client):
    # Register & Login first
    headers = await test_auth_flow(client)
    
    # 1. Create Note
    note_data = {
        "title": "My First Note",
        "body": "This is a test note.",
        "is_pinned": True
    }
    response = await client.post("/notes/", json=note_data, headers=headers)
    assert response.status_code == 201
    created_note = response.json()
    assert created_note["title"] == note_data["title"]
    note_id = created_note["_id"]

    # 2. Get All Notes
    response = await client.get("/notes/", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["results"][0]["title"] == note_data["title"]

    # 3. Get Single Note
    response = await client.get(f"/notes/{note_id}/", headers=headers)
    assert response.status_code == 200
    assert response.json()["_id"] == note_id

    # 4. Update Note
    update_data = {"title": "Updated Title"}
    response = await client.patch(f"/notes/{note_id}/", json=update_data, headers=headers)
    assert response.status_code == 200
    assert response.json()["title"] == "Updated Title"

    # 5. Delete Note
    response = await client.delete(f"/notes/{note_id}/", headers=headers)
    assert response.status_code == 200
    
    # Verify Deletion (Soft Delete usually filters it out)
    response = await client.get(f"/notes/{note_id}/", headers=headers)
    assert response.status_code == 404
