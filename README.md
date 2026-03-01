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

#### GenericCrud Parameters Explained
When initializing `GenericCrud` or `BaseGenericView`, you have a number of configurable options:
- `schema`: The Beanie `Document` model that this CRUD router controls (e.g. `User`, `Blog`).
- `prefix`: The URL prefix for the endpoints (e.g. `/blogs`).
- `tags`: OpenAPI tags used for grouping the endpoints in the Swagger UI.
- `repository`: An optional `BeanieRepository` instance. If omitted, one is automatically created for the `schema`.
- `permission_classes`: A list of backend permissions (e.g. `[IsOwner]`, `[AllowAny]`, `[IsAdminUser]`) that are executed before endpoints resolve.
- `list_fields`: A list of string fields (e.g., `["title", "author"]`) that dictate *which* fields are returned in the response for `GET` requests using MongoDB Projection. Other fields are omitted.
- `search_fields`: Fields to apply `$regex` indexing to when a `?search=` query parameter is supplied.
- `filter_fields`: Fields used for exact matching filters.
- `ordering_fields`: Fields allowing developers to request `?sort=` ordering.
- `database`: Used to override the default database.
- `use_auth`: A boolean flag defining whether backend authentication endpoints require a valid user token.
- `cache_ttl`: An integer representing the time in seconds a `GET` result remains cached in Redis.
- **`lookup_field`**: A string defining which field to use when fetching, updating, or deleting a single record. Defaults to `"id"`. Set this to `"slug"` (e.g., `lookup_field="slug"`) if you want your detail endpoints to query by a custom slug instead of the Beanie Document ID.
- **`populate_fields`**: A dictionary detailing how to join external collections via `$lookup`. Format: `{"local_author_id": "target_users_collection"}`. *Note: this manually defines the relations MongoDB should merge together.*
- **`fetch_links`**: A massive shortcut bool. When set to `True`, the backend inspects your `schema` for Beanie `Link[x]` types and Audit fields, and auto-generates the `populate_fields` dictionary for you!

`populate_fields` controls the MongoDB `$lookup` pipeline, determining which ID-referenced relations in other collections should be fetched and merged into the document (transforming an ID string into a full object dictionary). `list_fields` is used at the end of the query (Projection) to slice the returned dictionary and *only* send the specific list of keys to the user, stripping away sensitive or heavy data.

### 🖼️ Core Media System
Backbone includes a built-in, background-processed media handling system.

#### 1. The Attachment Model
All uploads are tracked via the `Attachment` model. It stores:
- `filename`, `file_path`, `content_type`
- `status` (pending, completed, failed)
- `size` (automatically converted to **MB**)
- `collection_name`, `document_id`, `field_name` (for automatic linking)

#### 2. Usage in Schemas
To add an image or file to a model, use `Link[Attachment]`:
```python
class Blog(AuditDocument):
    title: str
    thumbnail: Optional[Link["Attachment"]] = None
```

#### 3. Uploading Files
Use the built-in endpoint: `POST /api/media/upload/image`
- **Payload**: Form-data with `file` (UploadFile).
- **Optional Params**: `collection_name`, `document_id`, `field_name`.

#### 4. Automatic Linking
If you provide `collection_name`, `document_id`, and `field_name` during upload, Backbone will:
1. Save the file to `media/{collection_name}/`.
2. Automatically update the target document's field with a link to the new `Attachment`.

---

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
