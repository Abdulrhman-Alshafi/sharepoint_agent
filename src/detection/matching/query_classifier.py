"""Query type classification — scoring-based, pure Python.

Classifies whether a user query is a COUNT query, META query, or a generic
data query. Migrated from ``QueryAnalyzer.COUNT_KEYWORDS`` and
``QueryAnalyzer.META_KEYWORDS`` in
``src/infrastructure/external_services/query_intelligence.py``.
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

_COUNT_PHRASES = (
    "how many", "count", "number of", "total",
)

_META_PHRASES = (
    "what lists", "show lists", "all lists",
    "what libraries", "show libraries", "all libraries",
    "what pages", "show pages",
)


def classify_query_type(text: str) -> DetectionResult:
    """Classify query as ``count``, ``meta``, or no match.

    Returns:
        ``DetectionResult`` with ``intent="count"`` or ``intent="meta"``,
        or an empty result for generic data queries.
    """
    text_lower = text.lower()
    scores: dict[str, float] = {}
    layer_hit = ""
    matched: list[str] = []

    count_score, count_matched = score_phrases(text_lower, _COUNT_PHRASES, WEIGHT_EXPLICIT)
    if count_score:
        scores["count"] = count_score

    meta_score, meta_matched = score_phrases(text_lower, _META_PHRASES, WEIGHT_KEYWORD)
    if meta_score:
        scores["meta"] = meta_score

    if not scores:
        log_detection(logger, "matching.query", {}, None)
        return DetectionResult()

    selected = max(scores, key=scores.get)
    if selected == "count":
        layer_hit = "count_phrases"
        matched = count_matched
    else:
        layer_hit = "meta_phrases"
        matched = meta_matched

    log_detection(logger, "matching.query", scores, selected)
    return DetectionResult(
        intent=selected,
        score=scores[selected],
        layer=layer_hit,
        matched_phrases=matched,
    )
