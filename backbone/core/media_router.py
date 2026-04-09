from typing import Optional, Any
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Request
import httpx
import os
import mimetypes
import base64

from backbone.generic.views import GenericCustomApiView
from backbone.core.permissions import AllowAny
from backbone.core.models import Attachment
from backbone.core.media import (
    process_attachment_upload,
)
from backbone.common.services import background_internal_task

class MediaView(GenericCustomApiView):
    schema = Attachment
    permission_classes = [AllowAny]

    @classmethod
    def as_router(cls, prefix: str = "/media", tags: list = ["Media"], **kwargs) -> APIRouter:
        router = APIRouter(prefix=prefix, tags=tags, **kwargs)
        view = cls()
        
        @router.post("/upload")
        async def upload_media(
            request: Request,
            file: Optional[UploadFile] = File(None),
            url: Optional[str] = Form(None),
            collection_name: Optional[str] = Form(None),
            document_id: Optional[str] = Form(None),
            field_name: Optional[str] = Form(None)
        ):
            await view.resolve_context(request)
            return await view.handle_upload(
                request, 
                file=file, 
                url=url, 
                collection_name=collection_name, 
                document_id=document_id, 
                field_name=field_name
            )
        
        return router

    async def handle_upload(
        self, 
        request: Request, 
        file: Optional[UploadFile] = None, 
        url: Optional[str] = None, 
        collection_name: Optional[str] = None, 
        document_id: Optional[str] = None, 
        field_name: Optional[str] = None
    ) -> Any:
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

        # 3. Create Attachment record and process in internal background worker
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
            encoded_payload = base64.b64encode(file_bytes).decode("utf-8")
            internal_task_id = await background_internal_task(
                process_attachment_upload,
                attachment_id,
                encoded_payload,
            )

            # Internal worker never creates Task entries.
            # If Redis worker is disabled, task runs synchronously and this may already be completed.
            attachment = await Attachment.get(attachment_id)
            response_status = attachment.status if attachment else "pending"
            file_url = attachment.file_path if attachment else None
            response_url = None
            if file_url:
                response_url = file_url if file_url.startswith("http") else f"{request.base_url}{file_url.lstrip('/')}"

            return {
                "id": attachment_id,
                "task_id": internal_task_id,
                "status": response_status,
                "message": "Upload accepted and processing in background task.",
                "filename": filename,
                "url": response_url
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to process upload: {str(e)}")

router = MediaView.as_router()
