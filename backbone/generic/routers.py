from fastapi import APIRouter
from typing import Type, Any

class BackboneRouter:
    """
    A DRF-style router for Backbone FastAPI.
    Registers GenericCrud or BaseGenericView classes and aggregates their APIRouters.
    """
    def __init__(self, prefix: str = "", tags: list = None, **kwargs):
        self.router = APIRouter(prefix=prefix, tags=tags, **kwargs)
        self.registry = []

    def register(self, prefix: str, viewset: Type[Any], basename: str = None, **kwargs):
        """
        Registers a Backbone viewset (like BlogCrud / BlogViewSet).
        """
        # Instantiate the viewset with the provided prefix and any extra kwargs.
        # Ensure that if it has a schema, it's defined on the class or via kwargs.
        
        # Merge prefix properly
        if not prefix.startswith("/"):
            prefix = "/" + prefix
            
        instance = viewset(prefix=prefix, **kwargs)
        
        # Include its router
        if hasattr(instance, "router"):
            self.router.include_router(instance.router)
        self.registry.append(instance)
        
    def get_router(self) -> APIRouter:
        return self.router
