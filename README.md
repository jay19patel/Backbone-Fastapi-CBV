# 🚀 Backbone FastAPI: MongoDB-Only with Redis Caching

A modern, highly-modular FastAPI framework skeleton optimized for MongoDB/Beanie and enhanced with a Redis-based caching layer.

## 🛠 Features

- **MongoDB-Only Architecture**: Streamlined Beanie-based models for simplified data management.
- **Redis Caching**: Built-in caching for Generic Views (`List` and `Retrieve`) with automatic invalidation.
- **Dockerized Databases**: Easy setup for MongoDB and Redis using Docker Compose.
- **Fast Development**: Optimized for `uv` and `uvicorn` for a seamless local development experience.
- **Granular Auth**: JWT-based session management with refresh tokens.

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
