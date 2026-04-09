from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Type
from .signals import signals
from beanie import Document, PydanticObjectId, Insert, Replace, Save, Delete, Update, before_event, after_event, Link
from slugify import slugify
from pydantic import Field, EmailStr, field_serializer, model_validator
from pymongo import IndexModel, ASCENDING, DESCENDING
from backbone.core.fields import Name, Text, Bool, Thumbnail

class AuditDocument(Document):
    """
    Base Document with audit fields (created_at, updated_at, soft delete).
    """
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp when the document was created")
    created_by: Optional[str] = Field(default=None, description="ID of the user who created this document")
    updated_at: Optional[datetime] = Field(default=None, description="Timestamp when the document was last updated")
    updated_by: Optional[str] = Field(default=None, description="ID of the user who last updated this document")
    is_deleted: bool = Field(default=False, description="Soft delete flag for hiding record without permanent deletion")
    deleted_at: Optional[datetime] = Field(default=None, description="Timestamp when the document was soft-deleted")
    deleted_by: Optional[str] = Field(default=None, description="ID of the user who deleted this document")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self._initial_state = self.model_dump()
        except:
            self._initial_state = {}

    def has_changed(self, field: str) -> bool:
        """Check if a specific field has changed since initialization."""
        return self._initial_state.get(field) != getattr(self, field)

    @after_event(Insert)
    async def _emit_post_create(self):
        await signals.post_create.emit(self)

    @before_event(Replace, Save, Update)
    async def before_update_state(self):
        pass

    @after_event(Replace, Save, Update)
    async def _emit_post_update(self):
        # Detect field changes
        current_state = self.model_dump()
        changed_fields = {}
        
        for field, value in current_state.items():
            if field in self._initial_state and self._initial_state[field] != value:
                changed_fields[field] = (self._initial_state[field], value)
        
        if changed_fields:
            await signals.on_field_change.emit(self, changed_fields=changed_fields)
        
        await signals.post_update.emit(self, changed_fields=changed_fields)

        # Update initial state after replacement/save
        self._initial_state = current_state

    @after_event(Delete)
    async def _emit_post_delete(self):
        await signals.post_delete.emit(self)

    class Settings:
        pass

class EventDocument(AuditDocument):
    """
    Base Document that supports event hooks and state tracking.
    Now inherits hooks from AuditDocument.
    """
    class Settings:
        pass

class User(AuditDocument):
    email: EmailStr = Field(description="User's unique email address")
    full_name: Name = Field(description="User's full name")
    is_active: Bool = Field(default=True, description="Indicates if the user account is active")
    is_staff: Bool = Field(default=False, description="Indicates if the user has staff privileges")
    is_superuser: Bool = Field(default=False, description="Indicates if the user has superuser system privileges")
    hashed_password: str = Field(description="User's hashed password (internal use only)")
    
    # Profile fields
    profile_image: Thumbnail = Field(default=None, description="User's profile image or avatar")

    headline: Text = Field(default=None, max_length=255, description="A short professional headline")
    bio: Text = Field(default=None, description="Detailed bio or about section")
    is_google_account: Bool = Field(default=False, description="Indicates if the user authenticated via Google")

    @model_validator(mode='before')
    @classmethod
    def clean_empty_links(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if data.get("profile_image") == "":
                data["profile_image"] = None
        return data

    class Settings:
        name = "users"
        indexes = [
            IndexModel([("email", ASCENDING)], unique=True)
        ]

class Session(AuditDocument):
    user: Link["User"] = Field(description="Link to the authenticated user")
    refresh_token: str = Field(description="Highly secure refresh token string")
    is_active: bool = Field(default=True, description="Indicates if the session is currently active and valid")
    expires_at: datetime = Field(description="Timestamp when the session mathematically expires")
    user_agent: Optional[str] = Field(default=None, description="Browser or user agent string of the client device")
    ip_address: Optional[str] = Field(default=None, description="Captured IP address of the client device")

    class Settings:
        name = "sessions"
        indexes = [
            IndexModel([("user.$id", ASCENDING)]),
            IndexModel([("refresh_token", ASCENDING)], unique=True)
        ]

class LogEntry(Document):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of the log entry")
    level: str = Field(description="Severity level of the log (INFO, ERROR, etc.)")
    message: str = Field(description="Main log message")
    module: Optional[str] = Field(default=None, description="Name of the module where the log occurred")
    function: Optional[str] = Field(default=None, description="Name of the function where the log occurred")
    line: Optional[int] = Field(default=None, description="Line number of code where the log occurred")
    exception: Optional[str] = Field(default=None, description="Stringified exception trace if an error occurred")
    extra: Optional[Dict[str, Any]] = Field(default=None, description="Additional arbitrary metadata for the log")

    class Settings:
        name = "logs"
        indexes = [
            IndexModel([("level", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)])
        ]

class Task(Document):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of the task recording")
    task_id: str = Field(description="Unique identifier for the background task")
    function_name: str = Field(description="Name of the function executed by the task")
    status: str = Field(default="queued", description="Current status (queued, processing, completed, failed)")
    queued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp when the task was queued")
    started_at: Optional[datetime] = Field(default=None, description="Timestamp when the task started processing")
    completed_at: Optional[datetime] = Field(default=None, description="Timestamp when the task finished execution")
    error_message: Optional[str] = Field(default=None, description="Error message if the task failed")
    error_traceback: Optional[str] = Field(default=None, description="Traceback captured when the task fails")
    execution_time_s: Optional[float] = Field(default=None, description="Total execution time in seconds")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Arbitrary structured metadata for observability")

    class Settings:
        name = "task_logs"
        indexes = [
            IndexModel([("status", ASCENDING)]),
            IndexModel([("task_id", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)])
        ]

class Email(Document):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp when the email job record was created")
    queued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp when the email was queued for sending")
    started_at: Optional[datetime] = Field(default=None, description="Timestamp when sending started")
    sent_at: Optional[datetime] = Field(default=None, description="Timestamp when email was sent")

    to_email: EmailStr = Field(description="Recipient email address")
    subject: str = Field(description="Email subject line")
    from_email: Optional[EmailStr] = Field(default=None, description="Sender email used for this delivery")
    template_name: Optional[str] = Field(default=None, description="Template path used to render email body")
    context: Dict[str, Any] = Field(default_factory=dict, description="Template context payload")
    plain_text_body: Optional[str] = Field(default=None, description="Optional plain text fallback body")
    html_body: Optional[str] = Field(default=None, description="Rendered HTML body")

    attachments: List[Dict[str, Any]] = Field(default_factory=list, description="Explicit attachments metadata")
    pdf_attachments: List[Dict[str, Any]] = Field(default_factory=list, description="Templates to be rendered into PDF attachments")
    status: str = Field(default="queued", description="queued, processing, sent, failed, skipped")
    attempt_count: int = Field(default=0, description="How many send attempts were made")

    error_message: Optional[str] = Field(default=None, description="Failure reason if send failed")
    error_traceback: Optional[str] = Field(default=None, description="Traceback captured when send failed")
    provider_message_id: Optional[str] = Field(default=None, description="Provider response message id when available")

    class Settings:
        name = "email_delivery_logs"
        indexes = [
            IndexModel([("to_email", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)]),
        ]

class Store(Document):
    scope: str = Field(default="global", description="Singleton scope identifier")
    values: Dict[str, Any] = Field(default_factory=dict, description="Flexible key/value map")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp when the store document was created")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp when the store document was last updated")

    class Settings:
        name = "backbone_store"
        indexes = [
            IndexModel([("scope", ASCENDING)], unique=True),
            IndexModel([("updated_at", DESCENDING)]),
        ]

# Backward-compatible aliases
TaskLog = Task
EmailDeliveryLog = Email
BackboneStore = Store

class PasswordResetToken(Document):
    user_id: str = Field(description="ID of the user requesting a password reset")
    email: EmailStr = Field(description="Email associated with the password reset request")
    token_hash: str = Field(description="SHA256 hash of the raw reset token")
    is_active: bool = Field(default=True, description="Whether the reset token is still valid")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp when the token was created")
    expires_at: datetime = Field(description="Timestamp when the token expires")
    used_at: Optional[datetime] = Field(default=None, description="Timestamp when the token was consumed")

    class Settings:
        name = "password_reset_tokens"
        indexes = [
            IndexModel([("token_hash", ASCENDING)], unique=True),
            IndexModel([("user_id", ASCENDING)]),
            IndexModel([("email", ASCENDING)]),
            IndexModel([("is_active", ASCENDING)]),
            IndexModel([("expires_at", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)]),
        ]

class BackboneDocument(AuditDocument):
    """
    Enhanced Document with automatic slug generation and media URL resolution.
    It looks for 'slugify' and media markers in field metadata (json_schema_extra).
    """
    
    @before_event(Insert)
    async def _handle_automatic_slug(self):
        """Generates a slug if a field is marked for slugification."""
        for field_name, field_info in self.model_fields.items():
            # In Pydantic 2, metadata is stored in field_info.metadata for Annotated
            # But we also use json_schema_extra for backward compatibility.
            metadata = {}
            if field_info.json_schema_extra:
                metadata.update(field_info.json_schema_extra)
            
            # Extract from Annotated metadata if present
            for item in field_info.metadata:
                if isinstance(item, dict):
                    metadata.update(item)
                elif hasattr(item, "json_schema_extra"):
                     metadata.update(item.json_schema_extra)

            if metadata.get("slugify"):
                current_val = getattr(self, field_name)
                if not current_val or current_val == "string":
                    populate_from = metadata.get("populate_from") or metadata.get("depend", "name")
                    source_val = getattr(self, populate_from, None)
                    if source_val:
                        import uuid
                        from slugify import slugify
                        base_slug = slugify(str(source_val))
                        entropy = str(uuid.uuid4())[:8]
                        setattr(self, field_name, f"{base_slug}-{entropy}" if base_slug else entropy)


    @model_validator(mode='after')
    def _handle_empty_links(self) -> 'BackboneDocument':
        """Cleans up empty strings in link fields."""
        for field_name, field_info in self.model_fields.items():
            # Check if it's a Link or Attachment related field
            if getattr(self, field_name) == "":
                setattr(self, field_name, None)
        return self

    class Settings:
        pass

class Attachment(Document):
    """
    Universal Attachment model to track all media files.
    """
    filename: str = Field(description="Original name of the uploaded file")
    file_path: Optional[str] = Field(default=None, description="Storage path or URL of the file")
    content_type: str = Field(description="MIME type of the file (e.g. image/png)")
    collection_name: Optional[str] = Field(default=None, description="Name of the collection this attachment is linked to")
    document_id: Optional[str] = Field(default=None, description="ID of the document this attachment belongs to")
    field_name: Optional[str] = Field(default=None, description="Specific field name this attachment is bound to")
    status: str = Field(default="pending", description="Processing status (pending, completed, failed)")
    size: Optional[float] = Field(default=None, description="Size of the file in bytes")
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp when the upload began")
    created_by: Optional[str] = Field(default=None, description="ID of the user who uploaded the file")
    
    @field_serializer('file_path', when_used='json')
    def serialize_file_path(self, file_path: Optional[str]):
        if not file_path: return None
        if file_path.startswith("/media/"):
            from .url_utils import get_media_url
            return get_media_url(file_path)
        return file_path
    
    class Settings:
        name = "attachments"
        # Fields to return when this model is linked/populated
        return_link_data = ["id", "filename", "file_path", "content_type", "status", "size"]
        indexes = [
            IndexModel([("collection_name", ASCENDING)]),
            IndexModel([("document_id", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)])
        ]

# Resolve forward references
User.model_rebuild()
Attachment.model_rebuild()
