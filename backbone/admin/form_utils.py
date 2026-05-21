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


def is_attachment_choice_field(field: Any, collection: str | None = None) -> bool:
    """Fields like Thumbnail are stored as Attachment documents or URL strings."""
    annotation = str(getattr(field, "annotation", ""))
    return (collection == "attachments" or "Attachment" in annotation) and "str" in annotation


def _get_field_default(field: Any) -> Any:
    """Return the field's default value, or None if no default is defined."""
    try:
        from pydantic_core import PydanticUndefined

        val = field.default
        return None if val is PydanticUndefined else val
    except Exception:
        return None


def _is_nullable_str(annotation: str) -> bool:
    """Return True for str | None fields that should render as textareas."""
    ann = annotation.lower()
    return (
        "none" in ann
        and "str" in ann
        and "link" not in annotation  # exclude Thumbnail / Attachment
        and "dict" not in ann
        and "list" not in ann
    )


def build_field_widgets(
    model: type[Document], field_links: dict[str, str]
) -> dict[str, dict[str, Any]]:
    widgets: dict[str, dict[str, Any]] = {}
    for name, field in get_model_fields(model).items():
        # ? SKIP TRULY INTERNAL FIELDS AND RAW PLAIN PASSWORD FIELD
        if name in INTERNAL_FIELDS or name == "password":
            continue

        annotation = str(field.annotation)
        widget = "text"

        if name == "hashed_password":
            # ? RENDER AS MASKED PASSWORD INPUT IN ADMIN FORMS
            widget = "password"
        elif field.annotation is bool or "bool" in annotation:
            widget = "bool"
        elif "datetime" in annotation:
            # ? DATETIME FIELDS GET A NATIVE DATE-TIME PICKER
            widget = "datetime"
        elif name in field_links:
            widget = "link"
        elif is_image_field(field):
            widget = "image"
        elif "list" in annotation.lower():
            widget = "list"
        elif field.annotation in (int, float) or "int" in annotation or "float" in annotation:
            widget = "number"
        elif _is_nullable_str(annotation):
            # ? NULLABLE STR FIELDS (e.g. bio, description) GET A TEXTAREA
            widget = "textarea"

        widgets[name] = {
            "widget": widget,
            "required": field.is_required(),
            "description": field.description or f"Enter {name.replace('_', ' ')}",
            "default": _get_field_default(field),
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


def _pick_scalar_form_value(values: list[Any]) -> Any:
    """
    Choose the real scalar value for a single admin field.

    Attachment link widgets submit both a hidden selected-id input and a file
    input with the same field name. When no file is selected, Starlette may
    return the empty UploadFile as the scalar value, hiding the selected id.
    """
    if not values:
        return None

    for value in values:
        if isinstance(value, UploadFile) or is_empty_upload(value):
            continue
        if value not in (None, ""):
            return value

    return values[0]


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


async def resolve_attachment_choice(value: Any) -> Any:
    """Resolve an admin-selected attachment id into an Attachment document."""
    if not value:
        return value

    if isinstance(value, list):
        resolved = []
        for item in value:
            resolved_item = await resolve_attachment_choice(item)
            if resolved_item:
                resolved.append(resolved_item)
        return resolved

    if isinstance(value, Attachment):
        return value

    if hasattr(value, "id"):
        return value

    if isinstance(value, str) and ObjectId.is_valid(value):
        attachment = await Attachment.get(ObjectId(value))
        return attachment or value

    return value


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

        # ? EXPLICIT CLEAR SIGNAL — SENT BY THE REMOVE BUTTON ON LINK/ATTACHMENT FIELDS
        if skip_missing and str(form_data.get(f"_clear_{key}", "")) == "1":
            data[key] = None
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

        field_values = form_data.getlist(key)
        raw = field_values if is_list else _pick_scalar_form_value(field_values)

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
            # ? JINJA RENDERS PYTHON None AS THE LITERAL STRING "None" IN TEXT INPUTS — CONVERT BACK
            if isinstance(val, str) and val == "None":
                val = None
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

        if key == "hashed_password":
            # ? HASH THE PASSWORD IF PROVIDED; SKIP ENTIRELY WHEN BLANK TO PRESERVE EXISTING HASH
            if not val:
                # For update (skip_missing=True) this preserves the current password.
                # For create (skip_missing=False) Pydantic will raise "field required",
                # which surfaces in the form error list.
                continue
            from ..common.utils import PasswordManager

            if isinstance(val, str) and not val.startswith("$argon2"):
                val = PasswordManager.hash_password(val)

        # ? ALWAYS USE GETLIST — FINDS UPLOADFILE EVEN FOR SINGLE FIELDS (BOTH HIDDEN ID + FILE SUBMIT TOGETHER)
        file_candidates = form_data.getlist(key)
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
            if is_attachment_choice_field(field, collection):
                val = await resolve_attachment_choice(val)
            else:

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
        # ? is_image_field skip removed — explicit clear is handled via _clear_ signal above
        if val is None and skip_missing:
            continue

        data[key] = val

    return data
