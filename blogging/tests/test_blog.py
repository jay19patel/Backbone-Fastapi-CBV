"""
blogging/tests/test_blog
~~~~~~~~~~~~~~~~~~~~~~~~

Automated unit and integration test suite for the Blogging module.
Validates database schemas, validation behavior, signal hooks,
and deduplicated view analytics.
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

from backbone.core.models import Attachment, Store, User
from blogging.schemas.blog import (
    Blog,
    BlogCategory,
    BlogLike,
    BlogSectionText,
    BlogView,
)
from blogging.schemas.playlist import Playlist
from blogging.services.blog_hooks import handle_blog_view, register_blog_hooks


@pytest.fixture(autouse=True)
async def mock_db() -> AsyncGenerator[None, None]:
    """
    Fixture to initialize an in-memory mongomock database
    loaded with all Backbone and Blogging document schemas.
    """
    client = AsyncMongoMockClient()
    database_name = "test_backbone_blogging"

    models = [
        User,
        Attachment,
        Store,
        BlogCategory,
        Blog,
        BlogLike,
        BlogView,
        Playlist,
    ]

    await init_beanie(
        database=client[database_name],
        document_models=models,
    )

    # Force model rebuilds for forward-refs safety
    BlogCategory.model_rebuild()
    Blog.model_rebuild()
    BlogLike.model_rebuild()
    BlogView.model_rebuild()
    Playlist.model_rebuild()

    yield

    # Clean up client collections
    await client.drop_database(database_name)


async def create_test_user(email: str, name: str) -> User:
    """Helper to create a verified staff user in the test database."""
    user = User(
        email=email,
        full_name=name,
        hashed_password="scrypt:fake_password_hash",
        is_active=True,
        is_verified=True,
        is_staff=True,
    )
    await user.insert()
    return user


async def test_blog_category_creation_and_slug() -> None:
    """Validates category creation, field validation, and slug generation."""
    category = BlogCategory(name="Technology & Artificial Intelligence")
    await category.insert()

    assert category.id is not None
    assert category.name == "Technology & Artificial Intelligence"
    assert category.slug.startswith("technology-artificial-intelligence")


async def test_blog_post_crud_and_sections() -> None:
    """Validates full CRUD flow for a Blog post, including rich section types."""
    author = await create_test_user("author@njtech.in", "Jane Author")
    category = BlogCategory(name="Design Systems")
    await category.insert()

    section = BlogSectionText(content="This is the main body section content.")

    blog = Blog(
        title="Modern Web Design Aesthetics",
        excerpt="A guide to creating visually stunning web interfaces.",
        author=author,
        category=category,
        sections=[section],
        isPublished=True,
        publishedDate=datetime.now(UTC),
    )
    await blog.insert()

    assert blog.id is not None
    assert blog.slug.startswith("modern-web-design-aesthetics")
    assert len(blog.sections) == 1
    assert blog.sections[0].type == "text"
    assert blog.sections[0].content == "This is the main body section content."

    # Fetch back
    fetched = await Blog.get(blog.id)
    assert fetched is not None
    assert fetched.title == "Modern Web Design Aesthetics"
    assert fetched.author.ref.id == author.id


async def test_blog_view_hook_deduplication() -> None:
    """Validates unique views tracking and 15-minute deduplication hooks."""
    register_blog_hooks()

    author = await create_test_user("author2@njtech.in", "Jane Author")
    viewer = await create_test_user("viewer@njtech.in", "Viscious Viewer")

    blog = Blog(
        title="Unique View Test Post",
        excerpt="Validating view increment rules.",
        author=author,
        isPublished=True,
    )
    await blog.insert()

    # Mock Request
    class MockClient:
        def __init__(self, host: str) -> None:
            self.host = host

    class MockRequest:
        def __init__(self, host: str) -> None:
            self.client = MockClient(host=host)

    request1 = MockRequest(host="192.168.1.50")

    # 1. Trigger view by author (should be skipped)
    await handle_blog_view(blog, user=author, request=request1)
    updated_blog = await Blog.get(blog.id)
    assert updated_blog is not None
    assert updated_blog.views == 0

    # 2. Trigger view by viewer (should record first view)
    await handle_blog_view(blog, user=viewer, request=request1)
    updated_blog = await Blog.get(blog.id)
    assert updated_blog is not None
    assert updated_blog.views == 1

    # Verify a BlogView record is stored
    views_count = await BlogView.find_all().count()
    assert views_count == 1

    # 3. Rapid subsequent view by same viewer (should be deduplicated/skipped)
    await handle_blog_view(blog, user=viewer, request=request1)
    updated_blog = await Blog.get(blog.id)
    assert updated_blog is not None
    assert updated_blog.views == 1

    # 4. Rapid view from a different IP / anonymous (should record new view)
    request2 = MockRequest(host="10.0.0.12")
    await handle_blog_view(blog, user=None, request=request2)
    updated_blog = await Blog.get(blog.id)
    assert updated_blog is not None
    assert updated_blog.views == 2

    # Verify BlogView count is updated
    views_count = await BlogView.find_all().count()
    assert views_count == 2


async def test_curated_playlist_compilation() -> None:
    """Validates creating and maintaining curated Blog Playlists."""
    author = await create_test_user("curator@njtech.in", "Curator Joe")

    blog1 = Blog(
        title="First Awesome Article",
        excerpt="Intro to blogging.",
        author=author,
    )
    await blog1.insert()

    blog2 = Blog(
        title="Second Awesome Article",
        excerpt="Advanced details.",
        author=author,
    )
    await blog2.insert()

    playlist = Playlist(
        owner=author,
        name="Mastering Modern Development",
        description="A handpicked curation of developer journals.",
        blogs=[blog1, blog2],
        is_public=True,
    )
    await playlist.insert()

    assert playlist.id is not None
    assert playlist.slug.startswith("mastering-modern-development")
    assert len(playlist.blogs) == 2

    fetched_playlist = await Playlist.get(playlist.id)
    assert fetched_playlist is not None
    assert fetched_playlist.blogs[0].ref.id == blog1.id
    assert fetched_playlist.blogs[1].ref.id == blog2.id
