from backbone.generic.views import GenericCrud
from schemas.notes import Note

router = GenericCrud(
    schema=Note,
    prefix="/notes",
    tags=["Notes"]
).router
