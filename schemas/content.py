from typing import Optional
from pydantic import Field
from backbone.core.models import AuditDocument

class FAQ(AuditDocument):
    question: str
    answer: str
    is_active: bool = True

    class Settings:
        name = "faqs"

class Testimonial(AuditDocument):
    author: str
    content: str
    designation: Optional[str] = None
    is_active: bool = True

    class Settings:
        name = "testimonials"

class ContactMessage(AuditDocument):
    name: str
    email: str
    subject: str
    message: str
    is_read: bool = False

    class Settings:
        name = "contact_messages"
