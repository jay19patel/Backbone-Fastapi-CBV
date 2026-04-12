"""
backbone.generic.views
~~~~~~~~~~~~~~~~~~~~~~
Modern router-based generic views for Backbone.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, FileSystemLoader

from ..core.mixins import (
    CreateMixin, DeleteMixin, ListMixin, RetrieveMixin, UpdateMixin, ViewContext
)
from ..core.permissions import AllowAny, PermissionDependency
from .utils import _parse_sort, _register_actions, _extract_create_data, _extract_update_data

logger = logging.getLogger("backbone.views")
APP_TEMPLATE_ROOT = Path(__file__).resolve().parents[2] / "templates"
FRAMEWORK_TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "templates"


def build_page_templates() -> Jinja2Templates:
    """Use app templates first, then fall back to Backbone templates."""
    environment = default_page_templates.env if "default_page_templates" in globals() else None
    loader = ChoiceLoader(
        [
            FileSystemLoader(str(APP_TEMPLATE_ROOT)),
            FileSystemLoader(str(FRAMEWORK_TEMPLATE_ROOT)),
        ]
    )
    if environment is not None:
        environment.loader = loader
        return default_page_templates
    templates = Jinja2Templates(directory=str(APP_TEMPLATE_ROOT))
    templates.env.loader = loader
    return templates


default_page_templates = build_page_templates()

class GenericListView(ListMixin):
    @classmethod
    def as_router(cls, prefix: str, tags: Optional[List[str]] = None, **kwargs: Any) -> APIRouter:
        view = cls()
        router = APIRouter(prefix=prefix, tags=tags or [prefix.strip("/")], **kwargs)
        cls._register_list_route(router, view, view.get_permission_dependency())
        _register_actions(view, router)
        return router

    @staticmethod
    def _register_list_route(router: APIRouter, view: ListMixin, perm_dep: Callable) -> None:
        @router.get("/", summary=f"List {view.schema.__name__}")
        async def list_view(request: Request, user: Any = Depends(perm_dep), page: int = Query(1, ge=1), 
                            page_size: int = Query(10, ge=1, le=100), search: Optional[str] = Query(None),
                            sort: Optional[str] = Query(None)) -> dict:
            await view.resolve_context(request)
            query = await view.get_queryset(request, user)
            query = await view.filter_queryset(query, request)
            results, total = await view.perform_list(query, page=page, page_size=page_size, sort=_parse_sort(sort))
            return await view.format_list(results, total, page, page_size)

class GenericCreateView(CreateMixin):
    @classmethod
    def as_router(cls, prefix: str, tags: Optional[List[str]] = None, **kwargs: Any) -> APIRouter:
        view = cls()
        router = APIRouter(prefix=prefix, tags=tags or [prefix.strip("/")], **kwargs)
        cls._register_create_route(router, view, view.get_permission_dependency())
        _register_actions(view, router)
        return router

    @staticmethod
    def _register_create_route(router: APIRouter, view: CreateMixin, perm_dep: Callable) -> None:
        async def create_view(request: Request, data: Any = Body(...), user: Any = Depends(perm_dep)) -> Any:
            await view.resolve_context(request)
            val_data = await _extract_create_data(view, data)
            val_data.update({"created_at": datetime.now(timezone.utc), "is_deleted": False})
            if user: val_data["created_by"] = str(user.id)
            val_data = await view.before_create(val_data, user)
            inst = await view.perform_create(val_data)
            inst = await view.after_create(inst, user)
            
            # REFETCH: If fetch_links is enabled, re-fetch the document with all populated links
            # before returning it to the client. This ensures immediate data consistency.
            if view.fetch_links:
                pk = str(getattr(inst, "id", None) or inst.id)
                re_fetched = await view.perform_retrieve(pk, request, user)
                if re_fetched: inst = re_fetched

            await view._invalidate_cache()
            return view._serialize_response(inst)
        create_view.__annotations__["data"] = view.create_schema or view.schema
        router.add_api_route("/", create_view, methods=["POST"], response_model=view.response_schema or view.schema, status_code=201)

class GenericRetrieveView(RetrieveMixin):
    @classmethod
    def as_router(cls, prefix: str, tags: Optional[List[str]] = None, **kwargs: Any) -> APIRouter:
        view = cls()
        router = APIRouter(prefix=prefix, tags=tags or [prefix.strip("/")], **kwargs)
        cls._register_retrieve_route(router, view, view.get_permission_dependency())
        _register_actions(view, router)
        return router

    @staticmethod
    def _register_retrieve_route(router: APIRouter, view: RetrieveMixin, perm_dep: Callable) -> None:
        @router.get("/{pk}", summary=f"Retrieve {view.schema.__name__}")
        async def retrieve_view(request: Request, pk: str, user: Any = Depends(perm_dep)) -> Any:
            await view.resolve_context(request)
            await view.before_retrieve(pk, request, user)
            if view._cache and view._cache.enabled:
                cache_key = view._build_cache_key(
                    "detail",
                    {
                        "pk": pk,
                        "lookup_field": view.lookup_field,
                        "populate_fields": view._get_populate_fields(),
                        "user_id": str(user.id) if user else None,
                    },
                )
                inst = await view._cache.get_or_set(
                    cache_key,
                    view.cache_ttl,
                    view.perform_retrieve,
                    pk,
                    request,
                    user,
                )
            else:
                inst = await view.perform_retrieve(pk, request, user)
            return await view.after_retrieve(inst, request, user)

class GenericUpdateView(UpdateMixin):
    @classmethod
    def as_router(cls, prefix: str, tags: Optional[List[str]] = None, **kwargs: Any) -> APIRouter:
        view = cls()
        router = APIRouter(prefix=prefix, tags=tags or [prefix.strip("/")], **kwargs)
        cls._register_update_route(router, view, view.get_permission_dependency())
        _register_actions(view, router)
        return router

    @staticmethod
    def _register_update_route(router: APIRouter, view: UpdateMixin, perm_dep: Callable) -> None:
        async def update_view(request: Request, pk: str, data: Any = Body(...), user: Any = Depends(perm_dep)) -> Any:
            await view.resolve_context(request)
            inst = await view.get_object(pk, request, user)
            upd_data = await _extract_update_data(view, data)
            upd_data["updated_at"] = datetime.now(timezone.utc)
            if user: upd_data["updated_by"] = str(user.id)
            upd_data = await view.before_update(inst, upd_data, user)
            result = await view.perform_update(inst, upd_data)
            result = await view.after_update(result, user)
            
            # REFETCH: If populate_links_on_save is enabled, re-fetch with links
            if view.populate_links_on_save:
                pk = str(getattr(result, "id", None) or result.id)
                re_fetched = await view.perform_retrieve(pk, request, user)
                if re_fetched: result = re_fetched

            await view._invalidate_cache()
            return view._serialize_response(result)
        update_view.__annotations__["data"] = view.update_schema or Dict[str, Any]
        router.add_api_route("/{pk}", update_view, methods=["PATCH"], response_model=view.response_schema or view.schema)

class GenericDeleteView(DeleteMixin):
    @classmethod
    def as_router(cls, prefix: str, tags: Optional[List[str]] = None, **kwargs: Any) -> APIRouter:
        view = cls()
        router = APIRouter(prefix=prefix, tags=tags or [prefix.strip("/")], **kwargs)
        cls._register_delete_route(router, view, view.get_permission_dependency())
        _register_actions(view, router)
        return router

    @staticmethod
    def _register_delete_route(router: APIRouter, view: DeleteMixin, perm_dep: Callable) -> None:
        @router.delete("/{pk}", status_code=204, summary=f"Delete {view.schema.__name__}")
        async def delete_view(request: Request, pk: str, user: Any = Depends(perm_dep)) -> None:
            await view.resolve_context(request)
            inst = await view.get_object(pk, request, user)
            if await view.before_delete(inst, user):
                await view.perform_delete(inst)
                await view.after_delete(inst, user)
                await view._invalidate_cache()

class GenericCrudView(ListMixin, CreateMixin, RetrieveMixin, UpdateMixin, DeleteMixin):
    @classmethod
    def as_router(cls, prefix: str, tags: Optional[List[str]] = None, **kwargs: Any) -> APIRouter:
        view, router = cls(), APIRouter(prefix=prefix, tags=tags or [prefix.strip("/")], **kwargs)
        pdep = view.get_permission_dependency()
        GenericListView._register_list_route(router, view, pdep)
        GenericCreateView._register_create_route(router, view, pdep)
        GenericRetrieveView._register_retrieve_route(router, view, pdep)
        GenericUpdateView._register_update_route(router, view, pdep)
        GenericDeleteView._register_delete_route(router, view, pdep)
        _register_actions(view, router)
        return router

class GenericStatsView(ViewContext):
    stats_config: List[Dict[str, Any]] = []
    @classmethod
    def as_router(cls, prefix: str, tags: Optional[List[str]] = None, **kwargs: Any) -> APIRouter:
        view = cls()
        router = APIRouter(prefix=prefix, tags=tags or [prefix.strip("/")], **kwargs)
        @router.get("/", summary="Get aggregated statistics")
        async def stats_view(request: Request, user: Any = Depends(view.get_permission_dependency())) -> dict:
            await view.resolve_context(request)
            from ..core.repository import BeanieRepository
            res = {}
            for config in view.stats_config:
                model, stype, fltr, name = config["model"], config.get("type", "count"), config.get("filters", {}), config["name"]
                repo = BeanieRepository(view._repository.db if view._repository else None)
                repo.initialize(model)
                if stype == "count": res[name] = await repo.count(fltr)
                elif stype == "sum":
                    field = config.get("field", "")
                    agg = await model.get_pymongo_collection().aggregate([{"$match": fltr}, {"$group": {"_id": None, "total": {"$sum": f"${field}"}}}]).to_list(1)
                    res[name] = (agg[0].get("total") or 0) if agg else 0
            return res
        return router

class GenericSubResourceView(ViewContext):
    array_field: str = ""
    target_id_param: str = "id"
    @classmethod
    def as_router(cls, prefix: str, tags: Optional[List[str]] = None, **kwargs: Any) -> APIRouter:
        view = cls()
        router = APIRouter(prefix=prefix, tags=tags or [prefix.strip("/")], **kwargs)
        pdep = view.get_permission_dependency()
        @router.post("/{pk}/" + view.array_field + "/", summary=f"Add to {view.array_field}")
        async def add_item(request: Request, pk: str, data: Dict[str, Any] = Body(...), user: Any = Depends(pdep)) -> dict:
            await view.resolve_context(request)
            from beanie import PydanticObjectId
            inst = await view.get_object(pk, request, user)
            tid = data.get(view.target_id_param)
            await view._repository.update({"_id": PydanticObjectId(inst.get("id") or inst.get("_id"))}, {"$addToSet": {view.array_field: PydanticObjectId(tid)}})
            await view._invalidate_cache()
            return {"status": "success"}
        @router.delete("/{pk}/" + view.array_field + "/{target_id}/", summary=f"Remove from {view.array_field}")
        async def remove_item(request: Request, pk: str, target_id: str, user: Any = Depends(pdep)) -> dict:
            await view.resolve_context(request)
            from beanie import PydanticObjectId
            inst = await view.get_object(pk, request, user)
            await view._repository.update({"_id": PydanticObjectId(inst.get("id") or inst.get("_id"))}, {"$pull": {view.array_field: PydanticObjectId(target_id)}})
            await view._invalidate_cache()
            return {"status": "success"}
        return router

class GenericCustomApiView(ViewContext):
    endpoint: str = ""
    @classmethod
    def as_router(cls, prefix: str, tags: Optional[List[str]] = None, **kwargs: Any) -> APIRouter:
        view = cls()
        router = APIRouter(prefix=prefix, tags=tags or [prefix.strip("/")], **kwargs)
        pdep = view.get_permission_dependency()
        if cls.get != GenericCustomApiView.get:
            @router.get(view.endpoint)
            async def custom_get(request: Request, user: Any = Depends(pdep)) -> Any:
                await view.resolve_context(request)
                return await view.get(request, user)
        if cls.post != GenericCustomApiView.post:
            @router.post(view.endpoint)
            async def custom_post(request: Request, data: Dict[str, Any] = Body(...), user: Any = Depends(pdep)) -> Any:
                await view.resolve_context(request)
                return await view.post(request, data, user)
        return router
    async def get(self, *args, **kwargs): raise NotImplementedError()
    async def post(self, *args, **kwargs): raise NotImplementedError()


class GenericTemplateView:
    template_name: str = ""
    template_engine: Jinja2Templates = default_page_templates
    permission_classes: List[Any] = [AllowAny]
    page_name: str = "Template Page"
    page_description: str = ""
    admin_category: str = "Framework Pages"
    include_in_admin: bool = True

    def get_permission_dependency(self) -> Callable:
        return PermissionDependency(self.permission_classes)

    def get_template_name(self) -> str:
        if not self.template_name:
            raise ValueError("template_name must be defined for GenericTemplateView subclasses.")
        return self.template_name

    def normalize_context(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self.normalize_context(val) for key, val in value.items()}
        if isinstance(value, list):
            return [self.normalize_context(item) for item in value]
        if hasattr(value, "model_dump"):
            return self.normalize_context(value.model_dump(by_alias=True))
        return value

    async def get_context_data(self, request: Request, user: Any = None, **kwargs: Any) -> Dict[str, Any]:
        return {}

    async def render(self, request: Request, context: Dict[str, Any], status_code: int = 200) -> HTMLResponse:
        full_context = {
            "request": request,
            "page_name": self.page_name,
            "page_description": self.page_description,
            "current_user": context.get("current_user"),
            **self.normalize_context(context),
        }
        return self.template_engine.TemplateResponse(self.get_template_name(), full_context, status_code=status_code)

    @classmethod
    def as_router(cls, prefix: str, tags: Optional[List[str]] = None, **kwargs: Any) -> APIRouter:
        view = cls()
        route_name = kwargs.pop("name", cls.__name__.lower())
        admin_path = kwargs.pop("admin_path", prefix)
        router = APIRouter(prefix=prefix, tags=tags or [prefix.strip("/")], **kwargs)
        perm_dep = view.get_permission_dependency()

        @router.get("/", response_class=HTMLResponse, name=route_name)
        async def page_view(request: Request, user: Any = Depends(perm_dep)) -> HTMLResponse:
            context = await view.get_context_data(request, user=user)
            context["current_user"] = user
            return await view.render(request, context)

        if view.include_in_admin:
            from ..admin.site import admin_site

            admin_site.register_page(
                name=view.page_name,
                path=admin_path,
                methods=["GET"],
                description=view.page_description,
                category=view.admin_category,
            )

        return router


class GenericFormView(GenericTemplateView):
    success_redirect_url: Optional[str] = None

    async def post_context_data(self, request: Request, form_data: Dict[str, Any], user: Any = None) -> Dict[str, Any]:
        return {}

    async def handle_submit(self, request: Request, form_data: Dict[str, Any], user: Any = None) -> Dict[str, Any]:
        return await self.post_context_data(request, form_data, user=user)

    @staticmethod
    def _form_to_dict(form_data: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        for key in form_data.keys():
            values = form_data.getlist(key)
            payload[key] = values if len(values) > 1 else values[0]
        return payload

    @classmethod
    def as_router(cls, prefix: str, tags: Optional[List[str]] = None, **kwargs: Any) -> APIRouter:
        view = cls()
        route_name = kwargs.pop("name", cls.__name__.lower())
        admin_path = kwargs.pop("admin_path", prefix)
        router = APIRouter(prefix=prefix, tags=tags or [prefix.strip("/")], **kwargs)
        perm_dep = view.get_permission_dependency()

        @router.get("/", response_class=HTMLResponse, name=route_name)
        async def page_view(request: Request, user: Any = Depends(perm_dep)) -> HTMLResponse:
            context = await view.get_context_data(request, user=user)
            context["current_user"] = user
            return await view.render(request, context)

        @router.post("/", response_class=HTMLResponse)
        async def form_submit(request: Request, user: Any = Depends(perm_dep)) -> HTMLResponse:
            raw_form = await request.form()
            payload = view._form_to_dict(raw_form)
            result = await view.handle_submit(request, payload, user=user)
            if isinstance(result, RedirectResponse):
                return result
            if view.success_redirect_url and result.get("success"):
                return RedirectResponse(url=view.success_redirect_url, status_code=303)

            base_context = await view.get_context_data(request, user=user)
            base_context.update(result)
            base_context["current_user"] = user
            return await view.render(request, base_context)

        if view.include_in_admin:
            from ..admin.site import admin_site

            admin_site.register_page(
                name=view.page_name,
                path=admin_path,
                methods=["GET", "POST"],
                description=view.page_description,
                category=view.admin_category,
            )

        return router
