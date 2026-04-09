from typing import List, Type, Dict, Any, Optional
from pydantic import BaseModel
from beanie import Document

class ModelAdmin:
    """
    Configuration for how a model appears in the Admin.
    """
    list_display: List[str] = []
    search_fields: List[str] = []
    ordering: Optional[str] = None
    readonly_fields: List[str] = []

class AdminSite:
    """
    Registry for models to be managed via the Backbone Admin.
    """
    _instance: Optional["AdminSite"] = None

    def __init__(self):
        self._registry: Dict[str, Dict[str, Any]] = {}
        self._page_registry: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def get_instance(cls) -> "AdminSite":
        if cls._instance is None:
            cls._instance = AdminSite()
        return cls._instance

    def register(self, model: Type[Document], admin_class: Type[ModelAdmin] = ModelAdmin, category: str = "Custom Models"):
        """
        Register a model with the Admin site.
        """
        model_name = model.__name__
        self._registry[model_name] = {
            "model": model,
            "admin": admin_class(),
            "name": model_name,
            "category": category
        }

    def get_registered_models(self) -> List[Dict[str, Any]]:
        """
        Return a list of all registered models.
        """
        return list(self._registry.values())

    def get_model_config(self, model_name: str) -> Optional[Dict[str, Any]]:
        """
        Return the configuration for a specific registered model.
        """
        return self._registry.get(model_name)

    def register_page(
        self,
        *,
        name: str,
        path: str,
        methods: List[str],
        description: str = "",
        category: str = "Framework Pages",
    ) -> None:
        self._page_registry[name] = {
            "name": name,
            "path": path,
            "methods": methods,
            "description": description,
            "category": category,
        }

    def get_registered_pages(self) -> List[Dict[str, Any]]:
        return list(self._page_registry.values())

# Global singleton
admin_site = AdminSite.get_instance()
