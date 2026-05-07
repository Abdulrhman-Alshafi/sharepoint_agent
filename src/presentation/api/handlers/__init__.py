"""DEPRECATED — Handlers package.

All handlers have been renamed to orchestrators and moved to the
`orchestrators/` package. These re-exports exist solely for backward
compatibility during the transition.
"""

from src.presentation.api.orchestrators.item_orchestrator import handle_item_operations
from src.presentation.api.orchestrators.file_orchestrator import handle_file_operations
from src.presentation.api.orchestrators.site_orchestrator import handle_site_operations
from src.presentation.api.orchestrators.page_orchestrator import handle_page_operations
from src.presentation.api.orchestrators.library_orchestrator import handle_library_operations
from src.presentation.api.orchestrators.permission_orchestrator import handle_permission_operations
from src.presentation.api.orchestrators.enterprise_orchestrator import handle_enterprise_operations
from src.presentation.api.orchestrators.analysis_orchestrator import handle_analysis_operations
from src.presentation.api.orchestrators.update_orchestrator import handle_update_operations
from src.presentation.api.orchestrators.delete_orchestrator import handle_delete_operations

__all__ = [
    "handle_item_operations",
    "handle_file_operations",
    "handle_site_operations",
    "handle_page_operations",
    "handle_library_operations",
    "handle_permission_operations",
    "handle_enterprise_operations",
    "handle_analysis_operations",
    "handle_update_operations",
    "handle_delete_operations",
]
