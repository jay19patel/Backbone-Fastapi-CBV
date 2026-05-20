"""
blogging/schemas/blog
~~~~~~~~~~~~~~~~~~~~~

Beanie Documents and Pydantic schemas for the Blogging platform.
Supports rich-media sections, views, likes, and search embeddings.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from beanie import Link
from pydantic import BaseModel, Field, field_serializer, model_validator
from pymongo import ASCENDING, DESCENDING, IndexModel

from backbone.core.fields import Name, Owner, Slug, Text, Thumbnail


class BlogSectionBase(BaseModel):
    """Base class for all rich media and text sections within a blog post."""

    title: str | None = Field(default=None, description="Optional title or header for this section")
    type: str = Field(description="The section content type discriminator")


class BlogSectionText(BlogSectionBase):
    """Standard markdown or plain text section."""

    type: Literal["text"] = "text"
    content: str = Field(description="Body text in markdown or plain text format")


class BlogSectionBullets(BlogSectionBase):
    """Bullet points section."""

    type: Literal["bullets"] = "bullets"
    items: list[str] = Field(default_factory=list, description="List of bullet items")


class BlogSectionTable(BlogSectionBase):
    """Tabular data representation section."""

    type: Literal["table"] = "table"
    headers: list[str] = Field(default_factory=list, description="Table columns/headers")
    rows: list[list[str]] = Field(
        default_factory=list, description="Array of row cells matching headers"
    )


class BlogSectionNote(BlogSectionBase):
    """Highlight or callout note box."""

    type: Literal["note"] = "note"
    content: str = Field(description="Callout content or important notice text")


class BlogSectionLinkItem(BaseModel):
    """Represents a single hyperlink with descriptive metadata."""

    url: str = Field(description="Target destination URL")
    text: str = Field(description="Clickable hyperlinked text")
    description: str | None = Field(default=None, description="Short link helper text")


class BlogSectionLinks(BlogSectionBase):
    """List of resource links or related reading list."""

    type: Literal["links"] = "links"
    links: list[BlogSectionLinkItem] = Field(
        default_factory=list, description="List of hyperlink structures"
    )


class BlogSectionImage(BlogSectionBase):
    """An image section featuring local attachments or remote image URLs."""

    type: Literal["image"] = "image"
    imageUrl: str | None = Field(default=None, description="External image resource URL")
    caption: str | None = Field(default=None, description="Descriptive photo description")
    content: str | None = Field(
        default=None, description="Optional helper text block beside the image"
    )


class BlogSectionCode(BlogSectionBase):
    """A syntax-highlighted code block."""

    type: Literal["code"] = "code"
    language: str = Field(description="Programming language, e.g. python, javascript")
    content: str = Field(description="Code snippets text")


class BlogSectionYoutube(BlogSectionBase):
    """An embedded YouTube video element."""

    type: Literal["youtube"] = "youtube"
    videoId: str = Field(description="YouTube watch video ID or hash code")
    videoTitle: str | None = Field(default=None, description="Title of the video")
    description: str | None = Field(default=None, description="Optional video caption or details")


class BlogSectionFlowchartStep(BaseModel):
    """A single sequential node in a flow diagram."""

    id: str = Field(description="Unique node identifier within the chart")
    title: str = Field(description="Step title text")
    description: str = Field(description="Detailed narrative of this flow milestone")
    color: str | None = Field(default="blue", description="Node highlight color scheme")
    branches: list[BlogSectionFlowchartStep] | None = Field(
        default=None, description="Recursive branch steps"
    )


class BlogSectionFlowchart(BlogSectionBase):
    """Sequential flow chart block to represent process maps."""

    type: Literal["flowchart"] = "flowchart"
    steps: list[BlogSectionFlowchartStep] = Field(
        default_factory=list, description="Primary flowchart path steps"
    )


# Rebuild recursive step schema
BlogSectionFlowchartStep.model_rebuild()

BlogSection = (
    BlogSectionText
    | BlogSectionBullets
    | BlogSectionTable
    | BlogSectionNote
    | BlogSectionLinks
    | BlogSectionImage
    | BlogSectionCode
    | BlogSectionYoutube
    | BlogSectionFlowchart
)

from backbone.core.models import Attachment, BackboneDocument, User  # noqa: F401


class BlogCategory(BackboneDocument):
    """A category classification for blog posts, e.g., Technology, Art, Lifestyle."""

    name: Name = Field(description="The unique name of the blog category")
    slug: Slug(depend="name") = Field(
        default=None, description="URL-friendly identifier for the category"
    )

    class Settings:
        name = "blog_categories"
        return_link_data = ["id", "name", "slug"]
        indexes = [
            IndexModel(
                [("name", ASCENDING)],
                unique=True,
                partialFilterExpression={"is_deleted": {"$eq": False}},
            ),
            IndexModel(
                [("slug", ASCENDING)],
                unique=True,
                partialFilterExpression={"is_deleted": {"$eq": False}},
            ),
        ]


class Blog(BackboneDocument):
    """Represents a rich, interactive blog post or article."""

    title: Name = Field(description="The main title of the blog post")
    subtitle: Text = Field(default=None, description="A shorter subtitle or catchphrase")
    slug: Slug(depend="title") = Field(
        default=None, description="URL-friendly identifier for the blog"
    )

    excerpt: Text = Field(description="A short summary or snippet of the blog")
    introduction: Text = Field(
        default=None, description="The opening paragraph or introduction text"
    )
    sections: list[BlogSection] = Field(
        default_factory=list,
        description="Array of rich media sections making up the body of the blog",
    )
    conclusion: Text = Field(default=None, description="The closing paragraph or final summary")

    author: Owner = Field(description="User ID of the blog's author")
    category: Link[BlogCategory] | None = Field(
        default=None, description="The category this blog belongs to"
    )

    thumbnail: Thumbnail = Field(default=None, description="Cover image or thumbnail for the blog")

    isPublished: bool = Field(
        default=False, description="Flag indicating if the blog is formally live and public"
    )
    publishedDate: datetime | None = Field(
        default=None,
        description="Timestamp when the blog was formally published. Auto-set to current UTC datetime when isPublished is True.",
    )

    @model_validator(mode="after")
    def _auto_set_published_date(self) -> Blog:
        """
        Auto-assign publishedDate to the current UTC datetime whenever
        isPublished is True and no explicit date was provided.
        Draft blogs (isPublished=False) keep publishedDate as None.
        """
        if self.isPublished and self.publishedDate is None:
            self.publishedDate = datetime.now(UTC)
        return self

    # Analytics metrics
    views: int = Field(default=0, description="Cumulative total number of views")
    likes: int = Field(default=0, description="Cumulative total number of likes")

    # Vector search embedding
    embedding: Any | None = Field(
        default=None, description="Vector embeddings array for automated AI search"
    )

    class Settings:
        name = "blogs"
        return_link_data = [
            "id",
            "title",
            "slug",
            "thumbnail",
            "author",
            "category",
            "views",
            "likes",
        ]
        indexes = [
            IndexModel([("slug", ASCENDING)], unique=False),
            IndexModel([("author.$id", ASCENDING)], unique=False),
            IndexModel([("category.$id", ASCENDING)], unique=False),
            IndexModel([("created_at", DESCENDING)], unique=False),
        ]

    @field_serializer("thumbnail", when_used="json")
    def serialize_thumbnail(self, thumbnail: Thumbnail | None):
        from backbone.core.fields import serialize_attachment

        if not thumbnail:
            return None
        return serialize_attachment(thumbnail)

    @field_serializer("sections", when_used="json")
    def serialize_sections(self, sections: list[BlogSection]):
        from backbone.core.fields import serialize_attachment

        result = []
        for sec in sections:
            sec_dict = sec.model_dump(mode="json")
            if "images" in sec_dict and sec_dict["images"]:
                sec_dict["images"] = [serialize_attachment(i) for i in sec_dict["images"]]
            result.append(sec_dict)
        return result


class BlogLike(BackboneDocument):
    """Captures a user liking a specific blog post."""

    user: Owner = Field(description="The user who liked the blog")
    blog: Link[Blog] = Field(description="The specific blog that was liked")

    class Settings:
        name = "blog_likes"
        indexes = [
            IndexModel([("user.$id", ASCENDING), ("blog.$id", ASCENDING)], unique=True),
            IndexModel([("created_at", DESCENDING)], unique=False),
        ]


class BlogView(BackboneDocument):
    """Stores unique article view logs for analytical auditing and deduplication."""

    user: Owner | None = Field(
        default=None, description="The authenticated user who viewed the blog (if applicable)"
    )
    blog: Link[Blog] = Field(description="The specific blog that was viewed")
    ip_address: str | None = Field(
        default=None, description="IP address of the anonymous or authenticated viewer"
    )

    class Settings:
        name = "blog_views"
        indexes = [
            IndexModel([("created_at", DESCENDING)], unique=False),
            IndexModel([("blog.$id", ASCENDING), ("created_at", DESCENDING)], unique=False),
        ]


class BlogPromptState(BaseModel):
    """Refined representation of a blog generated by AI for frontend consumption."""

    title: str = Field(description="Aggregated title of the blog post")
    subtitle: str | None = Field(default=None, description="Post subtitle")
    excerpt: str | None = Field(default=None, description="Short snippet summaries")
    image: str | None = Field(default=None, description="Cover image source url")
    category: str | None = Field(default=None, description="Category classification string")
    tags: list[str] = Field(default_factory=list, description="Array of post tag metrics")
    content: dict[str, Any] = Field(description="Form expectation metadata map")
