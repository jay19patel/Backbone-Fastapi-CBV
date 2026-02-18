from backbone import EventDocument, logger
from backbone.core.models import AuditDocument
from pymongo import IndexModel, ASCENDING
from typing import List
from beanie import Insert, Replace, Save, Delete, Update, before_event, after_event

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

class NoteSchema(EventDocument):
    title: str
    body: str
    is_pinned: bool = False

    @after_event(Insert)
    async def after_create(self):
        logger.info(f"✨ Custom Event: Note created with title '{self.title}'")

    @before_event(Replace, Save, Update)
    async def before_update(self):
        if self.has_changed("title"):
            logger.info(f"📝 Title changed for note {self.id}")
        logger.info(f"💾 Saving updates for note {self.id}")

    @after_event(Delete)
    async def after_delete(self):
        logger.warning(f"🗑️ Note {self.id} was deleted")
    
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