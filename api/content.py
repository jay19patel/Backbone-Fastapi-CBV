from fastapi import APIRouter
from backbone.generic.views import GenericCrudView
from backbone.core.permissions import AllowAny
from schemas.content import FAQ, Testimonial, Contact

class FAQView(GenericCrudView):
    schema = FAQ
    search_fields = ["question", "answer"]
    list_fields = ["id", "question", "answer", "created_at"]
    permission_classes = [AllowAny]

class TestimonialView(GenericCrudView):
    schema = Testimonial
    search_fields = ["content", "author_name"]
    list_fields = ["id", "user", "author_name", "content", "rating", "productImage", "avatar_url", "created_at"]
    fetch_links = True
    permission_classes = [AllowAny]


class ContactView(GenericCrudView):
    schema = Contact
    search_fields = ["name", "email", "subject"]
    list_fields = ["id", "name", "email", "subject", "message", "created_at"]
    permission_classes = [AllowAny]

router = APIRouter()
router.include_router(ContactView.as_router("/content/contact", tags=["Contact"]))
router.include_router(FAQView.as_router("/faqs", tags=["FAQs"]))
router.include_router(TestimonialView.as_router("/testimonials", tags=["Testimonials"]))
