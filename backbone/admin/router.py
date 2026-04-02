import os
import math
from datetime import datetime, timezone
from typing import Optional, List
from bson import ObjectId
from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict # Added for pydantic models
from ..core.models import User
from ..common.utils import PasswordManager, TokenManager
from .site import admin_site

# Define INTERNAL_FIELDS globally
INTERNAL_FIELDS = ["id", "_id", "revision_id", "created_at", "created_by", "updated_at", "updated_by", "is_deleted", "deleted_at", "deleted_by"]

def get_model_fields(model):
    """
    Returns all Pydantic model_fields including those inherited from parent classes.
    model.model_fields only returns fields declared directly on the class.
    """
    all_fields = {}
    # Walk MRO in reverse so subclass fields override parent fields
    for cls in reversed(model.__mro__):
        if hasattr(cls, "model_fields") and isinstance(cls.model_fields, dict):
            all_fields.update(cls.model_fields)
    return all_fields

def get_display_fields(model):
    return [
        key for key in get_model_fields(model).keys()
        if key not in ["hashed_password", "password"] and key not in INTERNAL_FIELDS
    ]

def get_admin_search_fields(config, model):
    configured = getattr(config["admin"], "search_fields", None)
    if configured:
        return [field for field in configured if field in get_model_fields(model)]

    fallback = []
    for field_name in ["name", "title", "full_name", "username", "email", "filename", "question", "subject", "slug"]:
        if field_name in get_model_fields(model):
            fallback.append(field_name)
    return fallback

def build_admin_search_query(base_query, q, search_field, search_fields):
    query = dict(base_query)
    if not q:
        return query

    clauses = []
    trimmed = q.strip()

    if search_field == "id":
        if ObjectId.is_valid(trimmed):
            clauses.append({"_id": ObjectId(trimmed)})
        else:
            clauses.append({"_id": trimmed})
    else:
        target_fields = search_fields if search_field in ("all", "", None) else [search_field]
        for field_name in target_fields:
            clauses.append({field_name: {"$regex": trimmed, "$options": "i"}})
        if search_field in ("all", "", None) and ObjectId.is_valid(trimmed):
            clauses.append({"_id": ObjectId(trimmed)})

    if not clauses:
        return query

    if query:
        return {"$and": [query, {"$or": clauses}]}
    return {"$or": clauses}

def get_default_sort_field(model, config):
    ordering = getattr(config["admin"], "ordering", None)
    if ordering:
        field_name = ordering[1:] if ordering.startswith("-") else ordering
        if field_name in get_model_fields(model) or field_name == "id":
            return ordering
    if "created_at" in get_model_fields(model):
        return "-created_at"
    return "-id"

def build_sort_query(model, config, sort_by, order):
    requested_field = sort_by or get_default_sort_field(model, config)
    requested_order = order

    if requested_field.startswith("-"):
        requested_order = "desc"
        requested_field = requested_field[1:]

    allowed_fields = set(get_display_fields(model)) | {"id", "created_at", "updated_at"}
    if requested_field not in allowed_fields:
        requested_field = "created_at" if "created_at" in get_model_fields(model) else "id"

    sort_field = "_id" if requested_field == "id" else requested_field
    sort_direction = -1 if requested_order == "desc" else 1
    return [(sort_field, sort_direction)], requested_field, requested_order

router = APIRouter(prefix="/admin")

# Get absolute path to templates
template_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=template_dir)
templates.env.globals["admin_site"] = admin_site

# Custom Filters
def nice_title(value: str) -> str:
    if not value: return ""
    return value.replace("_", " ").title()

def filesize(value) -> str:
    """Format raw bytes into human-readable size (B, KB, MB, GB)."""
    try:
        size = float(value)
    except (TypeError, ValueError):
        return str(value) if value else "—"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(size) < 1024.0:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"

templates.env.filters["nice_title"] = nice_title
templates.env.filters["filesize"] = filesize

# Helper to check if logged in via Cookie
async def get_admin_user(request: Request) -> Optional[User]:
    token = request.cookies.get("admin_session")
    if not token:
        return None
    
    try:
        # Verify token and get user (simplified validation)
        payload = TokenManager.decode_token(token)
        if not payload:
            return None
            
        user_id = payload.get("sub")
        sid = payload.get("sid")
        
        # ideally verify session exists/is active too
        user = await User.get(user_id)
        if user and user.is_superuser:
            return user
    except Exception:
        pass
    return None

@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request, user: Optional[User] = Depends(get_admin_user)):
    if not user:
        return RedirectResponse(url="/admin/login")
    
    models = admin_site.get_registered_models()
    
    # Calculate Database Stats
    db_stats = {
        "total_models": len(models),
        "total_documents": 0,
        "total_size_mb": 0.0,
        "data_size_mb": 0.0,
        "storage_size_mb": 0.0,
        "index_size_mb": 0.0
    }
    
    # Get Global DB Stats (Official MongoDB metrics)
    try:
        if models:
            db = models[0]["model"].get_settings().pymongo_db
            db_stats_raw = await db.command("dbStats")
            db_stats["data_size_mb"] = round(db_stats_raw.get("dataSize", 0) / (1024 * 1024), 2)
            db_stats["storage_size_mb"] = round(db_stats_raw.get("storageSize", 0) / (1024 * 1024), 2)
            db_stats["index_size_mb"] = round(db_stats_raw.get("indexSize", 0) / (1024 * 1024), 2)
            
            total_db_bytes = db_stats_raw.get("totalSize") or (db_stats_raw.get("storageSize", 0) + db_stats_raw.get("indexSize", 0)) or 0
            db_stats["total_size_mb"] = round(total_db_bytes / (1024 * 1024), 2)
    except Exception:
        pass

    model_stats = {}
    for m in models:
        try:
            model = m["model"]
            
            # Safely get Count
            try:
                count = await model.find_all().count()
            except Exception:
                count = 0
            
            # Safely get detailed sizes
            size_mb = 0.0
            data_size_mb = 0.0
            if count > 0:
                try:
                    db = model.get_settings().pymongo_db
                    stats = await db.command("collStats", model.get_collection_name())
                    
                    # Logical/Raw Data Size
                    raw_bytes = stats.get("size") or 0
                    data_size_mb = raw_bytes / (1024 * 1024)
                    
                    # Total Footprint (Storage + Indexes)
                    total_bytes = stats.get("totalSize") or (stats.get("storageSize", 0) + stats.get("totalIndexSize", 0)) or 0
                    size_mb = total_bytes / (1024 * 1024)
                except Exception:
                    pass
            
            model_stats[m["name"]] = {
                "count": count, 
                "size_mb": round(size_mb, 4),      # Real Disk size
                "data_size_mb": round(data_size_mb, 4) # Uncompressed Data size
            }
            db_stats["total_documents"] += count
        except Exception as e:
            import traceback
            traceback.print_exc()
            model_stats[m["name"]] = {"count": 0, "size_mb": 0.0, "data_size_mb": 0.0}
            
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "models": models,
        "pages": admin_site.get_registered_pages(),
        "user": user,
        "now": datetime.now(timezone.utc),
        "db_stats": db_stats,
        "model_stats": model_stats
    })

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    superuser_count = await User.find(User.is_superuser == True).count()
    return templates.TemplateResponse("login.html", {
        "request": request,
        "superuser_exists": superuser_count > 0,
        "error": None
    })

@router.post("/login")
async def login_handle(
    request: Request,
    email: str = Form(...),
    password: str = Form(...)
):
    superuser_count = await User.find(User.is_superuser == True).count()
    
    # 1. Handle Superuser Creation if none exists
    if superuser_count == 0:
        hashed_pw = PasswordManager.hash_password(password)
        new_superuser = User(
            email=email,
            full_name=email.split('@')[0].title() or "Admin",
            hashed_password=hashed_pw,
            is_superuser=True,
            is_staff=True,
            is_active=True
        )
        await new_superuser.insert()
        user = new_superuser
    else:
        # 2. Normal Login via AuthService
        # Fetch user by email manually since AuthService expects email for standard login
        user = await User.find_one(User.email == email)
        
        if not user or not PasswordManager.verify_password(password, user.hashed_password):
             return templates.TemplateResponse("login.html", {
                "request": request,
                "superuser_exists": True,
                "error": "Invalid username or password"
            })
            
        if not user.is_superuser:
            return templates.TemplateResponse("login.html", {
                "request": request,
                "superuser_exists": True,
                "error": "Access denied. Superuser only."
            })

    # Create Session via AuthService
    from ..auth.service import AuthService
    auth_service = AuthService(request)
    
    # We use a manual session creation here because we already verified password
    session_data = await auth_service.create_session(
        user=user, 
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None
    )
    
    access_token = session_data["access_token"]

    response = RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="admin_session", value=access_token, httponly=True)
    return response

@router.get("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/admin/login")
    response.delete_cookie("admin_session")
    
    # Ideally invalidate session in DB too
    token = request.cookies.get("admin_session")
    if token:
         try:
            payload = TokenManager.decode_token(token)
            if payload:
                sid = payload.get("sid")
                from ..auth.service import AuthService
                auth_service = AuthService(request)
                await auth_service.logout(sid)
         except Exception:
             pass

    return response
         

# ── Export ────────────────────────────────────────────────────────────────────

@router.get("/export", response_class=HTMLResponse)
async def export_page(request: Request, user: Optional[User] = Depends(get_admin_user)):
    if not user:
        return RedirectResponse(url="/admin/login")
    models = admin_site.get_registered_models()
    return templates.TemplateResponse("export.html", {
        "request": request,
        "models": models,
        "user": user,
        "now": datetime.now(timezone.utc),
    })


@router.post("/export")
async def export_data(request: Request, user: Optional[User] = Depends(get_admin_user)):
    """
    Export selected models as a single JSON file download.
    Body: application/x-www-form-urlencoded with field `models` (multiple values).
    """
    from fastapi.responses import StreamingResponse
    import json

    if not user:
        raise HTTPException(status_code=401)

    form = await request.form()
    selected = form.getlist("models")

    all_models = {m["name"]: m["model"] for m in admin_site.get_registered_models()}
    export_payload = {}

    for name in selected:
        if name not in all_models:
            continue
        model = all_models[name]
        try:
            docs = await model.find_all().to_list()
            export_payload[name] = [
                json.loads(doc.model_dump_json()) for doc in docs
            ]
        except Exception as e:
            export_payload[name] = {"error": str(e)}

    json_bytes = json.dumps(export_payload, indent=2, default=str).encode("utf-8")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"backbone_export_{timestamp}.json"

    return StreamingResponse(
        iter([json_bytes]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Import ────────────────────────────────────────────────────────────────────

@router.get("/import", response_class=HTMLResponse)
async def import_page(request: Request, user: Optional[User] = Depends(get_admin_user)):
    if not user:
        return RedirectResponse(url="/admin/login")
    models = admin_site.get_registered_models()
    return templates.TemplateResponse("import.html", {
        "request": request,
        "models": models,
        "user": user,
        "now": datetime.now(timezone.utc),
    })


@router.post("/import", response_class=HTMLResponse)
async def import_data(
    request: Request,
    user: Optional[User] = Depends(get_admin_user),
    file: bytes = None,
):
    """
    Import JSON exported by /admin/export.
    Accepts multipart/form-data with a `file` field containing the JSON.
    """
    import json
    from fastapi import UploadFile, File

    if not user or not user.is_superuser:
        return RedirectResponse(url="/admin/login")

    form = await request.form()
    upload = form.get("file")
    if not upload:
        return templates.TemplateResponse("import.html", {
            "request": request,
            "models": admin_site.get_registered_models(),
            "user": user,
            "now": datetime.now(timezone.utc),
            "error": "No file uploaded.",
        })

    try:
        raw = await upload.read()
        payload: dict = json.loads(raw.decode("utf-8"))
    except Exception as e:
        return templates.TemplateResponse("import.html", {
            "request": request,
            "models": admin_site.get_registered_models(),
            "user": user,
            "now": datetime.now(timezone.utc),
            "error": f"Invalid JSON: {e}",
        })

    all_models = {m["name"]: m["model"] for m in admin_site.get_registered_models()}
    summary = {}

    for model_name, docs in payload.items():
        if model_name not in all_models:
            summary[model_name] = {"status": "skipped", "reason": "model not registered"}
            continue

        model = all_models[model_name]
        if not isinstance(docs, list):
            summary[model_name] = {"status": "skipped", "reason": "expected a list of documents"}
            continue

        inserted = 0
        skipped = 0
        for doc_data in docs:
            try:
                # Use motor directly to upsert by _id to avoid duplicates
                collection = model.get_pymongo_collection()
                from bson import ObjectId
                doc_id = doc_data.get("id") or doc_data.get("_id")
                if doc_id:
                    try:
                        doc_data["_id"] = ObjectId(str(doc_id))
                    except Exception:
                        doc_data["_id"] = doc_id
                    doc_data.pop("id", None)

                await collection.replace_one(
                    {"_id": doc_data["_id"]},
                    doc_data,
                    upsert=True,
                )
                inserted += 1
            except Exception:
                skipped += 1

        summary[model_name] = {"inserted": inserted, "skipped": skipped}

    models = admin_site.get_registered_models()
    return templates.TemplateResponse("import.html", {
        "request": request,
        "models": models,
        "user": user,
        "now": datetime.now(timezone.utc),
        "summary": summary,
    })


# ── Wipe Database ──────────────────────────────────────────────────────────────

from pydantic import BaseModel

class ApiWipeRequest(BaseModel):
    email: str
    password: str
    create_admin_if_none: bool = False

@router.get("/wipe", response_class=HTMLResponse)
async def wipe_page(request: Request, user: Optional[User] = Depends(get_admin_user)):
    if not user:
        return RedirectResponse(url="/admin/login")
    return templates.TemplateResponse("wipe.html", {
        "request": request,
        "models": admin_site.get_registered_models(),
        "user": user,
        "now": datetime.now(timezone.utc),
        "error": None
    })

@router.post("/wipe", response_class=HTMLResponse)
async def wipe_database(
    request: Request,
    password: str = Form(...),
    user: Optional[User] = Depends(get_admin_user)
):
    """
    Superuser-only: delete ALL documents from every registered model collection.
    Re-creates the admin user.
    """
    if not user or not user.is_superuser:
        return RedirectResponse(url="/admin/login")

    # Verify password first
    if not PasswordManager.verify_password(password, user.hashed_password):
        return templates.TemplateResponse("wipe.html", {
            "request": request,
            "models": admin_site.get_registered_models(),
            "user": user,
            "now": datetime.now(timezone.utc),
            "error": "Incorrect password. Wipe aborted."
        })

    all_models = admin_site.get_registered_models()
    
    for m in all_models:
        model = m["model"]
        try:
            collection = model.get_pymongo_collection()
            if m["name"] == "User":
                # Delete all except current user
                await collection.delete_many({"_id": {"$ne": user.id}})
            else:
                await collection.delete_many({})
        except Exception as e:
            pass

    # Invalidate Cache
    from ..core.config import BackboneConfig
    config = BackboneConfig.get_instance()
    if config.cache_service.enabled:
        await config.cache_service.flush() # Wipe entire Redis cache for this DB

    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/api/wipe")
async def api_wipe_database(payload: ApiWipeRequest):
    """
    API endpoint to wipe the database.
    Can also create an initial admin user if none exists.
    """
    superuser_count = await User.find(User.is_superuser == True).count()
    
    if superuser_count == 0 and payload.create_admin_if_none:
        hashed_pw = PasswordManager.hash_password(payload.password)
        new_superuser = User(
            email=payload.email,
            full_name="Admin",
            hashed_password=hashed_pw,
            is_superuser=True,
            is_staff=True,
            is_active=True
        )
        await new_superuser.insert()
        user = new_superuser
    else:
        user = await User.find_one(User.email == payload.email)
        if not user or not PasswordManager.verify_password(payload.password, user.hashed_password) or not user.is_superuser:
            raise HTTPException(status_code=401, detail="Invalid admin credentials")
            
    # Do Wipe
    all_models = admin_site.get_registered_models()
    results = {}
    for m in all_models:
        model = m["model"]
        name = m["name"]
        try:
            collection = model.get_pymongo_collection()
            if name == "User":
                 res = await collection.delete_many({"_id": {"$ne": user.id}})
            else:
                 res = await collection.delete_many({})
            results[name] = res.deleted_count
        except Exception as e:
            results[name] = f"error: {e}"
             
    # Cache clear
    from ..core.config import BackboneConfig
    config = BackboneConfig.get_instance()
    if config.cache_service.enabled:
        await config.cache_service.flush()
        
    return {
        "status": "success", 
        "message": "Database wiped successfully", 
        "preserved_admin": str(user.id),
        "cleared": results
    }


# ── Store & Settings ──────────────────────────────────────────────────────────

SENSITIVE_KEYS = {
    "secret_key", "password", "email_password", "google_client_secret", "google_client_id",
    "cloudinary_url", "redis_url", "mongodb_url", "token", "api_key",
    "private_key", "hashed_password", "client_secret"
}

def _is_sensitive(key: str) -> bool:
    k = key.lower()
    if "expire" in k or "username" in k:
        return False
    return any(s in k for s in SENSITIVE_KEYS)

def _mask_value(value) -> str:
    """
    Server-side masking — the real value never reaches the browser.
    Shows last 4 chars for short values, nothing for credential URLs.
    """
    if value is None or value == "":
        return ""
    s = str(value)
    if len(s) <= 4:
        return "••••••••"
    # Show only last 4 characters
    return "••••••••" + s[-4:]

def _get_config_entries() -> list:
    """Extract all settings fields with their current values and metadata.
    Sensitive values are masked SERVER-SIDE before being sent to the template.
    """
    from ..core.settings import Settings, settings
    import os

    # Gather env file keys (to mark from_env=True)
    env_keys = set()
    for env_file in [".env", ".env.prod"]:
        if os.path.exists(env_file):
            try:
                with open(env_file) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            env_keys.add(line.split("=", 1)[0].strip().lower())
            except Exception:
                pass

    entries = []
    for field_name, field_info in settings.model_fields.items():
        raw_val = getattr(settings, field_name, None)

        # Determine type label
        ann = field_info.annotation
        ann_str = str(ann).lower()
        if ann is bool or ann_str == "bool":
            type_label = "bool"
        elif ann is int or ann_str == "int":
            type_label = "int"
        elif ann is float or ann_str == "float":
            type_label = "float"
        else:
            type_label = "str"

        # env alias is used for lookup
        alias = field_info.alias or field_name
        from_env = alias.lower() in env_keys or field_name.lower() in env_keys

        # Description from field metadata
        description = field_info.description or ""

        is_sensitive = _is_sensitive(field_name) or _is_sensitive(alias)

        # ── MASK SERVER-SIDE ──────────────────────────────────────────────
        # Real value is NEVER sent to the browser for sensitive fields.
        display_value = _mask_value(raw_val) if (is_sensitive and raw_val) else raw_val

        entries.append({
            "key": alias if field_info.alias else field_name.upper(),
            "field_name": field_name,
            "value": display_value,        # masked or real — never raw secret
            "type": type_label,
            "is_sensitive": is_sensitive,
            "from_env": from_env,
            "description": description,
        })

    return entries


@router.get("/store", response_class=HTMLResponse)
async def store_page(request: Request, user: Optional[User] = Depends(get_admin_user)):
    if not user:
        return RedirectResponse(url="/admin/login")

    from ..core.models import Store
    from ..core.settings import settings

    config_entries = _get_config_entries()

    # Flatten Store documents into individual key entries
    store_entries = []
    try:
        all_stores = await Store.find_all().to_list()
        for store_doc in all_stores:
            for key, value in (store_doc.values or {}).items():
                store_entries.append({
                    "scope": store_doc.scope,
                    "key": key,
                    "value": value,
                    "updated_at": store_doc.updated_at,
                })
    except Exception:
        pass

    return templates.TemplateResponse("store.html", {
        "request": request,
        "models": admin_site.get_registered_models(),
        "user": user,
        "now": datetime.now(timezone.utc),
        "config_entries": config_entries,
        "store_entries": store_entries,
        "env_source": getattr(settings, "ENVIRONMENT", "develop"),
    })


class StoreEntryRequest(BaseModel):
    scope: str = "global"
    key: str
    value: object  # Any JSON value


class StoreDeleteRequest(BaseModel):
    scope: str
    key: str


@router.post("/store/entry")
async def store_save_entry(payload: StoreEntryRequest, user: Optional[User] = Depends(get_admin_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    from ..core.models import Store

    if not payload.key.strip():
        raise HTTPException(status_code=422, detail="Key cannot be empty")

    scope = payload.scope.strip() or "global"
    key = payload.key.strip()
    value = payload.value

    try:
        store_doc = await Store.find_one(Store.scope == scope)
        if store_doc:
            store_doc.values[key] = value
            store_doc.updated_at = datetime.now(timezone.utc)
            await store_doc.save()
        else:
            store_doc = Store(scope=scope, values={key: value})
            await store_doc.insert()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save: {str(e)}")

    return {"status": "ok", "scope": scope, "key": key}


@router.delete("/store/entry")
async def store_delete_entry(payload: StoreDeleteRequest, user: Optional[User] = Depends(get_admin_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    from ..core.models import Store

    scope = payload.scope.strip()
    key = payload.key.strip()

    try:
        store_doc = await Store.find_one(Store.scope == scope)
        if store_doc and key in store_doc.values:
            del store_doc.values[key]
            store_doc.updated_at = datetime.now(timezone.utc)
            await store_doc.save()
            # If scope document is now empty, optionally delete it
            if not store_doc.values:
                await store_doc.delete()
        else:
            raise HTTPException(status_code=404, detail="Entry not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete: {str(e)}")

    return {"status": "ok", "scope": scope, "key": key}


@router.get("/config", response_class=HTMLResponse)
async def config_list_page(request: Request, user: Optional[User] = Depends(get_admin_user)):
    if not user:
        return RedirectResponse(url="/admin/login")

    entries = _get_config_entries()
    env_count = sum(1 for e in entries if e.get("from_env"))
    default_count = len(entries) - env_count

    return templates.TemplateResponse("config_list.html", {
        "request": request,
        "models": admin_site.get_registered_models(),
        "user": user,
        "now": datetime.now(timezone.utc),
        "entries": entries,
        "env_count": env_count,
        "default_count": default_count,
    })


@router.get("/{model_name}", response_class=HTMLResponse)
async def model_list(
    request: Request, 
    model_name: str, 
    page: int = 1,
    q: str = "",
    search_field: str = "all",
    sort_by: str = "",
    order: str = "desc",
    page_size: int = 20,
    user: Optional[User] = Depends(get_admin_user)
):
    if not user:
        return RedirectResponse(url="/admin/login")
    
    config = admin_site.get_model_config(model_name)
    if not config:
        raise HTTPException(status_code=404, detail="Model not found")
    
    model = config["model"]
    limit = max(10, min(page_size, 100))
    skip = (page - 1) * limit

    base_query = {}
    if "is_deleted" in get_model_fields(model):
        base_query["is_deleted"] = {"$ne": True}

    search_fields = get_admin_search_fields(config, model)
    if search_field not in {"all", "id"} and search_field not in search_fields:
        search_field = "all"

    query = build_admin_search_query(base_query, q, search_field, search_fields)
    total_count = await model.find(query).count()
    
    from ..core.repository import BeanieRepository
    repo = BeanieRepository()
    repo.document_class = model
    populate_fields = BeanieRepository.detect_populate_fields(model)

    sort_query, active_sort_field, active_sort_order = build_sort_query(model, config, sort_by, order)
    items, _ = await repo.get_all(query, skip=skip, limit=limit, sort=sort_query, populate_fields=populate_fields)
    total_pages = math.ceil(total_count / limit) if limit > 0 else 1
    
    field_links = {}
    if populate_fields:
        for fname, fconfig in populate_fields.items():
            if isinstance(fconfig, dict) and "collection" in fconfig:
                coll = fconfig["collection"]
                for m_config in admin_site.get_registered_models():
                    if hasattr(m_config["model"], "Settings") and getattr(m_config["model"].Settings, "name", None) == coll:
                        field_links[fname] = m_config["name"]
                        break
    
    return templates.TemplateResponse("model_list.html", {
        "request": request,
        "model_name": model_name,
        "items": items,
        "total_count": total_count,
        "current_page": page,
        "total_pages": total_pages,
        "page_size": limit,
        "models": admin_site.get_registered_models(),
        "user": user,
        "now": datetime.now(timezone.utc),
        "field_links": field_links,
        "model_fields": get_model_fields(model),
        "internal_fields": INTERNAL_FIELDS,
        "display_fields": get_display_fields(model),
        "search_fields": search_fields,
        "search_query": q,
        "active_search_field": search_field,
        "active_sort_field": active_sort_field,
        "active_sort_order": active_sort_order,
        "page_size_options": [10, 20, 50, 100]
    })

@router.get("/{model_name}/create", response_class=HTMLResponse)
async def model_create_page(
    request: Request,
    model_name: str,
    user: Optional[User] = Depends(get_admin_user)
):
    if not user:
        return RedirectResponse(url="/admin/login")
    
    config = admin_site.get_model_config(model_name)
    if not config:
        raise HTTPException(status_code=404, detail="Model not found")
    
    model = config["model"]
    
    from ..core.repository import BeanieRepository
    populate_fields = BeanieRepository.detect_populate_fields(model)
    
    link_options = {}
    field_links = {}
    field_choices = {}
    
    if populate_fields:
        for fname, fconfig in populate_fields.items():
            if isinstance(fconfig, dict) and "collection" in fconfig:
                coll = fconfig["collection"]
                for m_config in admin_site.get_registered_models():
                    if hasattr(m_config["model"], "Settings") and getattr(m_config["model"].Settings, "name", None) == coll:
                        target_model_name = m_config["name"]
                        target_model = m_config["model"]
                        field_links[fname] = target_model_name
                        
                        # Fetch choices (Top 100 for performance)
                        try:
                            # Use a simple find to get recent items
                            items = await target_model.find_all().limit(20).to_list()
                            choices = []
                            for item in items:
                                # Try to find a good label
                                label = str(getattr(item, "name", getattr(item, "title", getattr(item, "slug", item.id))))
                                choices.append({
                                    "id": str(item.id),
                                    "label": label
                                })
                            field_choices[fname] = choices
                        except:
                            pass
                        break
                        
    return templates.TemplateResponse("model_create.html", {
        "request": request,
        "model_name": model_name,
        "model_fields": get_model_fields(model),
        "internal_fields": INTERNAL_FIELDS, 
        "models": admin_site.get_registered_models(),
        "user": user,
        "now": datetime.now(timezone.utc),
        "field_links": field_links,
        "field_choices": field_choices
    })

@router.post("/{model_name}/create")
async def model_create_handle(
    request: Request,
    model_name: str,
    user: Optional[User] = Depends(get_admin_user)
):
    if not user:
        return RedirectResponse(url="/admin/login")
    
    config = admin_site.get_model_config(model_name)
    if not config:
        raise HTTPException(status_code=404, detail="Model not found")
    
    model = config["model"]
    form_data = await request.form()
    
    # Filter and cast form data
    data = {}
    
    for key, field in get_model_fields(model).items():
        if key in INTERNAL_FIELDS:
            continue
            
        is_list = "list" in str(field.annotation).lower()
        is_link = "link" in str(field.annotation).lower()
        
        if key in form_data:
            val = form_data.getlist(key) if is_list else form_data[key]
            
            if is_list:
                if not val or (len(val) == 1 and not val[0]):
                    val = []
            elif not val and field.annotation != bool:
                continue
                
            # Simple type casting
            if field.annotation == bool:
                val = val.lower() == "true" if isinstance(val, str) else bool(val)
            elif field.annotation == int and not is_list:
                try: val = int(val)
                except: pass
            elif field.annotation == float and not is_list:
                try: val = float(val)
                except: pass
                
            if model_name == "User" and key == "hashed_password" and val:
                from ..common.utils import PasswordManager
                if isinstance(val, str) and not val.startswith("$argon2"):
                    val = PasswordManager.hash_password(val)
                    
            if is_link and val:
                from ..core.repository import BeanieRepository
                from bson import ObjectId
                from bson.dbref import DBRef
                populate_fields = BeanieRepository.detect_populate_fields(model)
                if key in populate_fields:
                    collection_name = populate_fields[key].get("collection")
                    if collection_name:
                        if is_list and isinstance(val, list):
                            new_val = []
                            for item_id in val:
                                try:
                                    if len(str(item_id)) == 24:
                                        new_val.append(DBRef(collection=collection_name, id=ObjectId(item_id)))
                                except: pass
                            val = new_val
                        elif isinstance(val, str) and len(val) == 24:
                            try:
                                val = DBRef(collection=collection_name, id=ObjectId(val))
                            except: pass
                    
            data[key] = val
            
    try:
        instance = model(**data)
        if hasattr(instance, "created_by"):
            instance.created_by = str(user.id)
        await instance.insert()
        return RedirectResponse(url=f"/admin/{model_name}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        # For now simple error, ideally re-render with error
        raise HTTPException(status_code=400, detail=f"Creation failed: {str(e)}")

@router.post("/{model_name}/delete_all")
async def model_delete_all_handle(
    request: Request,
    model_name: str,
    user: Optional[User] = Depends(get_admin_user)
):
    if not user or not user.is_superuser:
        return RedirectResponse(url="/admin/login")
    
    config = admin_site.get_model_config(model_name)
    if not config: raise HTTPException(status_code=404)
    
    model = config["model"]
    # Delete All
    await model.delete_all()
    
    return RedirectResponse(url=f"/admin/{model_name}", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/{model_name}/{pk}", response_class=HTMLResponse)
async def model_detail(
    request: Request,
    model_name: str,
    pk: str,
    user: Optional[User] = Depends(get_admin_user)
):
    if not user:
        return RedirectResponse(url="/admin/login")
    
    config = admin_site.get_model_config(model_name)
    if not config:
        raise HTTPException(status_code=404, detail="Model not found")
    
    model = config["model"]
    
    from bson import ObjectId
    from ..core.repository import BeanieRepository
    
    repo = BeanieRepository()
    repo.document_class = model
    populate_fields = BeanieRepository.detect_populate_fields(model)
    
    # query
    query = {"_id": pk}
    try:
        if len(str(pk)) == 24:
            query = {"_id": ObjectId(pk)}
    except:
        pass
        
    item_dict = await repo.get_one(query, populate_fields=populate_fields)
    
    
    if not item_dict:
        raise HTTPException(status_code=404, detail="Record not found")

    field_links = {}
    link_options = {}
    if populate_fields:
        for fname, fconfig in populate_fields.items():
            if isinstance(fconfig, dict) and "collection" in fconfig:
                coll = fconfig["collection"]
                for m_config in admin_site.get_registered_models():
                    if hasattr(m_config["model"], "Settings") and getattr(m_config["model"].Settings, "name", None) == coll:
                        target_model_name = m_config["name"]
                        target_model = m_config["model"]
                        field_links[fname] = target_model_name
                        
                        # Fetch ONLY the selected items to pre-populate the dropdown
                        try:
                            val = item_dict.get(fname)
                            if not val:
                                break
                                
                            val_list = val if isinstance(val, list) else [val]
                            val_list = [v for v in val_list if v]
                            
                            if not val_list:
                                break
                                
                            from bson import ObjectId
                            ids_to_fetch = []
                            for v in val_list:
                                vid = v.id if hasattr(v, "id") else v.get("id") if isinstance(v, dict) else v
                                try:
                                    if isinstance(vid, (str, ObjectId)):
                                        ids_to_fetch.append(ObjectId(str(vid)))
                                except: pass
                                
                            items = await target_model.find({"_id": {"$in": ids_to_fetch}}).to_list()
                            
                            options = []
                            for it in items:
                                label = str(it.id)
                                for display_field in ["name", "title", "full_name", "username", "email", "filename", "question"]:
                                    test_val = getattr(it, display_field, None)
                                    if test_val:
                                        label = f"{test_val} ({it.id})"
                                        break
                                options.append({"id": str(it.id), "label": label})
                            link_options[fname] = options
                        except:
                            pass
                        break

    return templates.TemplateResponse("model_detail.html", {
        "request": request,
        "model_name": model_name,
        "item": item_dict,
        "model_fields": get_model_fields(model),
        "models": admin_site.get_registered_models(),
        "user": user,
        "now": datetime.now(timezone.utc),
        "field_links": field_links,
        "link_options": link_options,
        "internal_fields": INTERNAL_FIELDS
    })

@router.post("/{model_name}/{pk}")
async def model_update_handle(
    request: Request,
    model_name: str,
    pk: str,
    user: Optional[User] = Depends(get_admin_user)
):
    if not user:
        return RedirectResponse(url="/admin/login")
    
    config = admin_site.get_model_config(model_name)
    if not config:
        raise HTTPException(status_code=404, detail="Model not found")
    
    model = config["model"]
    item = None
    fetch_error = None
    
    try:
        item = await model.get(pk)
    except Exception as e:
        fetch_error = str(e)

    if not item:
        from bson import ObjectId
        try:
            item = await model.find_one({"_id": ObjectId(pk)})
        except Exception as e:
            if not fetch_error:
                fetch_error = str(e)
        
    if not item:
        # Check if the record actually exists in DB but failed validation
        from bson import ObjectId
        try:
            # Try as ObjectId first, then as string
            raw_pkt = ObjectId(pk) if len(str(pk)) == 24 else pk
            raw_item = await model.get_pymongo_collection().find_one({"_id": raw_pkt})
            if not raw_item and isinstance(raw_pkt, ObjectId):
                raw_item = await model.get_pymongo_collection().find_one({"_id": str(pk)})
            
            if raw_item:
                # ── Transparent Repair logic ──
                import json
                repaired = False
                for field_name, field_info in get_model_fields(model).items():
                    is_list = "list" in str(field_info.annotation).lower()
                    if is_list and field_name in raw_item:
                        val = raw_item[field_name]
                        # Case 1: Field is a string that looks like a JSON array
                        if isinstance(val, str) and (val.startswith('[') or val.startswith('{')):
                             try:
                                raw_item[field_name] = json.loads(val)
                                repaired = True
                             except: pass
                        # Case 2: Field is a list containing one string that looks like a JSON array
                        elif isinstance(val, list) and len(val) == 1 and isinstance(val[0], str) and (val[0].startswith('[') or val[0].startswith('{')):
                             try:
                                raw_item[field_name] = json.loads(val[0])
                                repaired = True
                             except: pass
                
                if repaired:
                    try:
                        item = model(**raw_item)
                    except Exception as e2:
                        fetch_error = f"Repair attempted but still failed: {str(e2)}"
                
                if not item:
                    raise HTTPException(status_code=400, detail=f"ValidationError on record load: {fetch_error}")
        except HTTPException:
            raise
        except Exception as e:
            # Re-raise as 400 with the error detail so we can see what actually happened
            raise HTTPException(status_code=400, detail=f"Database lookup error: {str(e)}")
            
        raise HTTPException(status_code=404, detail="Record not found in the database. Please ensure the ID is correct.")

    form_data = await request.form()
    update_data = {}
    
    for key, field in get_model_fields(model).items():
        if key in INTERNAL_FIELDS:
            continue
            
        is_list = "list" in str(field.annotation).lower()
        is_link = "link" in str(field.annotation).lower()

        if key in form_data:
            val = form_data.getlist(key) if is_list else form_data[key]
            
            if is_list:
                if not val or (len(val) == 1 and not val[0]):
                    val = []
                else:
                    import json
                    parsed_val = []
                    for v in val:
                        if isinstance(v, str) and (v.startswith('[') or v.startswith('{')):
                            try:
                                parsed_v = json.loads(v)
                                if isinstance(parsed_v, list):
                                    parsed_val.extend(parsed_v)
                                else:
                                    parsed_val.append(parsed_v)
                            except Exception:
                                parsed_val.append(v)
                        else:
                            parsed_val.append(v)
                    val = parsed_val
            elif not val and field.annotation != bool:
                if is_link:
                    val = None
                else:
                    if field.annotation == str:
                        val = ""
                    else:
                        val = None

            if field.annotation == bool:
                val = val.lower() == "true" if isinstance(val, str) else bool(val)
            elif field.annotation == int and not is_list:
                try: val = int(val) if val is not None and val != "" else None
                except: pass
            elif field.annotation == float and not is_list:
                try: val = float(val) if val is not None and val != "" else None
                except: pass

            if model_name == "User" and key == "hashed_password" and val:
                from ..common.utils import PasswordManager
                if isinstance(val, str) and not val.startswith("$argon2"):
                    val = PasswordManager.hash_password(val)

            if is_link and val:
                from ..core.repository import BeanieRepository
                from bson import ObjectId
                from bson.dbref import DBRef
                populate_fields = BeanieRepository.detect_populate_fields(model)
                if key in populate_fields:
                    collection_name = populate_fields[key].get("collection")
                    if collection_name:
                        if is_list and isinstance(val, list):
                            new_val = []
                            for item_id in val:
                                try:
                                    if len(str(item_id)) == 24:
                                        new_val.append(DBRef(collection=collection_name, id=ObjectId(item_id)))
                                except: pass
                            val = new_val
                        elif isinstance(val, str) and len(val) == 24:
                            try:
                                val = DBRef(collection=collection_name, id=ObjectId(val))
                            except: pass

            update_data[key] = val
        else:
            if field.annotation == bool:
                update_data[key] = False
            elif is_list:
                update_data[key] = []

    try:
        if hasattr(item, "updated_at"):
            update_data["updated_at"] = datetime.now(timezone.utc)
        if hasattr(item, "updated_by"):
            update_data["updated_by"] = str(user.id)
            
        await item.set(update_data)
        return RedirectResponse(url=f"/admin/{model_name}/{pk}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        import traceback
        traceback.print_exc()
        # Try to provide a cleaner error message for Pydantic/Beanie validation errors
        error_msg = str(e)
        if "validation" in error_msg.lower():
            if hasattr(e, "errors"):
                # Pydantic 2 specific error formatting
                try:
                    formatted_errs = [f"{err['loc'][-1]}: {err['msg']}" for err in e.errors()]
                    error_msg = "; ".join(formatted_errs)
                except:
                    pass
        raise HTTPException(status_code=400, detail=f"Update validation failed: {error_msg}")

@router.get("/{model_name}/{pk}/delete")
async def model_delete_handle(
    request: Request,
    model_name: str,
    pk: str,
    user: Optional[User] = Depends(get_admin_user)
):
    if not user or not user.is_superuser:
        return RedirectResponse(url="/admin/login")
    
    config = admin_site.get_model_config(model_name)
    if not config: raise HTTPException(status_code=404)
    
    model = config["model"]
    try:
        item = await model.get(pk)
    except Exception:
        item = None
        
    if not item:
        from bson import ObjectId
        try:
            item = await model.find_one({"_id": ObjectId(pk)})
        except Exception:
            pass
            
    if item:
        if hasattr(item, "is_deleted"):
            await item.set({"is_deleted": True, "deleted_at": datetime.now(timezone.utc)})
        else:
            await item.delete()
            
    return RedirectResponse(url=f"/admin/{model_name}", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/api/search/{target_model}")
async def admin_api_search(
    request: Request,
    target_model: str,
    q: Optional[str] = "",
    page: int = 1,
    user: Optional[User] = Depends(get_admin_user)
):
    """
    Generic AJAX endpoint that returns Select2 formatted options manually paginated.
    """
    if not user:
         raise HTTPException(status_code=401)
         
    config = admin_site.get_model_config(target_model)
    if not config: return {"results": [], "pagination": {"more": False}}
    
    model = config["model"]
    limit = 10
    skip = (page - 1) * limit
    
    query = {}
    if "is_deleted" in get_model_fields(model):
        query["is_deleted"] = {"$ne": True}

    query = build_admin_search_query(query, q or "", "all", get_admin_search_fields(config, model))
            
    items = await model.find(query).skip(skip).limit(limit).to_list()
    total = await model.find(query).count()
    
    results = []
    for it in items:
        label = str(it.id)
        for display_field in ["name", "title", "full_name", "username", "email", "filename", "question"]:
            val = getattr(it, display_field, None)
            if val:
                label = f"{val} ({it.id})"
                break
        results.append({"id": str(it.id), "text": label})
        
    return {
        "results": results,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": math.ceil(total / limit)
    }
