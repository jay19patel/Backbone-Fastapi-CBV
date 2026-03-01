import base64
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
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
        
        # 3. Enqueue background task
        await background_task(process_attachment_upload, str(attachment.id), base64_data)
        
        return {
            "id": str(attachment.id),
            "status": "processing",
            "message": "Upload initiated",
            "filename": file.filename
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initiate upload: {str(e)}")
