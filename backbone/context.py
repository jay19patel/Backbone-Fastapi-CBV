from typing import Any, Type, Optional
from .interface import IDatabaseRepository

# Global Context for Backbone Configuration
# These are set by BackboneConfig usage
DATABASE: Optional[Any] = None
REPOSITORY_CLASS: Optional[Type[IDatabaseRepository]] = None

# Global Registry for components that need startup actions (like indexing)
REGISTERED_COMPONENTS: list = []
