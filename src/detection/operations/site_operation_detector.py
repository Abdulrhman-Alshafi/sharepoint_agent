"""Site operation intent detection — scoring-based, pure Python.

Detects when a user message is requesting a site-level operation (create,
delete, update, membership, navigation, theme, etc.).

Layers:
  1 — Multi-word explicit phrases → WEIGHT_EXPLICIT (0.9)
  2 — Single-keyword match        → WEIGHT_KEYWORD  (0.6)
"""

from __future__ import annotations

import logging

from src.detection.base import (
    DetectionResult,
    WEIGHT_EXPLICIT,
    WEIGHT_KEYWORD,
    score_phrases,
    log_detection,
)

logger = logging.getLogger(__name__)

_SITE_EXPLICIT_PHRASES = (
    "create site", "new site", "add site",
    "delete site", "remove site",
    "update site", "site member", "add member", "add owner",
    "site navigation", "recycle bin", "empty recycle bin",
    "site theme", "site permissions", "site storage",
    "site analytics", "restore from recycle bin",
)

_SITE_KEYWORDS = ("sharepoint site", "intranet", "workspace")


def detect_site_operation_intent(text: str) -> DetectionResult:
    """Detect site operation intent.

    Returns:
        ``intent="site_operation"`` with confidence score, or ``intent=None``.
    """
    text_lower = text.lower()
    scores: dict[str, float] = {}
    layer_hit = ""
    matched: list[str] = []

    l1_score, l1_matched = score_phrases(text_lower, _SITE_EXPLICIT_PHRASES, WEIGHT_EXPLICIT)
    if l1_score:
        scores["site_operation"] = l1_score
        layer_hit = "explicit_phrases"
        matched = l1_matched

    if "site_operation" not in scores:
        l2_score, l2_matched = score_phrases(text_lower, _SITE_KEYWORDS, WEIGHT_KEYWORD)
        if l2_score:
            scores["site_operation"] = l2_score
            layer_hit = "keywords"
            matched = l2_matched

    selected = "site_operation" if scores else None
    log_detection(logger, "operations.site", scores, selected)

    if selected:
        return DetectionResult(
            intent=selected,
            score=scores[selected],
            layer=layer_hit,
            matched_phrases=matched,
        )
    return DetectionResult()
