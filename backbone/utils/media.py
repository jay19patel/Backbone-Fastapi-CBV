import os
import shutil
from pathlib import Path
from typing import Optional
from backbone.core.models import Attachment
from backbone.core.config import BackboneConfig

# Define the base media directory relative to the project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent
MEDIA_DIR = BASE_DIR / "media"
IMAGES_DIR = MEDIA_DIR / "images"

# Ensure directories exist (skip on read-only filesystems)
try:
    os.makedirs(IMAGES_DIR, exist_ok=True)
except OSError:
    pass

async def process_attachment_upload(attachment_id: str, file_data: bytes, subfolder: str = "images"):
    """
    Background task to process and save attachment file.
    Uses attachment ID as filename.
    """
    try:
        attachment = await Attachment.get(attachment_id)
        if not attachment:
            return
            
        target_dir = MEDIA_DIR / subfolder
        os.makedirs(target_dir, exist_ok=True)
        
        # Extract extension from filename
        ext = os.path.splitext(attachment.filename)[1]
        unique_filename = f"{attachment_id}{ext}"
        file_path = target_dir / unique_filename
        
        # Save file data
        with open(file_path, "wb") as f:
            f.write(file_data)
            
        # Update attachment record
        relative_path = f"/media/{subfolder}/{unique_filename}"
        attachment.file_path = relative_path
        attachment.status = "completed"
        attachment.size = len(file_data)
        await attachment.save()
        
        # Caching logic: Cache the attachment data for fast lookups
        config = BackboneConfig.get_instance()
        if config.cache_service.enabled:
            cache_key = f"attachment:{attachment_id}"
            await config.cache_service.set(cache_key, attachment.model_dump_json(), ttl=3600)
            
            # If associated with a document, invalidate that document's cache if applicable
            if attachment.collection_name and attachment.document_id:
                doc_cache_key = f"{attachment.collection_name}:{attachment.document_id}"
                await config.cache_service.delete(doc_cache_key)
                
    except Exception as e:
        print(f"Error in background upload task: {e}")
        attachment = await Attachment.get(attachment_id)
        if attachment:
            attachment.status = "failed"
            await attachment.save()

async def get_attachment_cached(attachment_id: str) -> Optional[Attachment]:
    """
    Get attachment with caching.
    """
    config = BackboneConfig.get_instance()
    cache_key = f"attachment:{attachment_id}"
    
    if config.cache_service.enabled:
        cached_data = await config.cache_service.get(cache_key)
        if cached_data:
            return Attachment.model_validate_json(cached_data)
            
    attachment = await Attachment.get(attachment_id)
    if attachment and config.cache_service.enabled:
        await config.cache_service.set(cache_key, attachment.model_dump_json(), expire=3600)
    return attachment
