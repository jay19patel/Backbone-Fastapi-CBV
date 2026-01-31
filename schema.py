from typing import List
from backbone.schemas import AuditSchema

class BlogSchema(AuditSchema):
    title: str
    content: str
    author_id: str
    tags: List[str] = []
    
    # Metadata for MongoDB collection management
    class Meta:
        collection_name = "blogs"
        indexes = [
            {"fields": ["author_id"], "unique": False}
        ]

class NoteSchema(AuditSchema):
    title: str
    body: str
    is_pinned: bool = False
    
    class Meta:
        collection_name = "notes"
        indexes = [
            {"fields": ["title"], "unique": False},
            {"fields": ["created_by"], "unique": False} 
        ]

class PlaylistSchema(AuditSchema):
    name: str
    videos: List[str] = []
    is_public: bool = True
    
    class Meta:
        collection_name = "playlists"
        indexes = [
            {"fields": ["name"], "unique": False},
            {"fields": ["created_by"], "unique": False}
        ]