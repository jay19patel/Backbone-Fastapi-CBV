# 🚀 Backbone FastAPI: MongoDB-Only with Redis Caching

A modern, highly-modular FastAPI framework skeleton optimized for MongoDB/Beanie and enhanced with a Redis-based caching layer.

## 🛠 Features

- **Decoupled Model Signals**: Connect external logic (like notifications) to model events in `main.py` without modifying models.
- **Model Event Hooks**: Pre-built base class (`EventDocument`) with Beanie lifecycle hooks and change tracking.
- **Centralized Logging**: Comprehensive logging to Console, `app.log`, and asynchronously to MongoDB.
- **Automatic Registration**: Core models (`User`, `Session`, `LogEntry`) are automatically registered by `BackboneConfig`.

---

## 🚀 Getting Started

### 1. Prerequisites
- [Docker](https://docs.docker.com/get-docker/) & [Docker Compose](https://docs.docker.com/compose/install/)
- [uv](https://github.com/astral-sh/uv) (recommended) or Python 3.11+

### 2. Start Databases
Run the following command to start MongoDB and Redis in the background:
```bash
sudo docker-compose up -d
```
*Note: Redis is exposed on port `6380` to avoid conflicts with local instances.*

### 3. Install Dependencies
```bash
uv pip install -e .
```

### 4. Run the Application
Start the FastAPI server locally:
```bash
uv run uvicorn main:app --reload
```

---

## ✅ Verification: Is everything running?

### Check Database Connectivity
We provide a helper script to confirm that your local app can talk to the Dockerized databases:
```bash
uv run verify_db.py
```
**Expected Output:**
```
✅ MongoDB is UP and responding!
✅ Redis is UP and responding!
🚀 All database systems are running correctly!
```

### Check Docker Status
To see if the containers are alive:
```bash
sudo docker ps
```
You should see `backbone-fastapi-cbv-mongodb-1` and `backbone-fastapi-cbv-redis-1`.

---

## ⚙️ Configuration

You can configure the application in `main.py` via the `AppConfig` class:

```python
class AppConfig(settings.__class__):
    ENVIRONMENT: str = "develop"
    MONGODB_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "backbone_app"
    REDIS_URL: str = "redis://localhost:6380/0"
    CACHE_ENABLED: bool = True  # Toggle caching on/off
```

---

## 📖 Usage

### Authentication
- **Register**: `POST /auth/register`
- **Login**: `POST /auth/login` (Returns Access Token & sets Refresh Cookie)
- **Me**: `GET /auth/me` (Protected)

### Generic CRUD
Generic views automatically handle caching. For example, the `Playlists` endpoints:
- `GET /playlists/`: Retrieves paginated list (Cached)
- `GET /playlists/{pk}`: Retrieves single item (Cached)
- `POST/PATCH/DELETE`: Standard operations (Automatically invalidates cache)

### 🔔 Advanced: Model Signals & Events
The framework provides a decoupled signal system to handle model lifecycles:

1.  **Define a Handler in `main.py`**:
    ```python
    async def on_note_created(instance, **kwargs):
        logger.info(f"Notification: New note '{instance.title}'")

    signals.post_create.connect(NoteSchema, on_note_created)
    ```
2.  **Field Specific Tracking**:
    ```python
    async def on_pin_changed(instance, changed_fields=None, **kwargs):
        if "is_pinned" in changed_fields:
            logger.warning(f"Note {instance.id} pin status: {changed_fields['is_pinned']}")

    signals.on_field_change.connect(NoteSchema, on_pin_changed)
    ```

### 📝 Logging
Use the centralized logger to track system activity. Logs are stored in `logs/app.log` and the `log_entries` collection in MongoDB.

```python
from backbone import logger

logger.info("Something happenened!")
logger.error("An error occurred", extra_info={"details": "contextual data"})
```

### 🏗️ Event-Driven Models
Inherit from `EventDocument` in `schema.py` to enable automatic change tracking and signals:

```python
class MyModel(EventDocument):
    ...
    @after_event(Insert)
    async def custom_logic(self):
        logger.info("Internal model hook triggered")
```

---

## 📁 Project Structure

```text
backbone/
├── auth/          # Authentication routes & logic
├── core/          # Config, Models, and Repository
├── generic/       # Generic CRUD View classes
├── utils/         # Caching, Logging, and Passwords
main.py            # App Entry Point & Routing
schema.py          # Beanie Document Definitions
docker-compose.yml # DB Infrastructure
```
