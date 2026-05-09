"""Library operation intent detection — scoring-based, pure Python."""

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

_LIBRARY_EXPLICIT_PHRASES = (
    "create library", "new library", "add library", "document library",
    "create document library", "new document library",
    "show libraries", "show all libraries", "list libraries",
    "show me libraries", "show me all libraries",
    "delete library", "remove library",
    "library settings", "enable versioning", "library versioning",
    "add column to library", "library schema", "library structure",
    "add folder to library", "create folder in library", "add a folder to",
    "upload file", "add file", "upload document", "add document",
    "upload to library", "add to library",
)

_LIBRARY_KEYWORDS = ("library",)


def detect_library_operation_intent(text: str) -> DetectionResult:
    """Detect library operation intent.

    Returns:
        ``intent="library_operation"`` with confidence score, or ``intent=None``.
    """
    text_lower = text.lower()
    scores: dict[str, float] = {}
    layer_hit = ""
    matched: list[str] = []

    l1_score, l1_matched = score_phrases(text_lower, _LIBRARY_EXPLICIT_PHRASES, WEIGHT_EXPLICIT)
    if l1_score:
        scores["library_operation"] = l1_score
        layer_hit = "explicit_phrases"
        matched = l1_matched

    if "library_operation" not in scores:
        l2_score, l2_matched = score_phrases(text_lower, _LIBRARY_KEYWORDS, WEIGHT_KEYWORD)
        if l2_score:
            scores["library_operation"] = l2_score
            layer_hit = "keywords"
            matched = l2_matched

    selected = "library_operation" if scores else None
    log_detection(logger, "operations.library", scores, selected)

    if selected:
        return DetectionResult(
            intent=selected,
            score=scores[selected],
            layer=layer_hit,
            matched_phrases=matched,
        )
    return DetectionResult()
