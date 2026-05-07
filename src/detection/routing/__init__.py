"""Routing detection sub-package.

Exports resource-type router and webpart router.
"""

from src.detection.routing.resource_type_router import route_resource_type
from src.detection.routing.webpart_router import route_webpart
from src.detection.routing.page_content_router import detect_page_content_upgrade

__all__ = ["route_resource_type", "route_webpart", "detect_page_content_upgrade"]
