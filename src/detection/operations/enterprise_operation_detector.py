"""Enterprise operation intent detection — scoring-based, pure Python."""

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

_ENTERPRISE_EXPLICIT_PHRASES = (
    "create content type", "new content type", "add content type",
    "show content types", "list content types",
    "create term set", "new term set", "add term set",
    "term store", "managed metadata",
    "create view", "new view", "add view",
    "show views", "list views",
    "create column", "new column", "add column",
    "custom column", "site column",
    "create folder", "new folder", "add folder",
)

_ENTERPRISE_KEYWORDS = ("content type", "term set", "term store", "managed metadata", "view", "column")


def detect_enterprise_operation_intent(text: str) -> DetectionResult:
    """Detect enterprise/advanced operation intent (content types, term sets, views, etc).

    Returns:
        ``intent="enterprise_operation"`` with confidence score, or ``intent=None``.
    """
    text_lower = text.lower()
    scores: dict[str, float] = {}
    layer_hit = ""
    matched: list[str] = []

    l1_score, l1_matched = score_phrases(text_lower, _ENTERPRISE_EXPLICIT_PHRASES, WEIGHT_EXPLICIT)
    if l1_score:
        scores["enterprise_operation"] = l1_score
        layer_hit = "explicit_phrases"
        matched = l1_matched

    if "enterprise_operation" not in scores:
        l2_score, l2_matched = score_phrases(text_lower, _ENTERPRISE_KEYWORDS, WEIGHT_KEYWORD)
        if l2_score:
            scores["enterprise_operation"] = l2_score
            layer_hit = "keywords"
            matched = l2_matched

    selected = "enterprise_operation" if scores else None
    log_detection(logger, "operations.enterprise", scores, selected)

    if selected:
        return DetectionResult(
            intent=selected,
            score=scores[selected],
            layer=layer_hit,
            matched_phrases=matched,
        )
    return DetectionResult()
