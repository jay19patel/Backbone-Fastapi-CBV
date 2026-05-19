"""
backbone.generic
~~~~~~~~~~~~~~~~
Generic CRUD views and utilities.
"""

from .views import (
    GenericCreateView,
    GenericCrudView,
    GenericCustomApiView,
    GenericDeleteView,
    GenericListView,
    GenericRetrieveView,
    GenericStatsView,
    GenericSubResourceView,
    GenericUpdateView,
)

__all__ = [
    "GenericListView",
    "GenericCreateView",
    "GenericRetrieveView",
    "GenericUpdateView",
    "GenericDeleteView",
    "GenericCrudView",
    "GenericStatsView",
    "GenericSubResourceView",
    "GenericCustomApiView",
]
