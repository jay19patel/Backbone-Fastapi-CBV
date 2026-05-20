import os

from bson import ObjectId
from fastapi import Request
from fastapi.templating import Jinja2Templates

from ..common.utils import TokenManager
from ..core.models import User
from .form_utils import INTERNAL_FIELDS, get_model_fields
from .site import admin_site as admin_site


def get_display_fields(model):
    return [
        key
        for key in get_model_fields(model).keys()
        if key not in ["hashed_password", "password"] and key not in INTERNAL_FIELDS
    ]


def get_admin_search_fields(config, model):
    configured = getattr(config["admin"], "search_fields", None)
    if configured:
        return [field for field in configured if field in get_model_fields(model)]

    fallback = []
    for field_name in [
        "name",
        "title",
        "full_name",
        "username",
        "email",
        "filename",
        "question",
        "subject",
        "slug",
    ]:
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


template_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=template_dir)
from .jinja_helpers import register_admin_jinja_env

register_admin_jinja_env(templates.env)


async def get_admin_user(request: Request) -> User | None:
    token = request.cookies.get("admin_session")
    if not token:
        return None

    try:
        payload = TokenManager.decode_token(token)
        if not payload:
            return None

        user_id = payload.get("sub")
        user = await User.get(user_id)
        if user and user.is_superuser:
            return user
    except Exception:
        pass
    return None
