"""Item-operation and personal-query intent detection — thin wrapper.

All detection logic lives in :mod:`src.detection.intent.item_detector`.
This module is kept so existing imports remain unbroken.
"""

from typing import Optional

from src.detection.intent.item_detector import detect_item_intent as _detect


def detect_item_intent(message: str) -> Optional[str]:
    """Detect item operation or personal query intent.

    Returns:
        ``"personal_query"`` for personal data queries,
        ``"item_operation"`` for item CRUD,
        or ``None`` if no item intent detected.
    """
    result = _detect(message)
    return result.intent if result else None
