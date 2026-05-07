"""Permission operation intent detection — scoring-based, pure Python."""

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

_PERMISSION_EXPLICIT_PHRASES = (
    "grant access", "revoke access", "remove access",
    "check permissions", "check access", "show permissions",
    "add user to group", "remove user from group",
    "who has access", "who can access",
    "give permission", "deny permission",
    "share with", "stop sharing",
    "make public", "make private",
    "change permission", "update permission",
    "add member", "remove member",
)

_PERMISSION_KEYWORDS = ("permission", "access", "group", "share")


def detect_permission_operation_intent(text: str) -> DetectionResult:
    """Detect permission/access operation intent.

    Returns:
        ``intent="permission_operation"`` with confidence score, or ``intent=None``.
    """
    text_lower = text.lower()
    scores: dict[str, float] = {}
    layer_hit = ""
    matched: list[str] = []

    l1_score, l1_matched = score_phrases(text_lower, _PERMISSION_EXPLICIT_PHRASES, WEIGHT_EXPLICIT)
    if l1_score:
        scores["permission_operation"] = l1_score
        layer_hit = "explicit_phrases"
        matched = l1_matched

    if "permission_operation" not in scores:
        l2_score, l2_matched = score_phrases(text_lower, _PERMISSION_KEYWORDS, WEIGHT_KEYWORD)
        if l2_score:
            scores["permission_operation"] = l2_score
            layer_hit = "keywords"
            matched = l2_matched

    selected = "permission_operation" if scores else None
    log_detection(logger, "operations.permission", scores, selected)

    if selected:
        return DetectionResult(
            intent=selected,
            score=scores[selected],
            layer=layer_hit,
            matched_phrases=matched,
        )
    return DetectionResult()
