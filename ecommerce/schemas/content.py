from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from backbone.core.fields import Name, Owner, Text
from backbone.core.models import BackboneDocument


class FAQ(BackboneDocument):
    question: Name = Field(description="The frequently asked question")
    answer: Text = Field(description="The answer to the question")

    class Settings:
        name = "faqs"
        indexes = [IndexModel([("created_at", DESCENDING)], unique=False)]


class Testimonial(BackboneDocument):
    user: Owner | None = Field(
        default=None,
        description="The user who provided the testimonial (if authenticated), or placeholder",
    )
    author_name: str | None = Field(
        default=None, description="Name of the person giving the testimonial"
    )
    content: Text = Field(description="The feedback/content of the testimonial")
    rating: int = Field(default=5, description="Star rating out of 5")
    productImage: str | None = Field(
        default=None, description="Image URL of the product they received"
    )
    avatar_url: str | None = Field(default=None, description="Profile image URL for the reviewer")

    class Settings:
        name = "testimonials"
        indexes = [
            IndexModel([("user.id", ASCENDING)], unique=False),
            IndexModel([("created_at", DESCENDING)], unique=False),
        ]


class Contact(BackboneDocument):
    name: Name = Field(description="The name of the person contacting")
    email: str = Field(description="The email of the person contacting")
    subject: str = Field(description="The subject of the contact message")
    message: Text = Field(description="The content of the contact message")

    class Settings:
        name = "contacts"
        indexes = [
            IndexModel([("email", ASCENDING)], unique=False),
            IndexModel([("created_at", DESCENDING)], unique=False),
        ]


# Resolve forward references
FAQ.model_rebuild()
Testimonial.model_rebuild()
Contact.model_rebuild()
