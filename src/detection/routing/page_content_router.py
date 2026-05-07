"""Page-content upgrade router — scoring-based, pure Python.

Detects whether a page-routed query should be upgraded from a generic
page listing intent to a PAGE_CONTENT intent (i.e., the user is asking
about *what is written* on a page, not just listing pages).

Migrated from ``AIDataQueryService._PAGE_CONTENT_UPGRADE_KEYWORDS`` in
``src/infrastructure/external_services/query/service.py``.

Layers:
  1 — Explicit content-seeking phrases → WEIGHT_EXPLICIT (0.9)
  2 — Deadline / announcement signals  → WEIGHT_KEYWORD  (0.6)
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

# ── Layer 1: explicit content-access phrases ─────────────────────────────────
_CONTENT_EXPLICIT_PHRASES = (
    "what does",
    "what is on",
    "what is written",
    "show me the content",
    "what does the",
    "what is on the",
)

# ── Layer 2: content-signal keywords ────────────────────────────────────────
_CONTENT_SIGNAL_KEYWORDS = (
    "deadline",
    "deadlines",
    "announcement",
    "announcements",
    "events",
    "schedule",
    "due date",
)


def detect_page_content_upgrade(text: str) -> DetectionResult:
    """Detect whether a page query should be upgraded to PAGE_CONTENT intent.

    Returns:
        ``intent="page_content_upgrade"`` when the message is asking about
        the actual content of a page (not just listing pages), otherwise
        ``intent=None``.
    """
    text_lower = text.lower()
    scores: dict[str, float] = {}
    layer_hit = ""
    matched: list[str] = []

    # ── Layer 1: explicit content phrases ────────────────────────────────
    l1_score, l1_matched = score_phrases(text_lower, _CONTENT_EXPLICIT_PHRASES, WEIGHT_EXPLICIT)
    if l1_score:
        scores["page_content_upgrade"] = l1_score
        layer_hit = "content_phrases"
        matched = l1_matched

    # ── Layer 2: content-signal keywords ──────────────────────────────────
    if "page_content_upgrade" not in scores:
        l2_score, l2_matched = score_phrases(text_lower, _CONTENT_SIGNAL_KEYWORDS, WEIGHT_KEYWORD)
        if l2_score:
            scores["page_content_upgrade"] = l2_score
            layer_hit = "content_keywords"
            matched = l2_matched

    selected = "page_content_upgrade" if scores else None
    log_detection(logger, "routing.page_content", scores, selected)

    if selected:
        return DetectionResult(
            intent=selected,
            score=scores[selected],
            layer=layer_hit,
            matched_phrases=matched,
        )
    return DetectionResult()
