"""Operation detection sub-package.

Exports intent detectors for all SharePoint operation types.
"""

from src.detection.operations.site_operation_detector import detect_site_operation_intent
from src.detection.operations.page_operation_detector import detect_page_operation_intent
from src.detection.operations.library_operation_detector import detect_library_operation_intent
from src.detection.operations.file_operation_detector import detect_file_operation_intent
from src.detection.operations.list_item_operation_detector import detect_list_item_operation_intent

__all__ = [
    "detect_site_operation_intent",
    "detect_page_operation_intent",
    "detect_library_operation_intent",
    "detect_file_operation_intent",
    "detect_list_item_operation_intent",
]
