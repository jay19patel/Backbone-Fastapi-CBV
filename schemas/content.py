from typing import Optional
from pydantic import Field
from pymongo import IndexModel, ASCENDING, DESCENDING
from backbone.core.models import BackboneDocument, User
from backbone.core.fields import Text, Name, Owner

class FAQ(BackboneDocument):
    question: Name = Field(description="The frequently asked question")
    answer: Text = Field(description="The answer to the question")

    class Settings:
        name = "faqs"
        indexes = [
            IndexModel([("created_at", DESCENDING)], unique=False)
        ]

class Testimonial(BackboneDocument):
    user: Owner = Field(description="The user who provided the testimonial")
    content: Text = Field(description="The content of the testimonial")

    class Settings:
        name = "testimonials"
        indexes = [
            IndexModel([("user.id", ASCENDING)], unique=False),
            IndexModel([("created_at", DESCENDING)], unique=False)
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
            IndexModel([("created_at", DESCENDING)], unique=False)
        ]

# Resolve forward references
FAQ.model_rebuild()
Testimonial.model_rebuild()
Contact.model_rebuild()
