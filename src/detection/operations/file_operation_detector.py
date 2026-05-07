"""File operation intent detection — scoring-based, pure Python."""

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

_FILE_EXPLICIT_PHRASES = (
    "upload file", "upload document", "upload a file",
    "delete file", "remove file", "delete document", "remove document",
    "download file", "download document",
    "move file", "move document",
    "copy file", "copy document",
    "rename file", "rename document",
    "share file", "share document",
    "check out file", "check in file",
    "check out document", "check in document",
    "restore file", "restore version",
)

_FILE_KEYWORDS = ("file", "document", "attachment")


def detect_file_operation_intent(text: str) -> DetectionResult:
    """Detect file operation intent.

    Returns:
        ``intent="file_operation"`` with confidence score, or ``intent=None``.
    """
    text_lower = text.lower()
    scores: dict[str, float] = {}
    layer_hit = ""
    matched: list[str] = []

    l1_score, l1_matched = score_phrases(text_lower, _FILE_EXPLICIT_PHRASES, WEIGHT_EXPLICIT)
    if l1_score:
        scores["file_operation"] = l1_score
        layer_hit = "explicit_phrases"
        matched = l1_matched

    if "file_operation" not in scores:
        l2_score, l2_matched = score_phrases(text_lower, _FILE_KEYWORDS, WEIGHT_KEYWORD)
        if l2_score:
            scores["file_operation"] = l2_score
            layer_hit = "keywords"
            matched = l2_matched

    selected = "file_operation" if scores else None
    log_detection(logger, "operations.file", scores, selected)

    if selected:
        return DetectionResult(
            intent=selected,
            score=scores[selected],
            layer=layer_hit,
            matched_phrases=matched,
        )
    return DetectionResult()
