from typing import Optional
from pydantic import Field
from backbone.core.models import AuditDocument

class Note(AuditDocument):
    title: str
    content: str
    is_pinned: bool = False

    class Settings:
        name = "notes"
