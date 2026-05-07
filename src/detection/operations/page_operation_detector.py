"""Page operation intent detection — scoring-based, pure Python."""

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

_PAGE_EXPLICIT_PHRASES = (
    "create page", "new page", "add page",
    "publish page", "unpublish page",
    "show page", "get page", "view page",
    "list pages", "show all pages", "show me pages",
    "copy page", "duplicate page",
    "delete page", "remove page",
    "promote as news", "promote page", "news article",
)

_PAGE_KEYWORDS = ("page",)


def detect_page_operation_intent(text: str) -> DetectionResult:
    """Detect page operation intent.

    Returns:
        ``intent="page_operation"`` with confidence score, or ``intent=None``.
    """
    text_lower = text.lower()
    scores: dict[str, float] = {}
    layer_hit = ""
    matched: list[str] = []

    l1_score, l1_matched = score_phrases(text_lower, _PAGE_EXPLICIT_PHRASES, WEIGHT_EXPLICIT)
    if l1_score:
        scores["page_operation"] = l1_score
        layer_hit = "explicit_phrases"
        matched = l1_matched

    if "page_operation" not in scores:
        l2_score, l2_matched = score_phrases(text_lower, _PAGE_KEYWORDS, WEIGHT_KEYWORD)
        if l2_score:
            scores["page_operation"] = l2_score
            layer_hit = "keywords"
            matched = l2_matched

    selected = "page_operation" if scores else None
    log_detection(logger, "operations.page", scores, selected)

    if selected:
        return DetectionResult(
            intent=selected,
            score=scores[selected],
            layer=layer_hit,
            matched_phrases=matched,
        )
    return DetectionResult()
