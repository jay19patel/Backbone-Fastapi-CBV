import os
import base64
from pathlib import Path
from typing import Optional, Any, Type
from backbone.core.models import Attachment
from backbone.core.config import BackboneConfig
from beanie import Document, Link

# Define the base media directory relative to the project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent
MEDIA_DIR = BASE_DIR / "media"

async def process_attachment_upload(attachment_id: str, base64_data: str):
    """
    Background task to process and save attachment file.
    Decodes Base64 data and saves it to a collection-specific subfolder.
    Automatically links the attachment to the target document's field.
    """
    try:
        attachment = await Attachment.get(attachment_id)
        if not attachment:
            print(f"Attachment {attachment_id} not found.")
            return

        # Determine subfolder based on collection name
        subfolder = attachment.collection_name or "general"
        target_dir = MEDIA_DIR / subfolder
        os.makedirs(target_dir, exist_ok=True)

        # Extract extension and save file
        ext = os.path.splitext(attachment.filename)[1]
        filename = f"{attachment_id}{ext}"
        file_path = target_dir / filename

        # Decode Base64 data
        file_bytes = base64.b64decode(base64_data)
        
        with open(file_path, "wb") as f:
            f.write(file_bytes)

        # Update attachment status
        relative_path = f"/media/{subfolder}/{filename}"
        attachment.file_path = relative_path
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
                    print(f"Linked attachment {attachment_id} to {attachment.collection_name}:{attachment.document_id}.{attachment.field_name}")

        # Caching logic
        config = BackboneConfig.get_instance()
        if config.cache_service.enabled:
            cache_key = f"attachment:{attachment_id}"
            await config.cache_service.set(cache_key, attachment.model_dump_json(), ttl=3600)
            if attachment.collection_name and attachment.document_id:
                doc_cache_key = f"{attachment.collection_name}:{attachment.document_id}"
                await config.cache_service.delete(doc_cache_key)

    except Exception as e:
        print(f"Error in core background upload task: {e}")
        attachment = await Attachment.get(attachment_id)
        if attachment:
            attachment.status = "failed"
            await attachment.save()
