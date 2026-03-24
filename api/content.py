from fastapi import APIRouter
from backbone import GenericCrud, AllowAny, IsAuthenticated
from schemas.content import FAQ, Testimonial

faq_crud = GenericCrud(
    schema=FAQ,
    prefix="/faqs",
    tags=["FAQs"],
    search_fields=["question", "answer"],
    list_fields=["id", "question", "answer", "created_at"],
    permission_classes=[AllowAny]
)

testimonial_crud = GenericCrud(
    schema=Testimonial,
    prefix="/testimonials",
    tags=["Testimonials"],
    search_fields=["content"],
    list_fields=["id", "user", "content", "created_at"],
    fetch_links=True,
    permission_classes=[AllowAny]
)

router = APIRouter()
router.include_router(faq_crud.router)
router.include_router(testimonial_crud.router)
