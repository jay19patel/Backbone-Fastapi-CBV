from fastapi import FastAPI
from backbone import GenericCrud, GenericList, GenericRetrieve, AuthRouter, IsOwner, db
from schema import BlogSchema

app = FastAPI(title="Modular backbone Framework")

# 1. Register Auth (JWT + Argon2)
app.include_router(AuthRouter().router)

# 2. Register Blog View using GenericCrud (Everything in one)
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

# 3. Example of a Read-Only endpoint (Modular Usage)
# Only List and Retrieve are available for this prefix.
readonly_blogs = GenericList(
    db=db,
    schema=BlogSchema,
    prefix="/public-blogs",
    tags=["Public"],
    list_fields=["title", "created_at"],
    use_auth=False # Allow access without token
)
# We can also add specifically Retrieve to make it List/Detail only.
# readonly_detail = GenericRetrieve(db=db, schema=BlogSchema, prefix="/public-blogs", use_auth=False)
# app.include_router(readonly_detail.router) # Registers /{pk}/

app.include_router(readonly_blogs.router)

@app.on_event("startup")
async def startup():
    await blog_view.sync_indexes()
    print("Backbone system v6 (Modular Mixins) online.")

@app.get("/")
def home():
    return {
        "status": "online", 
        "version": "v6 (Modular Mixins)",
        "docs": "/docs"
    }
