from backbone.generic.views import GenericCrud
from schemas.content import FAQ, Testimonial, ContactMessage
from fastapi import APIRouter

router = APIRouter(tags=["Content"])

# Register FAQ CRUD
faq_router = GenericCrud(
    schema=FAQ,
    prefix="/faqs",
    tags=["FAQ"]
)
router.include_router(faq_router.router)

# Register Testimonial CRUD
testimonial_router = GenericCrud(
    schema=Testimonial,
    prefix="/testimonials",
    tags=["Testimonial"]
)
router.include_router(testimonial_router.router)

# Register ContactMessage CRUD
contact_router = GenericCrud(
    schema=ContactMessage,
    prefix="/contact",
    tags=["Contact"]
)
router.include_router(contact_router.router)
