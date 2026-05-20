from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from ..common.utils import PasswordManager
from ..core.models import User
from .shared import admin_site, get_admin_user, templates

router = APIRouter()


@router.get("/export", response_class=HTMLResponse)
async def export_page(request: Request, user: User | None = Depends(get_admin_user)):
    if not user:
        return RedirectResponse(url="/admin/login")
    models = admin_site.get_registered_models()
    return templates.TemplateResponse(
        request,
        "export.html",
        {
            "request": request,
            "models": models,
            "user": user,
            "now": datetime.now(UTC),
        },
    )


@router.post("/export")
async def export_data(request: Request, user: User | None = Depends(get_admin_user)):
    """
    Export selected models as a single JSON file download.
    Body: application/x-www-form-urlencoded with field `models` (multiple values).
    """
    import json

    from fastapi.responses import StreamingResponse

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
            export_payload[name] = [json.loads(doc.model_dump_json()) for doc in docs]
        except Exception as e:
            export_payload[name] = {"error": str(e)}

    json_bytes = json.dumps(export_payload, indent=2, default=str).encode("utf-8")

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"backbone_export_{timestamp}.json"

    return StreamingResponse(
        iter([json_bytes]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Import ────────────────────────────────────────────────────────────────────


@router.get("/import", response_class=HTMLResponse)
async def import_page(request: Request, user: User | None = Depends(get_admin_user)):
    if not user:
        return RedirectResponse(url="/admin/login")
    models = admin_site.get_registered_models()
    return templates.TemplateResponse(
        request,
        "import.html",
        {
            "request": request,
            "models": models,
            "user": user,
            "now": datetime.now(UTC),
        },
    )


@router.post("/import", response_class=HTMLResponse)
async def import_data(
    request: Request,
    user: User | None = Depends(get_admin_user),
    file: bytes = None,
):
    """
    Import JSON exported by /admin/export.
    Accepts multipart/form-data with a `file` field containing the JSON.
    """
    import json

    if not user or not user.is_superuser:
        return RedirectResponse(url="/admin/login")

    form = await request.form()
    upload = form.get("file")
    if not upload:
        return templates.TemplateResponse(
            request,
            "import.html",
            {
                "request": request,
                "models": admin_site.get_registered_models(),
                "user": user,
                "now": datetime.now(UTC),
                "error": "No file uploaded.",
            },
        )

    try:
        raw = await upload.read()
        payload: dict = json.loads(raw.decode("utf-8"))
    except Exception as e:
        return templates.TemplateResponse(
            request,
            "import.html",
            {
                "request": request,
                "models": admin_site.get_registered_models(),
                "user": user,
                "now": datetime.now(UTC),
                "error": f"Invalid JSON: {e}",
            },
        )

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
    return templates.TemplateResponse(
        request,
        "import.html",
        {
            "request": request,
            "models": models,
            "user": user,
            "now": datetime.now(UTC),
            "summary": summary,
        },
    )


# ── Wipe Database ──────────────────────────────────────────────────────────────


class ApiWipeRequest(BaseModel):
    email: str
    password: str
    create_admin_if_none: bool = False


@router.get("/wipe", response_class=HTMLResponse)
async def wipe_page(request: Request, user: User | None = Depends(get_admin_user)):
    if not user:
        return RedirectResponse(url="/admin/login")
    return templates.TemplateResponse(
        request,
        "wipe.html",
        {
            "request": request,
            "models": admin_site.get_registered_models(),
            "user": user,
            "now": datetime.now(UTC),
            "error": None,
        },
    )


@router.post("/wipe", response_class=HTMLResponse)
async def wipe_database(
    request: Request, password: str = Form(...), user: User | None = Depends(get_admin_user)
):
    """
    Superuser-only: delete ALL documents from every registered model collection.
    Re-creates the admin user.
    """
    if not user or not user.is_superuser:
        return RedirectResponse(url="/admin/login")

    # Verify password first
    if not PasswordManager.verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            request,
            "wipe.html",
            {
                "request": request,
                "models": admin_site.get_registered_models(),
                "user": user,
                "now": datetime.now(UTC),
                "error": "Incorrect password. Wipe aborted.",
            },
        )

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
        except Exception:
            pass

    # Invalidate Cache
    from ..core.config import BackboneConfig

    config = BackboneConfig.get_instance()
    if config.cache_service.enabled:
        await config.cache_service.flush()  # Wipe entire Redis cache for this DB

    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/api/wipe")
async def api_wipe_database(payload: ApiWipeRequest):
    """
    API endpoint to wipe the database.
    Can also create an initial admin user if none exists.
    """
    superuser_count = await User.find({"is_superuser": True}).count()

    if superuser_count == 0 and payload.create_admin_if_none:
        hashed_pw = PasswordManager.hash_password(payload.password)
        new_superuser = User(
            email=payload.email,
            full_name="Admin",
            hashed_password=hashed_pw,
            is_superuser=True,
            is_staff=True,
            is_active=True,
        )
        await new_superuser.insert()
        user = new_superuser
    else:
        user = await User.find_one({"email": payload.email})
        if (
            not user
            or not PasswordManager.verify_password(payload.password, user.hashed_password)
            or not user.is_superuser
        ):
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
        "cleared": results,
    }
