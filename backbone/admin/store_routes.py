from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from ..core.models import User
from .shared import admin_site, get_admin_user, templates

router = APIRouter()

# ── Store & Settings ──────────────────────────────────────────────────────────

SENSITIVE_KEYS = {
    "secret_key",
    "password",
    "email_password",
    "google_client_secret",
    "google_client_id",
    "cloudinary_url",
    "redis_url",
    "mongodb_url",
    "token",
    "api_key",
    "private_key",
    "hashed_password",
    "client_secret",
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
    from ..core.config import BackboneConfig

    settings = BackboneConfig.get_instance().config
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

        entries.append(
            {
                "key": alias if field_info.alias else field_name.upper(),
                "field_name": field_name,
                "value": display_value,  # masked or real — never raw secret
                "type": type_label,
                "is_sensitive": is_sensitive,
                "from_env": from_env,
                "description": description,
            }
        )

    return entries


@router.get("/store", response_class=HTMLResponse)
async def store_page(request: Request, user: User | None = Depends(get_admin_user)):
    if not user:
        return RedirectResponse(url="/admin/login")

    from ..core.models import Store

    settings = request.app.state.backbone_config.config

    config_entries = _get_config_entries()

    # Flatten Store documents into individual key entries
    store_entries = []
    try:
        all_stores = await Store.find_all().to_list()
        for store_doc in all_stores:
            for key, value in (store_doc.values or {}).items():
                store_entries.append(
                    {
                        "scope": store_doc.scope,
                        "key": key,
                        "value": value,
                        "updated_at": store_doc.updated_at,
                    }
                )
    except Exception:
        pass

    return templates.TemplateResponse(
        request,
        "store.html",
        {
            "request": request,
            "models": admin_site.get_registered_models(),
            "user": user,
            "now": datetime.now(UTC),
            "config_entries": config_entries,
            "store_entries": store_entries,
            "env_source": getattr(settings, "ENVIRONMENT", "develop"),
        },
    )


class StoreEntryRequest(BaseModel):
    scope: str = "global"
    key: str
    value: object  # Any JSON value


class StoreDeleteRequest(BaseModel):
    scope: str
    key: str


@router.post("/store/entry")
async def store_save_entry(payload: StoreEntryRequest, user: User | None = Depends(get_admin_user)):
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
            store_doc.updated_at = datetime.now(UTC)
            await store_doc.save()
        else:
            store_doc = Store(scope=scope, values={key: value})
            await store_doc.insert()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save: {str(e)}")

    return {"status": "ok", "scope": scope, "key": key}


@router.delete("/store/entry")
async def store_delete_entry(
    payload: StoreDeleteRequest, user: User | None = Depends(get_admin_user)
):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    from ..core.models import Store

    scope = payload.scope.strip()
    key = payload.key.strip()

    try:
        store_doc = await Store.find_one(Store.scope == scope)
        if store_doc and key in store_doc.values:
            del store_doc.values[key]
            store_doc.updated_at = datetime.now(UTC)
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
async def config_list_page(request: Request, user: User | None = Depends(get_admin_user)):
    if not user:
        return RedirectResponse(url="/admin/login")

    entries = _get_config_entries()
    env_count = sum(1 for e in entries if e.get("from_env"))
    default_count = len(entries) - env_count

    return templates.TemplateResponse(
        request,
        "config_list.html",
        {
            "request": request,
            "models": admin_site.get_registered_models(),
            "user": user,
            "now": datetime.now(UTC),
            "entries": entries,
            "env_count": env_count,
            "default_count": default_count,
        },
    )
