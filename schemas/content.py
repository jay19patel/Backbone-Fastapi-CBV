from typing import Optional
from pydantic import Field, EmailStr
from backbone.core.models import BackboneDocument
from backbone.core.fields import Name, Text, Bool

class FAQ(BackboneDocument):
    question: Name = Field(description="Frequently asked question statement")
    answer: Text = Field(description="Detailed answer or response to the FAQ")
    is_active: Bool = Field(default=True, description="Toggle whether this FAQ is visible on the frontend")

    class Settings:
        name = "faqs"

class Testimonial(BackboneDocument):
    author: Name = Field(description="Full name of the person giving the testimonial")
    content: Text = Field(description="Main body test of the testimonial")
    designation: Text = Field(default=None, description="Job title, company, or relation of the author")
    is_active: Bool = Field(default=True, description="Toggle whether this testimonial should be displayed")

    class Settings:
        name = "testimonials"

class ContactMessage(BackboneDocument):
    name: Name = Field(description="Name of the person who sent the message")
    email: EmailStr = Field(description="Email address of the sender")
    subject: Name = Field(description="Subject line of the contact inquiry")
    message: Text = Field(description="Full text body of the contact message")
    is_read: Bool = Field(default=False, description="Flag indicating if the admin has read this message")

    class Settings:
        name = "contact_messages"
