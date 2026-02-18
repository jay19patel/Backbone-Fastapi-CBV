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
    db = client[TEST_DATABASE_NAME]
    
    # Aggressive Cleanup
    collections = ["users", "sessions", "notes", "logs", "blogs", "playlists"]
    for coll in collections:
        await db[coll].delete_many({})
        
    # Initialize Beanie
    await init_beanie(database=db, document_models=[User, Session, NoteSchema])
    
    yield client
    
    # Teardown Cleanup
    for coll in collections:
        await db[coll].delete_many({})
    client.close()

@pytest_asyncio.fixture(scope="function")
async def client(db_client):
    from backbone import BackboneConfig
    from motor.motor_asyncio import AsyncIOMotorClient
    
    # Initialize BackboneConfig manually for the app instance to set state
    bc = BackboneConfig(
        app=app,
        config=config, # Use the new TestConfig instance
        document_models=[User, Session, NoteSchema]
    )
    # Since we are in testing and bypassing real lifespan sometimes, 
    # ensure state is set.
    app.state.backbone_config = bc
    
    # We still need to ensure Beanie is initialized for the models
    # This is done in db_client fixture too, but bc.lifespan does it properly.
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        app.dependency_overrides = {}
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
    assert response.status_code == 200, f"Login failed: {response.text}"
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
    print(f"\n[TEST_DEBUG] CREATED NOTE: {created_note}")
    assert created_note["title"] == note_data["title"]
    note_id = created_note.get("_id") or created_note.get("id")
    print(f"[TEST_DEBUG] FETCHING ID: {note_id}")

    # 2. Get All Notes
    response = await client.get("/notes/", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["results"][0]["title"] == note_data["title"]

    # 3. Get Single Note
    response = await client.get(f"/notes/{note_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["_id"] == note_id

    # 4. Update Note
    update_data = {"title": "Updated Title"}
    response = await client.patch(f"/notes/{note_id}", json=update_data, headers=headers)
    assert response.status_code == 200
    assert response.json()["title"] == "Updated Title"

    # 5. Delete Note
    response = await client.delete(f"/notes/{note_id}", headers=headers)
    assert response.status_code == 204 # Changed from 200 to match implementation @self.router.delete("/{pk}", status_code=204)
    
    # Verify Deletion (Soft Delete usually filters it out)
    response = await client.get(f"/notes/{note_id}", headers=headers)
    assert response.status_code == 404
