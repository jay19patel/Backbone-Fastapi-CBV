from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..core.models import User
from .shared import admin_site, get_admin_user, templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request, user: User | None = Depends(get_admin_user)):
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
        "index_size_mb": 0.0,
    }

    # Get Global DB Stats (Official MongoDB metrics)
    try:
        if models:
            db = models[0]["model"].get_settings().pymongo_db
            db_stats_raw = await db.command("dbStats")
            db_stats["data_size_mb"] = round(db_stats_raw.get("dataSize", 0) / (1024 * 1024), 2)
            db_stats["storage_size_mb"] = round(
                db_stats_raw.get("storageSize", 0) / (1024 * 1024), 2
            )
            db_stats["index_size_mb"] = round(db_stats_raw.get("indexSize", 0) / (1024 * 1024), 2)

            total_db_bytes = (
                db_stats_raw.get("totalSize")
                or (db_stats_raw.get("storageSize", 0) + db_stats_raw.get("indexSize", 0))
                or 0
            )
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
                    total_bytes = (
                        stats.get("totalSize")
                        or (stats.get("storageSize", 0) + stats.get("totalIndexSize", 0))
                        or 0
                    )
                    size_mb = total_bytes / (1024 * 1024)
                except Exception:
                    pass

            model_stats[m["name"]] = {
                "count": count,
                "size_mb": round(size_mb, 4),  # Real Disk size
                "data_size_mb": round(data_size_mb, 4),  # Uncompressed Data size
            }
            db_stats["total_documents"] += count
        except Exception:
            import traceback

            traceback.print_exc()
            model_stats[m["name"]] = {"count": 0, "size_mb": 0.0, "data_size_mb": 0.0}

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "request": request,
            "models": models,
            "pages": admin_site.get_registered_pages(),
            "user": user,
            "now": datetime.now(UTC),
            "db_stats": db_stats,
            "model_stats": model_stats,
        },
    )
