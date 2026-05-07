"""Location hint detection — scoring-based, pure Python.

Migrated from ``is_location_hint()`` in
``src/presentation/api/services/clarification_service.py``.

Layers:
  1 — Location keyword present (explicit → 0.9)
  2 — Short message (≤ 10 words) with at least one proper noun (contextual → 0.3)
"""

from __future__ import annotations

import logging

from src.detection.base import (
    DetectionResult,
    WEIGHT_EXPLICIT,
    WEIGHT_CONTEXTUAL,
    score_phrases,
    log_detection,
)

logger = logging.getLogger(__name__)

_LOCATION_PHRASES = (
    "site", "page", "portal", "intranet", "sharepoint",
    "it is on", "it's on", "try the", "check the", "look at",
    "in the", "on the", "from the", "under the",
)


def detect_location_hint(text: str) -> DetectionResult:
    """Detect whether *text* is a location hint.

    Returns:
        ``DetectionResult(intent="location_hint", ...)`` or empty result.
    """
    text_lower = text.lower().strip()
    scores: dict[str, float] = {}
    layer_hit = ""
    matched: list[str] = []

    # Layer 1 — explicit location keyword
    l1_score, l1_matched = score_phrases(text_lower, _LOCATION_PHRASES, WEIGHT_EXPLICIT)
    if l1_score:
        scores["location_hint"] = l1_score
        layer_hit = "location_phrases"
        matched = l1_matched

    if "location_hint" not in scores:
        # Layer 2 — short message with a capitalised proper noun
        words = text.split()
        has_proper = any(len(w) > 2 and w[0].isupper() for w in words)
        if len(words) <= 10 and has_proper:
            scores["location_hint"] = WEIGHT_CONTEXTUAL
            layer_hit = "short_proper_noun"
            matched = [w for w in words if len(w) > 2 and w[0].isupper()][:3]

    selected = "location_hint" if scores else None
    log_detection(logger, "matching.location_hint", scores, selected)

    if selected:
        return DetectionResult(
            intent=selected,
            score=scores[selected],
            layer=layer_hit,
            matched_phrases=matched,
        )
    return DetectionResult()
