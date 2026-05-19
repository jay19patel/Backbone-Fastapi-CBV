"""
backbone.admin.form_utils
~~~~~~~~~~~~~~~~~~~~~~~~~

Shared admin form parsing, upload handling, and validation error formatting.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from beanie import Document
from bson import ObjectId
from bson.dbref import DBRef
from fastapi import UploadFile
from pydantic import ValidationError

from ..core.models import Attachment
from ..core.repository import BeanieRepository

INTERNAL_FIELDS = [
    "id",
    "_id",
    "revision_id",
    "created_at",
    "created_by",
    "updated_at",
    "updated_by",
    "is_deleted",
    "deleted_at",
    "deleted_by",
]


def get_model_fields(model: type[Document]) -> dict[str, Any]:
    all_fields: dict[str, Any] = {}
    for cls in reversed(model.__mro__):
        if hasattr(cls, "model_fields") and isinstance(cls.model_fields, dict):
            all_fields.update(cls.model_fields)
    return all_fields


def is_empty_upload(value: Any) -> bool:
    if isinstance(value, UploadFile):
        return not bool(value.filename and str(value.filename).strip())
    if hasattr(value, "filename") and hasattr(value, "read"):
        return not bool(getattr(value, "filename", None))
    return False


def is_image_field(field: Any) -> bool:
    annotation = str(getattr(field, "annotation", ""))
    extra = (
        field.json_schema_extra
        if isinstance(getattr(field, "json_schema_extra", None), dict)
        else {}
    )
    if extra.get("upload") is False:
        return False
    return "Thumbnail" in annotation or (
        "Attachment" in annotation and ("Link" in annotation or "Union" in annotation)
    )


def build_field_widgets(
    model: type[Document], field_links: dict[str, str]
) -> dict[str, dict[str, Any]]:
    widgets: dict[str, dict[str, Any]] = {}
    for name, field in get_model_fields(model).items():
        if name in INTERNAL_FIELDS or name in ("hashed_password", "password"):
            continue

        annotation = str(field.annotation)
        widget = "text"
        if field.annotation is bool or annotation.endswith("bool"):
            widget = "bool"
        elif field.annotation in (int, float) or "int" in annotation or "float" in annotation:
            widget = "number"
        elif is_image_field(field):
            widget = "image"
        elif name in field_links:
            widget = "link"
        elif "list" in annotation.lower() or "List" in annotation:
            widget = "list"

        widgets[name] = {
            "widget": widget,
            "required": field.is_required(),
            "description": field.description or f"Enter {name.replace('_', ' ')}",
        }
    return widgets


def format_validation_errors(exc: ValidationError) -> tuple[list[dict[str, str]], str]:
    items: list[dict[str, str]] = []
    for error in exc.errors():
        location = error.get("loc", ())
        field_name = ".".join(str(part) for part in location if part != "__root__") or "form"
        items.append(
            {
                "field": field_name,
                "message": error.get("msg", "Invalid value"),
                "type": error.get("type", ""),
            }
        )
    return items, "Some fields are invalid. Review the messages below and try again."


def snapshot_form_values(form_data: Any) -> dict[str, str]:
    values: dict[str, str] = {}
    for key in form_data.keys():
        raw = form_data.get(key)
        if isinstance(raw, UploadFile):
            values[key] = raw.filename or ""
        elif isinstance(raw, list):
            values[key] = ", ".join(
                item.filename if isinstance(item, UploadFile) else str(item) for item in raw
            )
        else:
            values[key] = "" if raw is None else str(raw)
    return values


def sanitize_value_before_save(value: Any, *, is_list: bool) -> Any:
    if is_list and isinstance(value, list | tuple):
        cleaned = [item for item in value if not isinstance(item, UploadFile)]
        return cleaned or None

    if is_empty_upload(value):
        return None

    if isinstance(value, UploadFile):
        return None

    return value


async def process_upload_files(
    *,
    files: list[Any],
    model: type[Document],
    model_name: str,
    field_name: str,
    document_id: str | None = None,
) -> list[Attachment]:
    uploaded: list[Attachment] = []
    collection_name = getattr(model.Settings, "name", model_name.lower())

    for file_obj in files:
        if not isinstance(file_obj, UploadFile) or is_empty_upload(file_obj):
            continue

        attachment = Attachment(
            filename=file_obj.filename,
            content_type=file_obj.content_type,
            collection_name=collection_name,
            document_id=document_id,
            field_name=field_name,
            status="pending",
        )
        await attachment.insert()

        file_bytes = await file_obj.read()
        encoded = base64.b64encode(file_bytes).decode("utf-8")

        from ..common.services import background_internal_task
        from ..core.media import process_attachment_upload

        await background_internal_task(process_attachment_upload, str(attachment.id), encoded)
        uploaded.append(attachment)

    return uploaded


async def build_model_payload(
    *,
    form_data: Any,
    model: type[Document],
    model_name: str,
    user: Any = None,
    document_id: str | None = None,
    skip_missing: bool = False,
) -> dict[str, Any]:
    """Parse multipart admin form into a dict suitable for Beanie model construction."""
    data: dict[str, Any] = {}
    populate_fields_config = BeanieRepository.detect_populate_fields(model)

    for key, field in get_model_fields(model).items():
        if key in INTERNAL_FIELDS:
            continue

        is_list = "list" in str(field.annotation).lower()
        is_link = key in populate_fields_config

        if key not in form_data:
            if skip_missing:
                continue
            if field.annotation is bool:
                data[key] = False
            elif is_list:
                data[key] = []
            continue

        raw = form_data.getlist(key) if is_list else form_data.get(key)

        if is_list:
            if not raw or (len(raw) == 1 and not raw[0]):
                val: Any = []
            else:
                parsed: list[Any] = []
                for item in raw:
                    if isinstance(item, str) and (item.startswith("[") or item.startswith("{")):
                        try:
                            decoded = json.loads(item)
                            if isinstance(decoded, list):
                                parsed.extend(decoded)
                            else:
                                parsed.append(decoded)
                        except json.JSONDecodeError:
                            parsed.append(item)
                    else:
                        parsed.append(item)
                val = parsed
        else:
            val = raw
            if not val and field.annotation is not bool:
                if skip_missing and is_link:
                    continue
                if field.annotation is str:
                    val = ""
                elif skip_missing:
                    continue
                else:
                    val = None

        if field.annotation is bool:
            val = val.lower() == "true" if isinstance(val, str) else bool(val)
        elif field.annotation is int and not is_list:
            try:
                val = int(val) if val not in (None, "") else None
            except (TypeError, ValueError):
                pass
        elif field.annotation is float and not is_list:
            try:
                val = float(val) if val not in (None, "") else None
            except (TypeError, ValueError):
                pass

        if model_name == "User" and key == "hashed_password" and val:
            from ..common.utils import PasswordManager

            if isinstance(val, str) and not val.startswith("$argon2"):
                val = PasswordManager.hash_password(val)

        file_candidates = form_data.getlist(key) if is_list else [form_data.get(key)]
        uploads = await process_upload_files(
            files=file_candidates,
            model=model,
            model_name=model_name,
            field_name=key,
            document_id=document_id,
        )
        if uploads:
            val = uploads if is_list else uploads[0]

        if is_link and val:
            collection = populate_fields_config[key].get("collection")

            def to_dbref(value: Any) -> Any:
                if isinstance(value, str | ObjectId) and ObjectId.is_valid(str(value)):
                    return DBRef(collection=collection, id=ObjectId(str(value)))
                if hasattr(value, "id"):
                    return DBRef(collection=collection, id=ObjectId(str(value.id)))
                return value

            if isinstance(val, list):
                val = [to_dbref(item) for item in val]
            else:
                val = to_dbref(val)

        val = sanitize_value_before_save(val, is_list=is_list)
        if val is None and is_image_field(field):
            continue
        if val is None and skip_missing:
            continue

        data[key] = val

    return data
