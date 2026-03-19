"""
backbone.utils.media
--------------------
Thin re-export layer.  The canonical implementation lives in backbone.core.media.
DO NOT define process_attachment_upload here — it causes silent shadowing bugs.
"""
from backbone.core.media import process_attachment_upload  # single source of truth

from typing import Optional
from backbone.core.models import Attachment
from backbone.core.config import BackboneConfig


async def get_attachment_cached(attachment_id: str) -> Optional[Attachment]:
    """
    Return an Attachment, preferring the cache when available.
    """
    config = BackboneConfig.get_instance()
    cache_key = f"attachment:{attachment_id}"

    if config.cache_service.enabled:
        cached_data = await config.cache_service.get(cache_key)
        if cached_data:
            return Attachment.model_validate_json(cached_data)

    attachment = await Attachment.get(attachment_id)
    if attachment and config.cache_service.enabled:
        await config.cache_service.set(cache_key, attachment.model_dump_json(), ttl=3600)
    return attachment


__all__ = ["process_attachment_upload", "get_attachment_cached"]
