# Blogermenia Backend (Backbone FastAPI)

This backend is a FastAPI + MongoDB (Beanie) application built on top of the in-repo framework **Backbone**.

Backbone provides:
- generic class-based CRUD APIs
- auth/session flows
- admin UI
- background jobs (logged + internal no-log queues)
- media/attachment processing
- template pages/forms
- email queue + PDF attachment support
- singleton key-value store (`backbone.db_store`)

Core internal model names:
- `Task` (background task tracking)
- `Email` (email delivery tracking)
- `Store` (singleton key/value storage)

The app entrypoint is `main.py`.

---

## 1. What Is Inside

### High-level structure

```text
backend/
├── main.py                     # FastAPI app bootstrap + router wiring
├── api/                        # App API routers (blogs, users, playlists, content)
├── schemas/                    # App Beanie models
├── pages/                      # App template page views
├── templates/                  # App templates (pages + email)
├── backbone/                   # Framework layer
│   ├── core/                   # config, settings, models, repository, media
│   ├── generic/                # Generic views + router helpers
│   ├── auth/                   # Auth API + reset-password pages
│   ├── admin/                  # Admin site/router/templates
│   ├── common/                 # cache + background queue services
│   ├── email_sender.py         # queued SMTP email sender + PDF attachments
│   └── db.py                   # singleton key/value store service
└── test/apitest.py             # heavy integration seed and validation script
```

---

## 2. Quick Start

### Prerequisites

- Python `3.13+`
- MongoDB running
- Redis running (required for async queue workers; without Redis tasks run sync fallback)
- `uv`

### Install

```bash
cd backend
uv sync
```

### Configure `.env`

Create/update `.env` in `backend/` with valid `KEY=value` lines.

Important:
- do not use Python style (`EMAIL_PORT: int = 587`)
- do not add quotes unless required

### Run API

```bash
uv run uvicorn main:app --reload
```

Base URL default:
- `http://127.0.0.1:8000`

---

## 3. Core App Boot Flow

`main.py`:
1. creates FastAPI app
2. registers app models
3. initializes `BackboneConfig`
4. includes routers under `/api` and `/pages`

`BackboneConfig` wires:
- MongoDB
- Redis cache + queues (when enabled)
- task workers (`WORKER_COUNT`, `INTERNAL_WORKER_COUNT`)
- auth router (`/api/auth/*`)
- admin router (`/admin/*`)
- static media mount in non-production
- global exception logging to `logs` collection

---

## 4. Generic CRUD and Mixins

Backbone generic views are built from mixins:
- `ListMixin`
- `CreateMixin`
- `RetrieveMixin`
- `UpdateMixin`
- `DeleteMixin`

Main ready-to-use views:
- `GenericCrudView`
- `GenericStatsView`
- `GenericCustomApiView`
- `GenericTemplateView`
- `GenericFormView`

### Example: CRUD API in 10 lines

```python
from backbone.generic.views import GenericCrudView
from backbone.core.permissions import AllowAny
from schemas.blogs import Blog

class BlogView(GenericCrudView):
    schema = Blog
    search_fields = ["title", "excerpt"]
    list_fields = ["id", "title", "slug", "author"]
    fetch_links = True
    permission_classes = [AllowAny]
```

Then include router:

```python
router.include_router(BlogView.as_router("/blogs", tags=["Blogs"]))
```

### Custom action on generic view

```python
from backbone.generic.action import action

class BlogView(GenericCrudView):
    @action(detail=True, methods=["post"])
    async def publish(self, request, pk):
        return {"status": "published", "id": pk}
```

### Model hooks (create/update/delete/field change)

Backbone supports model-level hooks using signal helpers.

```python
from backbone import on_create, on_update, on_delete, on_field_change
from backbone.core.models import User

@on_create(User)
async def user_created(instance, **kwargs):
    print("created", instance.id)

@on_update(User)
async def user_updated(instance, changed_fields=None, **kwargs):
    print("updated", changed_fields or {})

@on_delete(User)
async def user_deleted(instance, **kwargs):
    print("deleted", instance.id)

@on_field_change(User, fields=["email", "full_name"])
async def profile_changed(instance, changed_fields=None, matched_fields=None, **kwargs):
    print("matched", matched_fields)
```

Notes:
- `changed_fields` format is `{field_name: (old_value, new_value)}`
- use `on_field_change(..., require_all=True)` if all listed fields must change together

### Hook trigger timing (important)

- `on_create(Model)`: triggers after successful document insert (`Insert` event).
- `on_update(Model)`: triggers after successful update/save/replace (`Update`, `Save`, `Replace` events).
- `on_delete(Model)`: triggers only on hard delete (`document.delete()`).
- `on_field_change(Model, fields=[...])`: triggers on update flow when monitored field(s) changed.

### Event order on update

- Backbone first computes `changed_fields`.
- Then `on_field_change` is emitted.
- Then `on_update` is emitted.

### Soft delete vs hard delete

- Generic `DELETE` APIs use soft delete by default (`is_deleted=True`, `deleted_at=...`).
- Soft delete behaves as an update, so `on_field_change` and `on_update` fire.
- `on_delete` does not fire for soft delete.
- `on_delete` fires only when hard delete is used.

### Which hook fires for common API actions

- `POST /resource`: `on_create`
- `PATCH /resource/{id}`: `on_field_change` (if fields matched), then `on_update`
- `DELETE /resource/{id}` (default soft): `on_field_change`, then `on_update`
- Hard delete path: `on_delete`

### Registration best practice

- Register hooks once during app startup/import.
- Keep registration idempotent (Backbone helpers already deduplicate by handler name).
- Place app-specific hook registration in a dedicated module (example: `backbone/auth/hooks.py`).

---

## 5. Background Jobs (Important)

Backbone has two queue patterns:

1. **Logged queue**  
   Use `background_task(...)`  
   - queue: `backbone_tasks`
   - creates `task_logs` entries (`Task` model)
   - good for business jobs where visibility is needed

2. **Internal queue (no Task entry)**  
   Use `background_internal_task(...)`  
   - queue: `backbone_internal_tasks`
   - no `task_logs` creation
   - used by internal framework jobs (like attachment processing)

### Worker behavior

- Workers start only when Redis client is enabled (`CACHE_ENABLED=true`).
- If Redis is disabled/unavailable, queue helper falls back to immediate sync execution.

---

## 6. Media / Attachment Upload

Endpoint:
- `POST /api/media/upload`

Supports:
- multipart file upload (`file`)
- image URL fetch (`url`)

Flow:
1. creates `Attachment` doc with `pending`
2. enqueues internal background task (no Task entry)
3. worker stores file (Cloudinary or local `/media/...`)
4. updates attachment status (`completed`/`failed`)
5. auto-links attachment to target document field when `collection_name`, `document_id`, `field_name` are provided

Response includes:
- `id` (attachment id)
- `task_id` (internal queue task id, may be `null` in sync fallback)
- `status`
- `url`

---

## 7. Email System

Email sender module:
- `backbone.email_sender`

Main capabilities:
- queued SMTP sending
- HTML template rendering (Jinja2)
- optional plain text fallback
- file attachments (`file_path` or `content_base64`)
- template-to-PDF attachment generation (ReportLab)
- delivery status logging via `Email` model

Collections used:
- `email_delivery_logs`

Statuses:
- `queued`
- `processing`
- `sent`
- `failed`
- `skipped` (when `EMAIL_ENABLED=false`)

### Automatic registration emails

On user register (`/api/auth/register`), system queues:
1. welcome email
2. welcome-pack email with PDF attachment

### Generic usage

```python
from backbone import email_sender

await email_sender.queue_email(
    to_email="user@example.com",
    subject="Invoice",
    template_name="email/welcome_pack_email.html",
    context={"full_name": "Demo User"},
    pdf_attachments=[
        {
            "template_name": "email/pdf/welcome_packet.html",
            "context": {"full_name": "Demo User"},
            "filename": "packet.pdf",
            "content_type": "application/pdf",
        }
    ],
)
```

### Gmail note

For Gmail SMTP:
- use `EMAIL_USERNAME`
- use Gmail **App Password** in `EMAIL_PASSWORD`
- set matching `EMAIL_FROM_EMAIL`

---

## 8. Singleton Key-Value Store (`backbone.db_store`)

Backbone provides a single document store via `Store` model (MongoDB collection `backbone_store`).

Use cases:
- API keys
- feature flags
- small runtime-config values

API:
- `await db_store.get(key, default=None)`
- `await db_store.set(key, value)`
- `await db_store.update({...})`
- `await db_store.delete(key)`
- `await db_store.all()`

Rules:
- key cannot be empty
- key cannot contain `.`
- key cannot start with `$`

### Example

```python
from backbone import db_store

await db_store.set("homepage_banner", "Welcome to Blogermenia")
banner = await db_store.get("homepage_banner")
```

Also see testing page:
- `GET /pages/store-test/`

---

## 9. Auth, Pages, Admin

### Auth API (`/api/auth`)

- `POST /register`
- `POST /login`
- `POST /google/login`
- `POST /refresh`
- `POST /logout`
- `GET /me`
- `PATCH /me`

### Password reset pages

- `GET/POST /pages/reset-password/`
- `GET/POST /pages/reset-password/confirm/`

### App pages

- `/pages/contact/`
- `/pages/contact/submissions/`
- `/pages/about/`
- `/pages/store-test/`

### Admin

- `/admin/*`
- model browsing and management for core + app models

---

## 10. Environment Variables (Defaults and Purpose)

From `backbone/core/settings.py`:

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | `your_super_secret_key_here_at_least_32_chars` | JWT/security secret |
| `ALGORITHM` | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | refresh token lifetime |
| `ENVIRONMENT` | `develop` | `develop` / `production` behavior |
| `MONGODB_URL` | `mongodb://localhost:27017` | MongoDB URL |
| `DATABASE_NAME` | `backbone_app` | DB name |
| `CACHE_ENABLED` | `false` | enables Redis cache + async queues |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL |
| `CACHE_TTL` | `300` | default cache TTL |
| `WORKER_COUNT` | `2` | logged task worker count |
| `INTERNAL_WORKER_COUNT` | `2` | internal task worker count |
| `RATE_LIMIT_ENABLED` | `true` | global rate limiting toggle |
| `RATE_LIMIT_DEFAULT_CALLS` | `100` | default request count limit |
| `RATE_LIMIT_DEFAULT_WINDOW` | `60` | default window seconds |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | CORS list |
| `GOOGLE_CLIENT_ID` | `""` | Google auth |
| `GOOGLE_CLIENT_SECRET` | `""` | Google auth |
| `CLOUDINARY_URL` | `""` | Cloudinary config |
| `EMAIL_ENABLED` | `true` | email on/off |
| `EMAIL_HOST` | `smtp.gmail.com` | SMTP host |
| `EMAIL_PORT` | `587` | SMTP port |
| `EMAIL_USE_TLS` | `true` | STARTTLS |
| `EMAIL_USE_SSL` | `false` | implicit SSL |
| `EMAIL_USERNAME` | `""` | SMTP username |
| `EMAIL_PASSWORD` | `""` | SMTP password/app password |
| `EMAIL_FROM_EMAIL` | `no-reply@example.com` | sender email |
| `EMAIL_FROM_NAME` | `Backbone` | sender display name |
| `EMAIL_TIMEOUT_SECONDS` | `30` | SMTP timeout |

### Example `.env`

```env
ENVIRONMENT=develop
SECRET_KEY=replace_with_a_real_secret

MONGODB_URL=mongodb://127.0.0.1:27017
DATABASE_NAME=BlogerMenia

CACHE_ENABLED=true
REDIS_URL=redis://127.0.0.1:6379/0
WORKER_COUNT=2
INTERNAL_WORKER_COUNT=2

CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
RATE_LIMIT_ENABLED=true

GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
CLOUDINARY_URL=

EMAIL_ENABLED=true
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
EMAIL_USERNAME=your_gmail@gmail.com
EMAIL_PASSWORD=your_gmail_app_password
EMAIL_FROM_EMAIL=your_gmail@gmail.com
EMAIL_FROM_NAME=Blogermenia
EMAIL_TIMEOUT_SECONDS=30
```

---

## 11. Testing and Validation

### A. Fast smoke check

```bash
uv run python -c "import main; print(bool(main.app))"
```

### B. Heavy integration test

Script:
- `test/apitest.py`

What it does:
- optional DB wipe
- creates many users
- uploads attachments (user/blog/playlist)
- creates categories/blogs/playlists
- optionally creates testimonials + FAQs
- validates list endpoints
- validates `store-test` page set/get flow
- validates email logs in DB

Run:

```bash
uv run python test/apitest.py
```

Tune load by editing constants at top of file:
- `NUM_USERS`
- `BLOGS_PER_USER`
- `PLAYLISTS_PER_USER`
- `USER_WORKER_CONCURRENCY`
- `BLOG_CREATE_CONCURRENCY`

Current repository defaults are intentionally low for quick validation.  
For heavy seed (around 2500 blogs), set for example:
- `NUM_USERS = 50`
- `BLOGS_PER_USER = 50`
- `PLAYLISTS_PER_USER = 2`

---

## 12. Build Your Own Feature (Recommended Pattern)

1. Add/extend Beanie model in `schemas/`.
2. Add view class using `GenericCrudView` in `api/`.
3. Include router in `main.py`.
4. Use `background_task` for tracked business jobs.
5. Use `email_sender.queue_email(...)` for async email.
6. Use `db_store` for small dynamic key-value config.

---

## 13. Troubleshooting

### 1) `python-dotenv could not parse statement...`

Your `.env` line format is invalid.  
Use:
- `KEY=value`

Do not use:
- `KEY: int = 123`

### 2) SMTP `530 Authentication Required`

Fix:
- set `EMAIL_USERNAME`
- set `EMAIL_PASSWORD` (App Password for Gmail)
- ensure `EMAIL_FROM_EMAIL` matches sender account

### 3) Background tasks not entering queue

If `CACHE_ENABLED=false`, Redis queue is disabled and tasks run synchronously.  
Set:
- `CACHE_ENABLED=true`
- valid `REDIS_URL`

### 4) Media uploads remain pending

Check:
- Redis worker running (for async mode)
- Cloudinary config (if using cloud)
- attachment errors in logs collection (`logs`) and attachment status in `attachments`

---

## 14. Key Files to Read

- `main.py`
- `backbone/__init__.py`
- `backbone/core/config.py`
- `backbone/core/settings.py`
- `backbone/core/models.py`
- `backbone/common/services.py`
- `backbone/email_sender.py`
- `backbone/db.py`
- `backbone/core/media_router.py`
- `pages/contact.py`
- `test/apitest.py`
