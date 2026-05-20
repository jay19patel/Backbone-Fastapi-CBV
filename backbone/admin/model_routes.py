import math
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from ..core.models import User
from .form_utils import (
    INTERNAL_FIELDS,
    build_field_widgets,
    build_model_payload,
    format_validation_errors,
    get_model_fields,
    snapshot_form_values,
)
from .shared import (
    admin_site,
    build_admin_search_query,
    build_sort_query,
    get_admin_search_fields,
    get_admin_user,
    get_display_fields,
    templates,
)

router = APIRouter()


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
    user: User | None = Depends(get_admin_user),
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

    sort_query, active_sort_field, active_sort_order = build_sort_query(
        model, config, sort_by, order
    )
    items, _ = await repo.get_all(
        query, skip=skip, limit=limit, sort=sort_query, populate_fields=populate_fields
    )
    total_pages = math.ceil(total_count / limit) if limit > 0 else 1

    field_links = {}
    if populate_fields:
        for fname, fconfig in populate_fields.items():
            if isinstance(fconfig, dict) and "collection" in fconfig:
                coll = fconfig["collection"]
                for m_config in admin_site.get_registered_models():
                    if (
                        hasattr(m_config["model"], "Settings")
                        and getattr(m_config["model"].Settings, "name", None) == coll
                    ):
                        field_links[fname] = m_config["name"]
                        break

    return templates.TemplateResponse(
        request,
        "model_list.html",
        {
            "request": request,
            "model_name": model_name,
            "items": items,
            "total_count": total_count,
            "current_page": page,
            "total_pages": total_pages,
            "page_size": limit,
            "models": admin_site.get_registered_models(),
            "user": user,
            "now": datetime.now(UTC),
            "field_links": field_links,
            "model_fields": get_model_fields(model),
            "internal_fields": INTERNAL_FIELDS,
            "display_fields": get_display_fields(model),
            "search_fields": search_fields,
            "search_query": q,
            "active_search_field": search_field,
            "active_sort_field": active_sort_field,
            "active_sort_order": active_sort_order,
            "page_size_options": [10, 20, 50, 100],
        },
    )


async def _load_field_links_and_choices(model) -> tuple[dict, dict, dict]:
    from ..core.repository import BeanieRepository

    populate_fields = BeanieRepository.detect_populate_fields(model)
    link_options: dict = {}
    field_links: dict = {}
    field_choices: dict = {}

    if not populate_fields:
        return link_options, field_links, field_choices

    for fname, fconfig in populate_fields.items():
        if not isinstance(fconfig, dict) or "collection" not in fconfig:
            continue
        coll = fconfig["collection"]
        for model_config in admin_site.get_registered_models():
            target_model = model_config["model"]
            if not hasattr(target_model, "Settings"):
                continue
            if getattr(target_model.Settings, "name", None) != coll:
                continue
            field_links[fname] = model_config["name"]
            try:
                items = await target_model.find_all().limit(20).to_list()
                field_choices[fname] = [
                    {
                        "id": str(item.id),
                        "label": str(
                            getattr(
                                item, "name", getattr(item, "title", getattr(item, "slug", item.id))
                            )
                        ),
                    }
                    for item in items
                ]
            except Exception:
                field_choices[fname] = []
            break

    return link_options, field_links, field_choices


async def _build_create_form_context(
    request: Request,
    model_name: str,
    model,
    user: User | None,
    *,
    form_errors: list | None = None,
    form_error_summary: str = "",
    form_values: dict | None = None,
) -> dict:
    _, field_links, field_choices = await _load_field_links_and_choices(model)
    return {
        "request": request,
        "model_name": model_name,
        "model_fields": get_model_fields(model),
        "internal_fields": INTERNAL_FIELDS,
        "models": admin_site.get_registered_models(),
        "user": user,
        "now": datetime.now(UTC),
        "field_links": field_links,
        "field_choices": field_choices,
        "field_widgets": build_field_widgets(model, field_links),
        "form_errors": form_errors or [],
        "form_error_summary": form_error_summary,
        "form_values": form_values or {},
    }


@router.get("/{model_name}/create", response_class=HTMLResponse)
async def model_create_page(
    request: Request, model_name: str, user: User | None = Depends(get_admin_user)
):
    if not user:
        return RedirectResponse(url="/admin/login")

    config = admin_site.get_model_config(model_name)
    if not config:
        raise HTTPException(status_code=404, detail="Model not found")

    model = config["model"]
    context = await _build_create_form_context(request, model_name, model, user)
    return templates.TemplateResponse(request, "model_create.html", context)


@router.post("/{model_name}/create")
async def model_create_handle(
    request: Request, model_name: str, user: User | None = Depends(get_admin_user)
):
    if not user:
        return RedirectResponse(url="/admin/login")

    config = admin_site.get_model_config(model_name)
    if not config:
        raise HTTPException(status_code=404, detail="Model not found")

    model = config["model"]
    form_data = await request.form()

    try:
        data = await build_model_payload(
            form_data=form_data,
            model=model,
            model_name=model_name,
            user=user,
        )
        instance = model(**data)
        if hasattr(instance, "created_by"):
            instance.created_by = str(user.id)
        await instance.insert()
        return RedirectResponse(url=f"/admin/{model_name}", status_code=status.HTTP_303_SEE_OTHER)
    except ValidationError as exc:
        field_errors, summary = format_validation_errors(exc)
        context = await _build_create_form_context(
            request,
            model_name,
            model,
            user,
            form_errors=field_errors,
            form_error_summary=summary,
            form_values=snapshot_form_values(form_data),
        )
        return templates.TemplateResponse(request, "model_create.html", context, status_code=400)
    except Exception as exc:
        context = await _build_create_form_context(
            request,
            model_name,
            model,
            user,
            form_errors=[{"field": "form", "message": str(exc), "type": "server_error"}],
            form_error_summary="Could not create this record. Check the details below.",
            form_values=snapshot_form_values(form_data),
        )
        return templates.TemplateResponse(request, "model_create.html", context, status_code=400)


@router.post("/{model_name}/delete_all")
async def model_delete_all_handle(
    request: Request, model_name: str, user: User | None = Depends(get_admin_user)
):
    if not user or not user.is_superuser:
        return RedirectResponse(url="/admin/login")

    config = admin_site.get_model_config(model_name)
    if not config:
        raise HTTPException(status_code=404)

    model = config["model"]
    # Delete All
    await model.delete_all()

    return RedirectResponse(url=f"/admin/{model_name}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{model_name}/{pk}", response_class=HTMLResponse)
async def model_detail(
    request: Request, model_name: str, pk: str, user: User | None = Depends(get_admin_user)
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
                    if (
                        hasattr(m_config["model"], "Settings")
                        and getattr(m_config["model"].Settings, "name", None) == coll
                    ):
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
                                vid = (
                                    v.id
                                    if hasattr(v, "id")
                                    else v.get("id")
                                    if isinstance(v, dict)
                                    else v
                                )
                                try:
                                    if isinstance(vid, str | ObjectId):
                                        ids_to_fetch.append(ObjectId(str(vid)))
                                except:
                                    pass

                            items = await target_model.find(
                                {"_id": {"$in": ids_to_fetch}}
                            ).to_list()

                            options = []
                            for it in items:
                                label = str(it.id)
                                for display_field in [
                                    "name",
                                    "title",
                                    "full_name",
                                    "username",
                                    "email",
                                    "filename",
                                    "question",
                                ]:
                                    test_val = getattr(it, display_field, None)
                                    if test_val:
                                        label = f"{test_val} ({it.id})"
                                        break
                                options.append({"id": str(it.id), "label": label})
                            link_options[fname] = options
                        except:
                            pass
                        break

    return templates.TemplateResponse(
        request,
        "model_detail.html",
        {
            "request": request,
            "model_name": model_name,
            "item": item_dict,
            "model_fields": get_model_fields(model),
            "models": admin_site.get_registered_models(),
            "user": user,
            "now": datetime.now(UTC),
            "field_links": field_links,
            "link_options": link_options,
            "internal_fields": INTERNAL_FIELDS,
        },
    )


@router.post("/{model_name}/{pk}")
async def model_update_handle(
    request: Request, model_name: str, pk: str, user: User | None = Depends(get_admin_user)
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
                        if isinstance(val, str) and (val.startswith("[") or val.startswith("{")):
                            try:
                                raw_item[field_name] = json.loads(val)
                                repaired = True
                            except:
                                pass
                        # Case 2: Field is a list containing one string that looks like a JSON array
                        elif (
                            isinstance(val, list)
                            and len(val) == 1
                            and isinstance(val[0], str)
                            and (val[0].startswith("[") or val[0].startswith("{"))
                        ):
                            try:
                                raw_item[field_name] = json.loads(val[0])
                                repaired = True
                            except:
                                pass

                if repaired:
                    try:
                        item = model(**raw_item)
                    except Exception as e2:
                        fetch_error = f"Repair attempted but still failed: {str(e2)}"

                if not item:
                    raise HTTPException(
                        status_code=400, detail=f"ValidationError on record load: {fetch_error}"
                    )
        except HTTPException:
            raise
        except Exception as e:
            # Re-raise as 400 with the error detail so we can see what actually happened
            raise HTTPException(status_code=400, detail=f"Database lookup error: {str(e)}")

        raise HTTPException(
            status_code=404,
            detail="Record not found in the database. Please ensure the ID is correct.",
        )

    form_data = await request.form()
    update_data = await build_model_payload(
        form_data=form_data,
        model=model,
        model_name=model_name,
        user=user,
        document_id=str(pk),
        skip_missing=True,
    )

    for key, field in get_model_fields(model).items():
        if key in INTERNAL_FIELDS:
            continue
        if field.annotation is bool and key not in form_data:
            update_data[key] = False
        if model_name == "User" and key == "hashed_password" and not update_data.get(key):
            update_data.pop(key, None)

    try:
        if hasattr(item, "updated_at"):
            update_data["updated_at"] = datetime.now(UTC)
        if hasattr(item, "updated_by") and user:
            update_data["updated_by"] = str(user.id)

        # Ensure we don't overwrite created_by if it's already there
        if hasattr(item, "created_by") and hasattr(item, "created_at"):
            update_data.pop("created_by", None)
            update_data.pop("created_at", None)

        await item.set(update_data)
        await item.save()  # Guarantee persistence

        response = RedirectResponse(
            url=f"/admin/{model_name}/{pk}", status_code=status.HTTP_303_SEE_OTHER
        )
        # Add a success cookie for the frontend to show a toast/notification
        response.set_cookie("admin_success", f"{model_name} updated successfully", max_age=5)
        return response
    except Exception as e:
        import traceback

        traceback.print_exc()
        error_msg = str(e)
        if "validation" in error_msg.lower():
            if hasattr(e, "errors"):
                try:
                    formatted_errs = [f"{err['loc'][-1]}: {err['msg']}" for err in e.errors()]
                    error_msg = "; ".join(formatted_errs)
                except Exception:
                    pass
        # ? REDIRECT BACK WITH ERROR COOKIE INSTEAD OF GENERIC 400 PAGE
        err_response = RedirectResponse(
            url=f"/admin/{model_name}/{pk}", status_code=status.HTTP_303_SEE_OTHER
        )
        err_response.set_cookie("admin_error", error_msg[:250], max_age=10, path="/")
        return err_response


@router.post("/{model_name}/{pk}/delete")
async def model_delete_handle(
    request: Request, model_name: str, pk: str, user: User | None = Depends(get_admin_user)
):
    if not user or not user.is_superuser:
        return RedirectResponse(url="/admin/login")

    config = admin_site.get_model_config(model_name)
    if not config:
        raise HTTPException(status_code=404)

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
            await item.set({"is_deleted": True, "deleted_at": datetime.now(UTC)})
        else:
            await item.delete()

    return RedirectResponse(url=f"/admin/{model_name}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/api/search/{target_model}")
async def admin_api_search(
    request: Request,
    target_model: str,
    q: str | None = "",
    page: int = 1,
    user: User | None = Depends(get_admin_user),
):
    """
    Generic AJAX endpoint that returns Select2 formatted options manually paginated.
    """
    if not user:
        raise HTTPException(status_code=401)

    config = admin_site.get_model_config(target_model)
    if not config:
        return {"results": [], "pagination": {"more": False}}

    model = config["model"]
    limit = 10
    skip = (page - 1) * limit

    query = {}
    if "is_deleted" in get_model_fields(model):
        query["is_deleted"] = {"$ne": True}

    query = build_admin_search_query(query, q or "", "all", get_admin_search_fields(config, model))

    # ? USE RAW PYMONGO SO VALIDATION ERRORS ON CORRUPTED DOCUMENTS NEVER BREAK THE DROPDOWN
    collection = model.get_pymongo_collection()
    raw_docs = await collection.find(query).skip(skip).limit(limit).to_list(length=limit)
    total = await collection.count_documents(query)

    display_fields = ["name", "title", "full_name", "username", "email", "filename", "question"]
    results = []
    for doc in raw_docs:
        doc_id = str(doc.get("_id", ""))
        label = doc_id
        for field_key in display_fields:
            field_val = doc.get(field_key)
            if field_val and isinstance(field_val, str):
                label = f"{field_val} ({doc_id})"
                break
        results.append({"id": doc_id, "text": label})

    return {
        "results": results,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": math.ceil(total / limit),
    }
