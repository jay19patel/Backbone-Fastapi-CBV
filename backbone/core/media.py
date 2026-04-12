import os
import base64
import logging
import mimetypes
from pathlib import Path
from backbone.core.models import Attachment
from backbone.core.config import BackboneConfig

logger = logging.getLogger("backbone.media")

# Define the base media directory relative to the project root (for local dev)
BASE_DIR = Path(__file__).resolve().parent.parent.parent
MEDIA_DIR = BASE_DIR / "media"


def _is_cloudinary_configured() -> bool:
    """Check if Cloudinary is configured."""
    try:
        import cloudinary
        config = cloudinary.config()
        return bool(config.cloud_name and config.api_key and config.api_secret)
    except Exception:
        return False


async def _upload_to_cloudinary(file_bytes: bytes, subfolder: str, public_id: str, content_type: str) -> str:
    """
    Upload file bytes to Cloudinary and return the secure URL.
    """
    import cloudinary.uploader

    # Determine resource type from content_type
    resource_type = "image"
    if content_type.startswith("video/"):
        resource_type = "video"
    elif not content_type.startswith("image/"):
        resource_type = "raw"

    result = cloudinary.uploader.upload(
        file_bytes,
        folder=f"blogermenia/{subfolder}",
        public_id=public_id,
        resource_type=resource_type,
        overwrite=True,
    )
    return result["secure_url"]


async def _save_to_local(file_bytes: bytes, subfolder: str, filename: str) -> str:
    """
    Save file bytes to local media directory and return the relative path.
    """
    target_dir = MEDIA_DIR / subfolder
    os.makedirs(target_dir, exist_ok=True)

    file_path = target_dir / filename
    with open(file_path, "wb") as f:
        f.write(file_bytes)

    return f"/media/{subfolder}/{filename}"


async def save_external_image(url: str, subfolder: str, filename: str) -> str:
    """
    Download an external image and save it either to Cloudinary or locally.
    Returns the secure URL or local relative path.
    """
    import httpx
    async with httpx.AsyncClient() as client:
        res = await client.get(url)
        if res.status_code != 200:
            raise Exception(f"Failed to download image from {url}")
        file_bytes = res.content
        content_type = res.headers.get("Content-Type", "image/jpeg")

    if _is_cloudinary_configured():
        return await _upload_to_cloudinary(file_bytes, subfolder, filename.split('.')[0], content_type)
    else:
        return await _save_to_local(file_bytes, subfolder, filename)


async def process_attachment_upload(attachment_id: str, base64_data: str):
    """
    Background task to process and save attachment file.
    Uploads to Cloudinary in production, saves locally in development.
    Automatically links the attachment to the target document's field.
    """
    try:
        attachment = await Attachment.get(attachment_id)
        if not attachment:
            logger.warning("Attachment %s not found for processing.", attachment_id)
            return

        # Determine subfolder based on collection name
        subfolder = attachment.collection_name or "general"

        # Extract extension
        ext = os.path.splitext(attachment.filename)[1]
        if not ext:
            ext = mimetypes.guess_extension(attachment.content_type) or ".bin"
        filename = f"{attachment_id}{ext}"

        # Decode Base64 data
        file_bytes = base64.b64decode(base64_data)

        # Upload to Cloudinary or save locally
        if _is_cloudinary_configured():
            file_url = await _upload_to_cloudinary(
                file_bytes, subfolder, attachment_id, attachment.content_type
            )
        else:
            file_url = await _save_to_local(file_bytes, subfolder, filename)

        # Update attachment status
        attachment.file_path = file_url
        attachment.status = "completed"
        # Convert size to MB and round to 2 decimal places
        size_mb = round(len(file_bytes) / (1024 * 1024), 2)
        attachment.size = size_mb
        await attachment.save()

        # --- Automatic Linking Logic ---
        if attachment.collection_name and attachment.document_id and attachment.field_name:
            # Try to find the model class in registered models
            config = BackboneConfig.get_instance()
            target_model = None
            for model in config.document_models:
                if getattr(model.Settings, "name", None) == attachment.collection_name:
                    target_model = model
                    break
            
            if target_model:
                doc = await target_model.get(attachment.document_id)
                if doc:
                    # Update the specified field with the attachment link
                    setattr(doc, attachment.field_name, attachment)
                    await doc.save()
                    logger.info(
                        "Linked attachment %s to %s:%s.%s",
                        attachment_id,
                        attachment.collection_name,
                        attachment.document_id,
                        attachment.field_name,
                    )

        # Caching logic
        config = BackboneConfig.get_instance()
        if config.cache_service.enabled:
            cache_key = f"attachment:{attachment_id}"
            await config.cache_service.set(cache_key, attachment.model_dump_json(), ttl=3600)
            if attachment.collection_name and attachment.document_id:
                doc_cache_key = f"{attachment.collection_name}:{attachment.document_id}"
                await config.cache_service.delete(doc_cache_key)

    except Exception as e:
        logger.exception("Error in background attachment upload for %s: %s", attachment_id, e)
        attachment = await Attachment.get(attachment_id)
        if attachment:
            attachment.status = "failed"
            await attachment.save()
