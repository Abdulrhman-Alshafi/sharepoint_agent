"""Backwards-compatible shim — list item operations use cases.

The original monolith has been split into three focused use cases:

    ListItemCRUDUseCase   — basic CRUD + validated variants
                            (list_item_crud_use_case.py)
    ListItemBatchUseCase  — batch create/update + advanced OData queries
                            (list_item_batch_use_case.py)
    ListItemViewsUseCase  — item attachments + custom list views
                            (list_item_views_use_case.py)

``ListItemOperationsUseCase`` is kept here as a composite class that inherits
all three for uninterrupted backwards compatibility.
"""

from src.application.use_cases.list_item_crud_use_case import ListItemCRUDUseCase
from src.application.use_cases.list_item_batch_use_case import ListItemBatchUseCase
from src.application.use_cases.list_item_views_use_case import ListItemViewsUseCase
from typing import Any, Optional
from src.domain.repositories import IListRepository


class ListItemOperationsUseCase(
    ListItemCRUDUseCase,
    ListItemBatchUseCase,
    ListItemViewsUseCase,
):
    """Composite use case — all list-item operations in one class.

    Prefer the narrower classes for new code:
      - ``ListItemCRUDUseCase``  for create/read/update/delete.
      - ``ListItemBatchUseCase`` for batch operations and advanced queries.
      - ``ListItemViewsUseCase`` for attachments and views.
    """

    def __init__(self, repository: IListRepository, permission_repository: Optional[Any] = None):
        # All three parents share the same ``repository`` attribute — one call
        # to the first parent's __init__ is sufficient under CPython MRO.
        ListItemCRUDUseCase.__init__(self, repository, permission_repository=permission_repository)
        self._crud = self  # ListItemBatchUseCase uses self._crud internally


__all__ = [
    "ListItemOperationsUseCase",
    "ListItemCRUDUseCase",
    "ListItemBatchUseCase",
    "ListItemViewsUseCase",
]
