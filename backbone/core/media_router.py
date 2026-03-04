import os
import base64
import httpx
import mimetypes
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Body
from pydantic import BaseModel
from typing import Optional
from .models import Attachment
from .media import process_attachment_upload
from ..utils.tasks import background_task

router = APIRouter(tags=["Media"], prefix="/media")

@router.post("/upload/image")
async def upload_image(
    file: UploadFile = File(...),
    collection_name: Optional[str] = Form(None),
    document_id: Optional[str] = Form(None),
    field_name: Optional[str] = Form(None)
):
    """
    Upload an image file. 
    Creates a pending Attachment record and processes the file in the background using Base64.
    """
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File provided is not an image.")
        
    try:
        # 1. Create a pending Attachment record
        attachment = Attachment(
            filename=file.filename,
            content_type=file.content_type,
            collection_name=collection_name,
            document_id=document_id,
            field_name=field_name,
            status="pending"
        )
        await attachment.insert()
        
        # 2. Read file data and encode to Base64 to avoid Redis bytes serialization issues
        file_bytes = await file.read()
        base64_data = base64.b64encode(file_bytes).decode("utf-8")
        
        # Extrapolate relative path to return immediately
        ext = os.path.splitext(file.filename)[1]
        relative_path = f"/media/{collection_name or 'general'}/{attachment.id}{ext}"

        # 3. Enqueue background task
        await background_task(process_attachment_upload, str(attachment.id), base64_data)
        
        return {
            "id": str(attachment.id),
            "status": "processing",
            "message": "Upload initiated",
            "filename": file.filename,
            "url": f"http://127.0.0.1:8000{relative_path}" # Temporary hardcode for local dev matching other URLs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initiate upload: {str(e)}")


class UploadFromUrlRequest(BaseModel):
    url: str
    collection_name: Optional[str] = None
    document_id: Optional[str] = None
    field_name: Optional[str] = None


@router.post("/upload/url")
async def upload_from_url(data: UploadFromUrlRequest):
    """
    Download an image from a remote URL, save it as an Attachment, 
    and return an ID and URL — same as the file upload endpoint.
    """
    image_url = data.url.strip()
    if not image_url:
        raise HTTPException(status_code=400, detail="URL is required.")

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            response = await client.get(image_url)
        
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Failed to fetch image from URL (HTTP {response.status_code}).")
        
        content_type = response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        if not content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail=f"URL does not point to an image (content-type: {content_type}).")
        
        # Derive extension from content-type
        ext = mimetypes.guess_extension(content_type) or ".jpg"
        if ext == ".jpe": ext = ".jpg"  # normalize jpeg
        
        # Derive a filename from the URL
        url_path = image_url.split("?")[0].rstrip("/")
        raw_filename = url_path.split("/")[-1] or f"image{ext}"
        if not os.path.splitext(raw_filename)[1]:
            raw_filename = f"{raw_filename}{ext}"
        
        file_bytes = response.content
        base64_data = base64.b64encode(file_bytes).decode("utf-8")
        
        # Create Attachment record
        attachment = Attachment(
            filename=raw_filename,
            content_type=content_type,
            collection_name=data.collection_name,
            document_id=data.document_id,
            field_name=data.field_name,
            status="pending"
        )
        await attachment.insert()
        
        relative_path = f"/media/{data.collection_name or 'general'}/{attachment.id}{ext}"
        
        # Enqueue same background processing task
        await background_task(process_attachment_upload, str(attachment.id), base64_data)
        
        return {
            "id": str(attachment.id),
            "status": "processing",
            "message": "URL image download initiated",
            "filename": raw_filename,
            "url": f"http://127.0.0.1:8000{relative_path}"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download image from URL: {str(e)}")

