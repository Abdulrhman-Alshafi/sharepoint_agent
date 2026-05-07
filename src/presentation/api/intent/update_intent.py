"""Update intent detection — thin wrapper.

All detection logic lives in :mod:`src.detection.intent.update_detector`.
This module is kept so existing imports remain unbroken.
"""

from typing import Optional

from src.detection.intent.update_detector import detect_update_intent as _detect


def detect_update_intent(message: str) -> Optional[str]:
    """Detect update intent.

    Returns:
        ``"update"`` for schema-level resource updates,
        ``"item_operation"`` for record-level item updates,
        or ``None`` if no update intent detected.
    """
    result = _detect(message)
    return result.intent if result else None
