from fastapi import FastAPI
from backbone import GenericCrud, AuthRouter, IsOwner, db
from schema import BlogSchema

app = FastAPI(title="Optimized backbone Framework")

# 1. Register Auth (JWT + Argon2)
app.include_router(AuthRouter().router)

# 2. Register Blog View using GenericCrud (Full CRUD)
# GenericCrud inherits listing functionality from GenericList.
blog_view = GenericCrud(
    db=db,
    schema=BlogSchema,
    prefix="/blogs",
    tags=["Blogs"],
    list_fields=["title", "author_id"],
    filter_fields=["tags"],
    permission_classes=[IsOwner]
)
app.include_router(blog_view.router)

@app.on_event("startup")
async def startup():
    await blog_view.sync_indexes()
    print("Backbone system v5 (Separated Crud/List) online.")

@app.get("/")
def home():
    return {
        "status": "online", 
        "version": "v5 (GenericCrud & GenericList)",
        "docs": "/docs"
    }
