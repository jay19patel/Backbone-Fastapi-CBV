from fastapi import APIRouter
from backbone import GenericCrud, AllowAny
from backbone.core.models import User

user_crud = GenericCrud(
    schema=User,
    prefix="/user",
    tags=["Users"],
    search_fields=["full_name", "email", "headline", "bio"],
    list_fields=["id", "full_name", "email", "headline", "profile_image"],
    permission_classes=[AllowAny]
)

router = user_crud.router

# Top authors logic can be added later as a custom route
@router.get("/top-authors/", tags=["Users"])
async def get_top_authors():
    # Placeholder for top authors logic
    # In Beanie, we can aggregate over blogs
    return {"message": "Top authors will be implemented here"}
