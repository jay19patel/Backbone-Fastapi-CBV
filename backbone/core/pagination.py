from typing import Any, List, Optional, Dict
from pydantic import BaseModel, ConfigDict

class BasePagination:
    """
    Base class for pagination configurations.
    """
    def paginate_queryset(self, query: Any, request: Any):
        raise NotImplementedError("paginate_queryset() must be implemented.")

    def get_paginated_response(self, data: List[Any], **kwargs):
        raise NotImplementedError("get_paginated_response() must be implemented.")

class PageNumberPagination(BasePagination):
    """
    Pagination based on fixed-size pages, requested by a page number.
    """
    page_size = 10
    page_query_param = "page"
    page_size_query_param = "page_size"
    max_page_size = 100
    
    def get_paginated_response(self, data: List[Any], total: int, page: int, page_size: int) -> Dict[str, Any]:
        return {
            "total": total,
            "count": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 1,
            "results": data
        }

class CursorPagination(BasePagination):
    """
    Cursor based pagination for high-performance and robust sorting. 
    (Underlying query layer configures Mongo ObjectId/timestamp conditions)
    """
    cursor_query_param = "cursor"
    page_size = 10
    ordering = "-created_at"
    
    def get_paginated_response(self, data: List[Any], next_cursor: Optional[str] = None, prev_cursor: Optional[str] = None) -> Dict[str, Any]:
        return {
            "next": next_cursor,
            "previous": prev_cursor,
            "results": data
        }
