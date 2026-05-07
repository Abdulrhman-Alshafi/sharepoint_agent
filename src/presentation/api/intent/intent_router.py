"""Intent router — thin wrapper.

All scoring logic lives in :mod:`src.detection.intent.router`.
This module is kept so existing imports remain unbroken.
"""

import logging
from typing import Optional

from src.detection.intent.router import route_intent

logger = logging.getLogger(__name__)


def detect_enhanced_intent(message: str) -> Optional[str]:
    """Detect if message matches an enhanced intent.

    Returns the detected intent name or ``None`` if no enhanced intent
    is matched (falls through to AI classifier).

    Possible return values:
        - ``"page_query"``
        - ``"personal_query"``
        - ``"item_operation"``
        - ``"analyze"``
        - ``"update"``
        - ``"delete"``
        - ``"site_operation"``
        - ``"page_operation"``
        - ``"library_operation"``
        - ``"file_operation"``
        - ``"permission_operation"``
        - ``"enterprise_operation"``
        - ``None``
    """
    result = route_intent(message)
    if result:
        logger.info("[intent] Detected: %s for message: %.80s", result, message)
    return result
