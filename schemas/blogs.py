from datetime import datetime
from typing import List, Optional, Dict, Any, Union, Literal
from beanie import Link
from pydantic import BaseModel, Field
from pymongo import IndexModel, ASCENDING, DESCENDING
from backbone.core.models import BackboneDocument, User, Attachment
from backbone.core.fields import Name, Slug, Text, Thumbnail, Owner, Connect

class BlogSectionBase(BaseModel):
    title: Optional[str] = None
    type: str

class BlogSectionText(BlogSectionBase):
    type: Literal["text"] = "text"
    content: str

class BlogSectionBullets(BlogSectionBase):
    type: Literal["bullets"] = "bullets"
    items: List[str]

class BlogSectionTable(BlogSectionBase):
    type: Literal["table"] = "table"
    headers: List[str]
    rows: List[List[str]]

class BlogSectionNote(BlogSectionBase):
    type: Literal["note"] = "note"
    content: str

class BlogSectionLinkItem(BaseModel):
    url: str
    text: str
    description: Optional[str] = None

class BlogSectionLinks(BlogSectionBase):
    type: Literal["links"] = "links"
    links: List[BlogSectionLinkItem]

class BlogSectionImage(BlogSectionBase):
    type: Literal["image"] = "image"
    attachment: Optional[Link[Attachment]] = None  # Resolved generically by Backbone
    caption: Optional[str] = None
    content: Optional[str] = None

class BlogSectionCode(BlogSectionBase):
    type: Literal["code"] = "code"
    language: str
    content: str

class BlogSectionYoutube(BlogSectionBase):
    type: Literal["youtube"] = "youtube"
    videoId: str
    videoTitle: Optional[str] = None
    description: Optional[str] = None

class BlogSectionFlowchartStep(BaseModel):
    id: str
    title: str
    description: str
    color: Optional[str] = "blue"
    branches: Optional[List['BlogSectionFlowchartStep']] = None

class BlogSectionFlowchart(BlogSectionBase):
    type: Literal["flowchart"] = "flowchart"
    steps: List[BlogSectionFlowchartStep]

# Resolve recursive references
BlogSectionFlowchartStep.model_rebuild()

BlogSection = Union[
    BlogSectionText,
    BlogSectionBullets,
    BlogSectionTable,
    BlogSectionNote,
    BlogSectionLinks,
    BlogSectionImage,
    BlogSectionCode,
    BlogSectionYoutube,
    BlogSectionFlowchart
]

from backbone.core.fields import Bool

class BlogCategory(BackboneDocument):
    name: Name = Field(description="The unique name of the blog category")
    slug: Slug(depend="name") = Field(default=None, description="URL-friendly identifier for the category")
    
    class Settings:
        name = "blog_categories"
        return_link_data = ["id", "name", "slug"]
        indexes = [
            IndexModel([("name", ASCENDING)], unique=True),
            IndexModel([("slug", ASCENDING)], unique=True)
        ]

class Blog(BackboneDocument):
    title: Name = Field(description="The main title of the blog post")
    subtitle: Text = Field(default=None, description="A shorter subtitle or catchphrase")
    slug: Slug(depend="title") = Field(default=None, description="URL-friendly identifier for the blog")

    excerpt: Text = Field(description="A short summary or snippet of the blog")
    introduction: Text = Field(default=None, description="The opening paragraph or introduction text")
    sections: List[BlogSection] = Field(default_factory=list, description="Array of rich media sections making up the body of the blog")
    conclusion: Text = Field(default=None, description="The closing paragraph or final summary")

    author: Owner = Field(description="User ID of the blog's author")
    category: Optional[Link[BlogCategory]] = Field(default=None, description="The category this blog belongs to")

    thumbnail: Thumbnail = Field(default=None, description="Cover image or thumbnail for the blog")
    
    isPublished: Bool = Field(default=False, description="Flag indicating if the blog is definitively live and public")
    publishedDate: Optional[datetime] = Field(default=None, description="Timestamp when the blog was formally published")

    # Analytics
    views: int = Field(default=0, description="Cumulative total number of views")
    likes: int = Field(default=0, description="Cumulative total number of likes")

    embedding: Optional[Any] = Field(default=None, description="Vector embeddings array for automated AI search")

    class Settings:
        name = "blogs"
        return_link_data = ["id", "title", "slug", "thumbnail", "author", "category", "views", "likes"]
        indexes = [
            IndexModel([("slug", ASCENDING)], unique=False),
            IndexModel([("author.id", ASCENDING)], unique=False),
            IndexModel([("category.id", ASCENDING)], unique=False),
            IndexModel([("created_at", DESCENDING)], unique=False)
        ]

class BlogLike(BackboneDocument):
    user: Owner = Field(description="The user who liked the blog")
    blog: Connect(Blog) = Field(description="The specific blog that was liked")

    class Settings:
        name = "blog_likes"
        indexes = [
            IndexModel([("user.id", ASCENDING), ("blog.id", ASCENDING)], unique=True),
            IndexModel([("created_at", DESCENDING)], unique=False)
        ]

class BlogView(BackboneDocument):
    user: Optional[Owner] = Field(default=None, description="The authenticated user who viewed the blog (if applicable)")
    blog: Connect(Blog) = Field(description="The specific blog that was viewed")
    ip_address: Optional[str] = Field(default=None, description="IP address of the anonymous or authenticated viewer")

    class Settings:
        name = "blog_views"
        indexes = [
            IndexModel([("created_at", DESCENDING)], unique=False)
        ]

# Resolve forward references
Blog.model_rebuild()
BlogLike.model_rebuild()
BlogView.model_rebuild()
