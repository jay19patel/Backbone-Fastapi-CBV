from typing import Callable, List, Dict, Any, Type, Optional
from collections import defaultdict
import asyncio

class Signal:
    """
    A simple signal dispatcher that allows connecting handlers to events.
    """
    def __init__(self, name: str):
        self.name = name
        # Mapping of Model Class -> List of Handlers
        self._handlers: Dict[Type, List[Callable]] = defaultdict(list)

    def connect(self, model_class: Type, handler: Callable):
        """Connect a handler to this signal for a specific model class."""
        if handler not in self._handlers[model_class]:
            self._handlers[model_class].append(handler)

    def disconnect(self, model_class: Type, handler: Callable) -> bool:
        """Disconnect a handler from this signal for a specific model class."""
        handlers = self._handlers.get(model_class, [])
        if handler in handlers:
            handlers.remove(handler)
            return True
        return False

    async def emit(self, instance: Any, model_class: Optional[Type] = None, **kwargs):
        """Emit the signal to all handlers registered for the instance's class."""
        if model_class is None:
            model_class = type(instance)
        handlers = self._handlers.get(model_class, [])
        
        # Also call handlers registered for base classes (if needed)
        # For now, let's keep it simple and just do direct class match
        
        tasks = []
        for handler in handlers:
            if asyncio.iscoroutinefunction(handler):
                tasks.append(handler(instance, **kwargs))
            else:
                handler(instance, **kwargs)
        
        if tasks:
            await asyncio.gather(*tasks)

class SignalManager:
    """
    Manager for global model signals.
    """
    post_create = Signal("post_create")
    post_update = Signal("post_update")
    post_delete = Signal("post_delete")
    on_field_change = Signal("on_field_change")
    on_view = Signal("on_view")

# Global instance for easy access
signals = SignalManager()
