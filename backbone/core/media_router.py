import os
import base64
import httpx
import mimetypes
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Body, Request
from pydantic import BaseModel
from typing import Optional, Any
from backbone.generic.views import GenericCustomApi
from backbone.core.permissions import AllowAny
from backbone.core.models import Attachment
from backbone.core.media import process_attachment_upload, _is_cloudinary_configured, _upload_to_cloudinary, _save_to_local
from backbone.utils.tasks import background_task

class MediaRouter(GenericCustomApi):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("schema", Attachment)
        kwargs.setdefault("prefix", "/media")
        kwargs.setdefault("tags", ["Media"])
        kwargs.setdefault("endpoint", "/upload")
        # We need to explicitly allow form-data passing, so we'll override the post method completely
        super().__init__(*args, **kwargs)
        
    def _register_custom_routes(self):
        # Override the default _register_custom_routes because GenericCustomApi expects a JSON Body 
        # and we need to accept Form data + UploadFile for standard HTML file uploads
        @self.router.post(self.endpoint, tags=self.router.tags)
        async def custom_post(
            request: Request,
            file: Optional[UploadFile] = File(None),
            url: Optional[str] = Form(None),
            collection_name: Optional[str] = Form(None),
            document_id: Optional[str] = Form(None),
            field_name: Optional[str] = Form(None)
        ):
            await self._resolve_context(request)
            return await self.post(request, file=file, url=url, collection_name=collection_name, document_id=document_id, field_name=field_name)

    async def post(self, request: Request, file: Optional[UploadFile] = None, url: Optional[str] = None, collection_name: Optional[str] = None, document_id: Optional[str] = None, field_name: Optional[str] = None) -> Any:
        if not file and not url:
            raise HTTPException(status_code=400, detail="Either 'file' or 'url' must be provided.")
            
        file_bytes = None
        content_type = ""
        filename = ""
        
        # 1. Handle URL Download
        if url:
            image_url = url.strip()
            try:
                async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
                    response = await client.get(
                        image_url, 
                        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                    )
                
                if response.status_code != 200:
                    raise HTTPException(status_code=400, detail=f"Failed to fetch image from URL (HTTP {response.status_code}).")
                
                content_type = response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
                if not content_type.startswith("image/"):
                    raise HTTPException(status_code=400, detail=f"URL does not point to an image (content-type: {content_type}).")
                
                ext = mimetypes.guess_extension(content_type) or ".jpg"
                if ext == ".jpe": ext = ".jpg"
                
                url_path = image_url.split("?")[0].rstrip("/")
                raw_filename = url_path.split("/")[-1] or f"image{ext}"
                if not os.path.splitext(raw_filename)[1]:
                    raw_filename = f"{raw_filename}{ext}"
                    
                filename = raw_filename
                file_bytes = response.content
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to download image from URL: {str(e)}")
        
        # 2. Handle File Upload
        elif file:
            filename = file.filename
            content_type = file.content_type
            if not content_type.startswith("image/"):
                raise HTTPException(status_code=400, detail="File provided is not an image.")
            try:
                file_bytes = await file.read()
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")

        # 3. Create Attachment and upload synchronously
        try:
            attachment = Attachment(
                filename=filename,
                content_type=content_type,
                collection_name=collection_name,
                document_id=document_id,
                field_name=field_name,
                status="pending"
            )
            await attachment.insert()

            attachment_id = str(attachment.id)
            subfolder = collection_name or "general"
            ext = os.path.splitext(filename)[1]
            if not ext: ext = mimetypes.guess_extension(content_type) or ".jpg"
            if ext == ".jpe": ext = ".jpg"

            # Upload directly (synchronous — works on serverless too)
            if _is_cloudinary_configured():
                file_url = await _upload_to_cloudinary(
                    file_bytes, subfolder, attachment_id, content_type
                )
            else:
                local_filename = f"{attachment_id}{ext}"
                file_url = await _save_to_local(file_bytes, subfolder, local_filename)
                # Convert local path to full URL
                file_url_response = f"{request.base_url}{file_url.lstrip('/')}"

            # Update attachment with result
            attachment.file_path = file_url
            attachment.status = "completed"
            size_mb = round(len(file_bytes) / (1024 * 1024), 2)
            attachment.size = size_mb
            await attachment.save()

            # Automatic linking (run in background if Redis available, else inline)
            if attachment.collection_name and attachment.document_id and attachment.field_name:
                from backbone.core.config import BackboneConfig
                config = BackboneConfig.get_instance()
                target_model = None
                for model in config.document_models:
                    if getattr(model.Settings, "name", None) == attachment.collection_name:
                        target_model = model
                        break
                if target_model:
                    doc = await target_model.get(attachment.document_id)
                    if doc:
                        setattr(doc, attachment.field_name, attachment)
                        await doc.save()

            # Build response URL
            if file_url.startswith("http"):
                response_url = file_url
            else:
                response_url = f"{request.base_url}{file_url.lstrip('/')}"

            return {
                "id": attachment_id,
                "status": "completed",
                "message": "Upload successful",
                "filename": filename,
                "url": response_url
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to process upload: {str(e)}")

media_api = MediaRouter()
router = media_api.router
