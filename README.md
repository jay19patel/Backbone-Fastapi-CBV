# 🚀 Backbone FastAPI: Modern & Modular

A senior-level, highly-modular FastAPI framework skeleton optimized for MongoDB/Beanie and enhanced with a Redis-backed Task Queue and Caching layer.

## 🛠 Features

- **Standardized UTC Handling**: All timestamps use modern `datetime.now(timezone.utc)`.
- **Modular Generic Views**: Decomposed architecture using the `as_router()` pattern for maximum scalability.
- **Enterprise Task Queue**: Redis-backed background tasks with exponential backoff retry logic.
- **Decoupled Model Signals**: Connect external logic to model events without modifying core schemas.
- **Centralized Service Layer**: Unified `backbone/common/` for shared services, exceptions, and utilities.

---

## 🚀 Getting Started

### 1. Prerequisites
- [uv](https://github.com/astral-sh/uv) (recommended) or Python 3.12+
- MongoDB and Redis instances

### 2. Install Dependencies
```bash
uv pip install -e .
```

### 3. Run the Application
```bash
uv run uvicorn main:app --reload
```

---

## 📖 Usage

### Modern Generic CRUD
Inherit from `GenericCrudView` and use `as_router()` for zero-boilerplate APIs:

```python
from backbone import GenericCrudView, AllowAny
from schemas.blogs import Blog

class BlogView(GenericCrudView):
    schema = Blog
    search_fields = ["title", "excerpt"]
    permission_classes = [AllowAny]

router.include_router(BlogView.as_router("/blogs", tags=["Blogs"]))
```

### Advanced Task Queue
Execute long-running tasks in the background with automatic retries:

```python
from backbone import background_task

async def process_data(item_id: str):
    # your logic here
    pass

@router.post("/process")
async def trigger_process(id: str):
    await background_task(process_data, id, max_retries=5)
    return {"status": "enqueued"}
```

### View Actions
Add custom endpoints directly to your Generic views:

```python
from backbone.generic.action import action

class BlogView(GenericCrudView):
    @action(detail=True, methods=["post"])
    async def like(self, request, pk):
        # custom logic
        return {"status": "liked"}
```

---

## 📁 Project Structure

```text
backbone/
├── auth/          # Authentication service & session management
├── common/        # Shared services, Task Queue, and Exceptions
├── core/          # Config, Models, Permissions, and Repository
├── generic/       # Modern Generic CRUD View package
│   ├── views.py   # Core view classes (as_router)
│   ├── utils.py   # Internal extraction helpers
│   └── action.py  # Action decorator logic
main.py            # App Entry Point & Routing
schemas/           # Beanie Document Definitions
api/               # Business logic routers
```
