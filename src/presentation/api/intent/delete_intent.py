"""Delete intent detection — thin wrapper.

All detection logic lives in :mod:`src.detection.intent.delete_detector`.
This module is kept so existing imports remain unbroken.
"""

from typing import Optional

from src.detection.intent.delete_detector import detect_delete_intent as _detect


def detect_delete_intent(message: str) -> Optional[str]:
    """Detect delete intent.

    Returns:
        ``"delete"`` for resource deletion,
        ``"item_operation"`` for list-item deletion,
        ``None`` to let file handler or other logic handle it,
        or ``None`` if no delete intent detected.
    """
    result = _detect(message)
    return result.intent if result else None
