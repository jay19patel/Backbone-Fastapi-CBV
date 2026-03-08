from backbone.generic.views import GenericCrud
from backbone.core.permissions import AllowAny
from schemas.content import FAQ, Testimonial, ContactMessage
from fastapi import APIRouter

router = APIRouter(tags=["Content"])

# Register FAQ - CRUD
faq_router = GenericCrud(
    schema=FAQ,
    prefix="/faqs",
    tags=["FAQ"],
    permission_classes=[AllowAny],
    use_auth=False
)
router.include_router(faq_router.router)

# Register Testimonial - CRUD
testimonial_router = GenericCrud(
    schema=Testimonial,
    prefix="/testimonials",
    tags=["Testimonial"],
    permission_classes=[AllowAny],
    use_auth=False
)
router.include_router(testimonial_router.router)

# Register ContactMessage - CRUD
contact_router = GenericCrud(
    schema=ContactMessage,
    prefix="/contact",
    tags=["Contact"],
    permission_classes=[AllowAny],
    use_auth=False
)
router.include_router(contact_router.router, prefix="/content")
