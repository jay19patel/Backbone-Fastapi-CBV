# Backbone for FastAPI

`Backbone` is the reusable backend framework layer inside this repository. It is designed to make FastAPI development faster by combining class-based CRUD views, Beanie repositories, permissions, auth, admin tooling, caching, Redis jobs, and shared infrastructure into one coherent developer experience.

This package is already useful for internal development. The next goal is to make it cleaner, more extensible, and more production-grade.

## Goals

- reduce repeated CRUD boilerplate
- give developers an easy way to build APIs from Beanie models
- provide a built-in admin surface
- support auth, sessions, media, caching, and background jobs
- keep extension points simple so Backbone can grow into a real reusable framework

## Current Feature Set

### Core

- `BackboneConfig` for app bootstrap and lifecycle wiring
- Beanie database initialization
- framework settings with environment-based behavior
- shared exception and utility layers

### Data and repository layer

- `BeanieRepository` abstraction
- CRUD helpers
- pagination support
- projection support
- populate/link detection support
- soft-delete-oriented query patterns

### Generic views

- `GenericListView`
- `GenericCreateView`
- `GenericRetrieveView`
- `GenericUpdateView`
- `GenericDeleteView`
- `GenericCrudView`
- `GenericStatsView`
- `GenericSubResourceView`
- `GenericCustomApiView`
- custom `@action(...)` endpoints on views

### Auth

- register
- login
- refresh
- logout
- Google login
- session validation
- JWT access and refresh token helpers

### Admin

- model registry
- admin login
- dashboard
- model browsing
- export screens
- template-driven HTML admin pages

### Infrastructure

- Redis-backed caching
- Redis-backed background task queue
- background worker loop
- sliding-window rate limiting
- signal/event hooks
- attachment/media support
- DB log persistence support

## High-Level Architecture

```text
backend/
├── backbone/
│   ├── admin/        # Admin registry, router, templates
│   ├── auth/         # Auth router and auth services
│   ├── common/       # Shared services, utils, exceptions
│   ├── core/         # Config, settings, models, permissions, repository
│   ├── generic/      # Generic class-based views and router helpers
│   └── schemas/      # Shared response/input schemas
├── api/              # App-level routers built using Backbone
├── schemas/          # App-level document models
└── main.py           # App entrypoint
```

## Developer Workflow

The intended usage pattern is:

1. Define a Beanie `Document`.
2. Create a view class using `GenericCrudView` or another generic view.
3. Configure permissions, search fields, list fields, and link population.
4. Register the router in the app.
5. Optionally add custom actions, signals, admin config, and service logic.

### Example

```python
from backbone import GenericCrudView, AllowAny
from schemas.blogs import Blog

class BlogView(GenericCrudView):
    schema = Blog
    search_fields = ["title", "excerpt"]
    permission_classes = [AllowAny]
    fetch_links = True

router.include_router(BlogView.as_router("/blogs", tags=["Blogs"]))
```

### Custom action example

```python
from backbone.generic.action import action

class BlogView(GenericCrudView):
    @action(detail=True, methods=["post"])
    async def publish(self, request, pk):
        return {"status": "published"}
```

## Running The Backend

### Prerequisites

- Python 3.13+
- MongoDB
- Redis
- `uv`

### Install

```bash
uv sync
```

### Start the API

```bash
uv run uvicorn main:app --reload
```

## Configuration

Backbone settings are defined in [`backbone/core/settings.py`](/Users/jaypatel/Desktop/Development/Jay/Blogermenia-Djnago/backend/backbone/core/settings.py).

Important settings:

- `SECRET_KEY`
- `ENVIRONMENT`
- `MONGODB_URL`
- `DATABASE_NAME`
- `CACHE_ENABLED`
- `REDIS_URL`
- `RATE_LIMIT_ENABLED`
- `CORS_ALLOWED_ORIGINS`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `CLOUDINARY_URL`

Example `.env`:

```env
SECRET_KEY=replace_with_a_real_secret
ENVIRONMENT=develop
MONGODB_URL=mongodb://localhost:27017
DATABASE_NAME=backbone_app
CACHE_ENABLED=true
REDIS_URL=redis://localhost:6379/0
RATE_LIMIT_ENABLED=true
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
CLOUDINARY_URL=
```

## What Is Good Right Now

- the generic CRUD foundation is strong
- the package structure is understandable
- the framework already reduces a lot of repetitive FastAPI code
- auth, admin, cache, signals, and jobs are integrated in one place
- developers can build app-level routers quickly

## What Needs Improvement

Backbone is not fully production-grade yet. The biggest gaps are:

- framework code and app code are still partly coupled
- repository methods do not always return one consistent shape
- there are too many broad exception handlers and silent fallbacks
- admin and auth flows need stronger hardening
- worker architecture is still lightweight
- observability and tests need stronger coverage

The full review is documented in [BACKBONE_ARCHITECTURE_AUDIT.md](/Users/jaypatel/Desktop/Development/Jay/Blogermenia-Djnago/backend/BACKBONE_ARCHITECTURE_AUDIT.md).

## Recommended Next Refactor Stages

### Stage 1: Stabilize contracts

- standardize repository return types
- add a proper app factory pattern
- remove old/outdated assumptions
- document extension boundaries clearly

### Stage 2: Improve developer ergonomics

- add cleaner service-layer examples
- add better admin customization APIs
- add scaffolding helpers
- improve docs and usage examples

### Stage 3: Production hardening

- strengthen auth and admin security
- add health checks
- add structured logging and metrics
- improve background worker architecture
- add framework-level tests

## Design Direction

To keep Backbone easy to extend, new work should follow these rules:

- routers should stay thin
- services should hold business logic
- repositories should own persistence logic
- framework internals should stay app-agnostic
- extension points should be explicit and documented

## Useful Files

- package exports: [`backbone/__init__.py`](/Users/jaypatel/Desktop/Development/Jay/Blogermenia-Djnago/backend/backbone/__init__.py)
- config bootstrap: [`backbone/core/config.py`](/Users/jaypatel/Desktop/Development/Jay/Blogermenia-Djnago/backend/backbone/core/config.py)
- settings: [`backbone/core/settings.py`](/Users/jaypatel/Desktop/Development/Jay/Blogermenia-Djnago/backend/backbone/core/settings.py)
- repository: [`backbone/core/repository.py`](/Users/jaypatel/Desktop/Development/Jay/Blogermenia-Djnago/backend/backbone/core/repository.py)
- mixins: [`backbone/core/mixins.py`](/Users/jaypatel/Desktop/Development/Jay/Blogermenia-Djnago/backend/backbone/core/mixins.py)
- generic views: [`backbone/generic/views.py`](/Users/jaypatel/Desktop/Development/Jay/Blogermenia-Djnago/backend/backbone/generic/views.py)
- auth router: [`backbone/auth/router.py`](/Users/jaypatel/Desktop/Development/Jay/Blogermenia-Djnago/backend/backbone/auth/router.py)
- admin router: [`backbone/admin/router.py`](/Users/jaypatel/Desktop/Development/Jay/Blogermenia-Djnago/backend/backbone/admin/router.py)

