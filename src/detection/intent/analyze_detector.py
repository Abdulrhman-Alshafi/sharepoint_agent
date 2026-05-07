"""Analyze / inspect intent detection — scoring-based, pure Python.

Detects when a user wants to analyze, summarize, or inspect a resource.

Layers:
  1 — ``"more about / details about / details on"`` + resource word
        → ``"analyze"`` at WEIGHT_EXPLICIT
      Absent resource word → ``"page_query"`` (these phrases are page-like)
  2 — General trigger + resource word
        → ``"analyze"`` at WEIGHT_KEYWORD
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

_ANALYZE_TRIGGER_WORDS = frozenset({
    "analyze", "what is in", "what is the content of", "summarize", "describe",
    "tell me about", "explain", "more about", "details about", "details on", "inspect",
})

_ANALYZE_RESOURCE_WORDS = frozenset({"site", "page", "list", "library"})

# Phrases that only make sense with a resource target
_ANALYZE_NEEDS_RESOURCE = frozenset({"more about", "details about", "details on"})


def detect_analyze_intent(text: str) -> DetectionResult:
    """Detect analyze / inspect intent.

    Returns:
        ``intent="analyze"``     — user wants analysis of a specific resource
        ``intent="page_query"``  — phrase implies page context, no resource word
        ``intent=None``          — no analyze intent detected
    """
    text_lower = text.lower()
    scores: dict[str, float] = {}
    layer_hit = ""
    matched: list[str] = []

    # ── Layer 1: narrow phrases (only valid WITH resource) ────────────────
    l1_score, l1_matched = score_phrases(text_lower, _ANALYZE_NEEDS_RESOURCE, WEIGHT_EXPLICIT)
    if l1_score:
        has_resource = any(rw in text_lower for rw in _ANALYZE_RESOURCE_WORDS)
        if has_resource:
            scores["analyze"] = l1_score
            layer_hit = "narrow_phrase_with_resource"
            matched = l1_matched
        else:
            scores["page_query"] = WEIGHT_KEYWORD
            layer_hit = "narrow_phrase_no_resource"
            matched = l1_matched

    # ── Layer 2: general trigger + resource word ──────────────────────────
    if not scores:
        l2_score, l2_matched = score_phrases(text_lower, _ANALYZE_TRIGGER_WORDS, WEIGHT_KEYWORD)
        if l2_score:
            has_resource = any(rw in text_lower for rw in _ANALYZE_RESOURCE_WORDS)
            if has_resource:
                scores["analyze"] = l2_score
                layer_hit = "trigger_with_resource"
                matched = l2_matched
            # no resource → not enough signal for analyze; fall through to None

    selected = max(scores, key=scores.get) if scores else None
    log_detection(logger, "intent.analyze", scores, selected)

    if selected:
        return DetectionResult(
            intent=selected,
            score=scores[selected],
            layer=layer_hit,
            matched_phrases=matched,
        )
    return DetectionResult()
