from backbone.generic.views import GenericList, GenericCreate
from backbone.core.permissions import AllowAny
from schemas.content import FAQ, Testimonial, ContactMessage
from fastapi import APIRouter

router = APIRouter(tags=["Content"])

# Register FAQ List - Publicly visible
faq_router = GenericList(
    schema=FAQ,
    prefix="/faqs",
    tags=["FAQ"],
    permission_classes=[AllowAny],
    use_auth=False
)
router.include_router(faq_router.router)

# Register Testimonial List - Publicly visible
testimonial_router = GenericList(
    schema=Testimonial,
    prefix="/testimonials",
    tags=["Testimonial"],
    permission_classes=[AllowAny],
    use_auth=False
)
router.include_router(testimonial_router.router)

# Register ContactMessage Create - Public can send messages
contact_router = GenericCreate(
    schema=ContactMessage,
    prefix="/contact",
    tags=["Contact"],
    permission_classes=[AllowAny],
    use_auth=False
)
router.include_router(contact_router.router, prefix="/content")
