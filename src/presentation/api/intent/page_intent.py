"""Page-related intent detection — thin wrapper.

All detection logic lives in :mod:`src.detection.intent.page_detector`.
This module is kept so existing imports remain unbroken.
"""

from typing import Optional

from src.detection.intent.page_detector import detect_page_intent as _detect


def detect_page_intent(message: str) -> Optional[str]:
    """Detect page content query intent.

    Returns ``"page_query"`` if the message is asking about page content,
    or ``None`` if no page intent is detected.
    """
    result = _detect(message)
    return result.intent if result else None
