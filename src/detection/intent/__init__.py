"""Intent detection sub-package.

Exports the central router and all individual detectors so callers
can import from a single location:

    from src.detection.intent import route_intent
    from src.detection.intent import detect_page_intent, detect_item_intent
"""

from src.detection.intent.page_detector import detect_page_intent
from src.detection.intent.item_detector import detect_item_intent
from src.detection.intent.update_detector import detect_update_intent
from src.detection.intent.delete_detector import detect_delete_intent
from src.detection.intent.analyze_detector import detect_analyze_intent
from src.detection.intent.router import route_intent

__all__ = [
    "detect_page_intent",
    "detect_item_intent",
    "detect_update_intent",
    "detect_delete_intent",
    "detect_analyze_intent",
    "route_intent",
]
