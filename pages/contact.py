from __future__ import annotations

from typing import Any, Dict, List

from bson import ObjectId
from fastapi import APIRouter, Request

from backbone import AllowAny, GenericFormView, GenericTemplateView, db_store
from backbone.core.repository import BeanieRepository
from schemas.content import Contact


def _contact_search_query(raw_query: str) -> Dict[str, Any]:
    query = (raw_query or "").strip()
    if not query:
        return {"is_deleted": False}

    clauses: List[Dict[str, Any]] = [
        {"name": {"$regex": query, "$options": "i"}},
        {"email": {"$regex": query, "$options": "i"}},
        {"subject": {"$regex": query, "$options": "i"}},
        {"message": {"$regex": query, "$options": "i"}},
    ]
    if ObjectId.is_valid(query):
        clauses.insert(0, {"_id": ObjectId(query)})

    return {
        "$and": [
            {"is_deleted": False},
            {"$or": clauses},
        ]
    }


class ContactPage(GenericFormView):
    template_name = "pages/contact_form.html"
    permission_classes = [AllowAny]
    page_name = "Contact"
    page_description = "Simple contact form page powered by Backbone templates."
    admin_category = "Application Pages"

    async def get_context_data(self, request: Request, user: Any = None, **kwargs: Any) -> Dict[str, Any]:
        return {
            "submitted": False,
            "success": False,
            "error": "",
            "form_values": {
                "name": "",
                "email": "",
                "subject": "",
                "message": "",
            },
        }

    async def handle_submit(self, request: Request, form_data: Dict[str, Any], user: Any = None) -> Dict[str, Any]:
        payload = {
            "name": str(form_data.get("name", "")).strip(),
            "email": str(form_data.get("email", "")).strip(),
            "subject": str(form_data.get("subject", "")).strip(),
            "message": str(form_data.get("message", "")).strip(),
        }

        if not all(payload.values()):
            return {
                "submitted": True,
                "success": False,
                "error": "All fields are required.",
                "form_values": payload,
            }

        contact = Contact(**payload)
        await contact.insert()

        return {
            "submitted": True,
            "success": True,
            "error": "",
            "message_text": "Your message has been submitted successfully.",
            "form_values": {
                "name": "",
                "email": "",
                "subject": "",
                "message": "",
            },
        }


class ContactListingPage(GenericTemplateView):
    template_name = "pages/contact_list.html"
    permission_classes = [AllowAny]
    page_name = "Contact Listing"
    page_description = "Review submitted contact requests in a simple responsive table."
    admin_category = "Application Pages"
    page_size = 12

    @staticmethod
    def _get_page_number(request: Request) -> int:
        raw_page = str(request.query_params.get("page", "1") or "1").strip()
        try:
            return max(int(raw_page), 1)
        except ValueError:
            return 1

    async def get_context_data(self, request: Request, user: Any = None, **kwargs: Any) -> Dict[str, Any]:
        query_text = request.query_params.get("q", "").strip()
        page = self._get_page_number(request)
        mongo_query = _contact_search_query(query_text)

        total = await Contact.find(mongo_query).count()
        skip = (page - 1) * self.page_size
        records = (
            await Contact.find(mongo_query)
            .sort([("created_at", -1)])
            .skip(skip)
            .limit(self.page_size)
            .to_list()
        )

        repo = BeanieRepository()
        repo.initialize(Contact)
        contacts = repo.serialize_document(records)
        total_pages = max((total + self.page_size - 1) // self.page_size, 1)

        return {
            "contacts": contacts,
            "query": query_text,
            "page": page,
            "page_size": self.page_size,
            "total": total,
            "total_pages": total_pages,
            "has_previous": page > 1,
            "has_next": page < total_pages,
            "previous_page": page - 1,
            "next_page": page + 1,
        }


class AboutPage(GenericTemplateView):
    template_name = "pages/about_blogermenia.html"
    permission_classes = [AllowAny]
    page_name = "About Blogermenia"
    page_description = "Overview of Blogermenia and the Backbone-powered backend system."
    admin_category = "Application Pages"

    async def get_context_data(self, request: Request, user: Any = None, **kwargs: Any) -> Dict[str, Any]:
        return {
            "stack": [
                "Next.js 15 frontend",
                "FastAPI backend",
                "MongoDB with Beanie ODM",
                "Redis for cache and background jobs",
                "Backbone framework for CRUD, admin, auth, and pages",
            ],
            "capabilities": [
                "Blog, playlist, media, and content APIs",
                "Admin dashboard with model management",
                "Generic class-based API views",
                "Template and form pages under /pages",
                "Authentication, sessions, and password reset flow",
            ],
            "principles": [
                "Keep app code separated from Backbone core",
                "Favor reusable generic layers over repeated routers",
                "Keep UI and admin usable on mobile as well as desktop",
            ],
        }


class StoreTestPage(GenericFormView):
    template_name = "pages/store_test.html"
    permission_classes = [AllowAny]
    page_name = "Backbone Store Test"
    page_description = "Set and read Backbone singleton key/value data using backbone.db_store.get."
    admin_category = "Application Pages"

    @staticmethod
    def _resolve_key(request: Request) -> str:
        key = str(request.query_params.get("key", "homepage_banner")).strip()
        return key or "homepage_banner"

    async def get_context_data(self, request: Request, user: Any = None, **kwargs: Any) -> Dict[str, Any]:
        key = self._resolve_key(request)
        value = await db_store.get(key, "No value set yet.")
        return {
            "submitted": False,
            "success": False,
            "error": "",
            "active_key": key,
            "active_value": value,
            "form_values": {"key": key, "value": ""},
            "all_values": await db_store.all(),
        }

    async def handle_submit(self, request: Request, form_data: Dict[str, Any], user: Any = None) -> Dict[str, Any]:
        key = str(form_data.get("key", "")).strip()
        value = str(form_data.get("value", "")).strip()

        if not key:
            return {
                "submitted": True,
                "success": False,
                "error": "Key is required.",
                "active_key": "homepage_banner",
                "active_value": await db_store.get("homepage_banner", "No value set yet."),
                "form_values": {"key": "", "value": value},
                "all_values": await db_store.all(),
            }

        await db_store.set(key, value)
        fetched_value = await db_store.get(key)
        return {
            "submitted": True,
            "success": True,
            "error": "",
            "message_text": f"Saved and fetched via backbone.db_store.get('{key}')",
            "active_key": key,
            "active_value": fetched_value,
            "form_values": {"key": key, "value": ""},
            "all_values": await db_store.all(),
        }


router = APIRouter()
router.include_router(
    ContactPage.as_router(
        "/contact",
        tags=["Pages"],
        name="contact_page",
        admin_path="/pages/contact",
    )
)
router.include_router(
    ContactListingPage.as_router(
        "/contact/submissions",
        tags=["Pages"],
        name="contact_listing_page",
        admin_path="/pages/contact/submissions",
    )
)
router.include_router(
    AboutPage.as_router(
        "/about",
        tags=["Pages"],
        name="about_page",
        admin_path="/pages/about",
    )
)
router.include_router(
    StoreTestPage.as_router(
        "/store-test",
        tags=["Pages"],
        name="store_test_page",
        admin_path="/pages/store-test",
    )
)
