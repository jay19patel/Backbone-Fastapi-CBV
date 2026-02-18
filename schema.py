from typing import List, Optional
from backbone.core.models import AuditDocument
from pymongo import IndexModel, ASCENDING

class BlogSchema(AuditDocument):
    title: str
    content: str
    author_id: str
    tags: List[str] = []
    
    class Settings:
        name = "blogs"
        indexes = [
            IndexModel([("author_id", ASCENDING)], unique=False)
        ]

class NoteSchema(AuditDocument):
    title: str
    body: str
    is_pinned: bool = False
    
    class Settings:
        name = "notes"
        indexes = [
            IndexModel([("title", ASCENDING)], unique=False),
            IndexModel([("created_by", ASCENDING)], unique=False)
        ]

class PlaylistSchema(AuditDocument):
    name: str
    videos: List[str] = []
    is_public: bool = True
    
    class Settings:
        name = "playlists"
        indexes = [
            IndexModel([("name", ASCENDING)], unique=False),
            IndexModel([("created_by", ASCENDING)], unique=False)
        ]