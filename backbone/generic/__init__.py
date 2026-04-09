"""
backbone.generic
~~~~~~~~~~~~~~~~
Generic CRUD views and utilities.
"""

from .views import (
    GenericListView, GenericCreateView, GenericRetrieveView,
    GenericUpdateView, GenericDeleteView, GenericCrudView,
    GenericStatsView, GenericSubResourceView, GenericCustomApiView
)

__all__ = [
    "GenericListView", "GenericCreateView", "GenericRetrieveView",
    "GenericUpdateView", "GenericDeleteView", "GenericCrudView",
    "GenericStatsView", "GenericSubResourceView", "GenericCustomApiView"
]
