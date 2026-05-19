from typing import Any, Optional

from beanie import Document


class ModelAdmin:
    """
    Configuration for how a model appears in the Admin.
    """

    list_display: list[str] = []
    search_fields: list[str] = []
    ordering: str | None = None
    readonly_fields: list[str] = []


class AdminSite:
    """
    Registry for models to be managed via the Backbone Admin.
    """

    _instance: Optional["AdminSite"] = None

    def __init__(self):
        self._registry: dict[str, dict[str, Any]] = {}
        self._page_registry: dict[str, dict[str, Any]] = {}

    @classmethod
    def get_instance(cls) -> "AdminSite":
        if cls._instance is None:
            cls._instance = AdminSite()
        return cls._instance

    def register(
        self,
        model: type[Document],
        admin_class: type[ModelAdmin] = ModelAdmin,
        category: str = "Custom Models",
    ):
        """
        Register a model with the Admin site.
        """
        model_name = model.__name__
        self._registry[model_name] = {
            "model": model,
            "admin": admin_class(),
            "name": model_name,
            "category": category,
        }

    def get_registered_models(self) -> list[dict[str, Any]]:
        """
        Return a list of all registered models.
        """
        return list(self._registry.values())

    def get_model_config(self, model_name: str) -> dict[str, Any] | None:
        """
        Return the configuration for a specific registered model.
        """
        return self._registry.get(model_name)

    def register_page(
        self,
        *,
        name: str,
        path: str,
        methods: list[str],
        description: str = "",
        category: str = "Framework Pages",
    ) -> None:
        self._page_registry[path] = {
            "name": name,
            "path": path,
            "methods": methods,
            "description": description,
            "category": category,
        }

    def get_registered_pages(self) -> list[dict[str, Any]]:
        return list(self._page_registry.values())


# Global singleton
admin_site = AdminSite.get_instance()
