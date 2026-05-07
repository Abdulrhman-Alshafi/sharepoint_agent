"""Page-related intent detection — scoring-based, pure Python.

Detects when a user's message is asking about page content, news,
announcements, or other information that lives on SharePoint pages
rather than in lists or libraries.

Layers:
  0 — Concept-based routing via ConceptMapper (external, optional)
  1 — Explicit phrases (high confidence) → WEIGHT_EXPLICIT (0.9)
  2 — Question-word + page-reference combination → WEIGHT_KEYWORD (0.6)
  3 — Info-seeking with no explicit resource type → WEIGHT_CONTEXTUAL (0.3)
"""

from __future__ import annotations

import logging
from typing import Optional

from src.detection.base import (
    DetectionResult,
    WEIGHT_EXPLICIT,
    WEIGHT_KEYWORD,
    WEIGHT_CONTEXTUAL,
    score_phrases,
    log_detection,
)

logger = logging.getLogger(__name__)

# ── Layer 0: concept signals ─────────────────────────────────────────────────
_PAGE_CONCEPT_SIGNALS = frozenset({
    "announcements", "news", "events", "updates", "schedule",
    "calendar", "spotlight", "hero", "welcome", "highlights",
    "newsletter", "recent launches", "company news", "team news", "launches",
})

_PAGE_MANAGEMENT_WORDS = frozenset({
    "create", "make a page", "build a page", "add a page", "new page",
    "update the page", "edit the page", "delete the page",
    "remove the page", "publish the page",
})

# ── Layer 1: explicit high-confidence phrases ────────────────────────────────
_PAGE_CONTENT_PHRASES = (
    "page says", "on home page", "on the page", "on news page",
    "on events page", "on the intranet", "what is written on",
    "show me the content of", "read the page", "content of the page",
    "content on the page", "text on the page", "what is on the home",
    "what's on the home", "what events are on", "what is scheduled on",
    "what does the home", "what does the news", "what does the page",
    "what does the events", "what does the about", "what does the welcome",
    "what's on the", "what is on the", "what does the",
    "announcements on", "deadline on", "schedule on", "events on",
    "what is posted on", "what's posted on",
)

# ── Layer 2: question starters + page references ─────────────────────────────
_PAGE_QUESTION_STARTERS = (
    "what ", "who ", "when ", "where ", "which ", "how many ",
    "tell me ", "show me ", "find ", "get ", "list ",
)

_PAGE_REFERENCE_WORDS = (
    " page", "home page", "homepage", "intranet page", "news page",
    "welcome page", "about page", "events page", "project page",
    "hr page", "team page", "updates page", "dashboard page",
)

# ── Layer 3: info-seeking without explicit resource type ─────────────────────
_RESOURCE_TYPE_WORDS = (
    "list", "library", "document", "file", "site", "item", "record",
    "column", "folder", "drive", "sharepoint list", "sharepoint library",
)

_INFO_STARTERS = (
    "what is the ", "what are the ", "what is a ", "what are ",
    "tell me about the ", "tell me about ",
    "show me the ", "show me ",
    "what's the ", "what's in the ", "what's on the ",
    "describe the ", "explain the ",
)

_METADATA_WORDS = (
    "how many", "list all", "show all", "all the",
    "all lists", "all libraries", "all pages", "all sites",
)


def detect_page_intent(text: str) -> DetectionResult:
    """Detect page-content query intent.

    Returns a :class:`~src.detection.base.DetectionResult` with
    ``intent="page_query"`` when the message is asking about page
    content, otherwise ``intent=None``.

    Layers used:
        0 — ConceptMapper (optional, wrapped in try/except)
        1 — Explicit phrases              → score 0.9
        2 — Question + page reference     → score 0.6
        3 — Info-seeking / no resource    → score 0.3
    """
    text_lower = text.lower()
    scores: dict[str, float] = {}
    layer_hit = ""
    matched: list[str] = []

    # ── Layer 0: concept mapper ──────────────────────────────────────────
    is_management = any(m in text_lower for m in _PAGE_MANAGEMENT_WORDS)
    try:
        from src.infrastructure.services.concept_mapper import ConceptMapper
        mapping = ConceptMapper().map_query(text_lower)
        if mapping.resource_hint == "page" or (
            set(mapping.concepts) & _PAGE_CONCEPT_SIGNALS and not is_management
        ):
            scores["page_query"] = WEIGHT_EXPLICIT
            layer_hit = "concept_mapper"
            matched = list(set(mapping.concepts) & _PAGE_CONCEPT_SIGNALS)
    except Exception:
        pass  # never let an optional layer break detection

    # ── Layer 1: explicit phrases ────────────────────────────────────────
    if "page_query" not in scores:
        l1_score, l1_matched = score_phrases(text_lower, _PAGE_CONTENT_PHRASES, WEIGHT_EXPLICIT)
        if l1_score:
            scores["page_query"] = l1_score
            layer_hit = "explicit_phrases"
            matched = l1_matched

    # ── Layer 2: question + page reference (not management) ─────────────
    if "page_query" not in scores:
        has_question = any(
            text_lower.startswith(qw) or f" {qw}" in text_lower
            for qw in _PAGE_QUESTION_STARTERS
        )
        has_page_ref = any(ref in text_lower for ref in _PAGE_REFERENCE_WORDS)
        if has_question and has_page_ref and not is_management:
            scores["page_query"] = WEIGHT_KEYWORD
            layer_hit = "question_page_ref"
            matched = [ref for ref in _PAGE_REFERENCE_WORDS if ref in text_lower]

    # ── Layer 3: info-seeking with no resource type mentioned ────────────
    if "page_query" not in scores:
        has_info = any(
            text_lower.startswith(s) or text_lower.startswith("can you " + s.strip())
            for s in _INFO_STARTERS
        )
        no_resource = not any(rw in text_lower for rw in _RESOURCE_TYPE_WORDS)
        no_meta = not any(mw in text_lower for mw in _METADATA_WORDS)
        if has_info and no_resource and no_meta:
            scores["page_query"] = WEIGHT_CONTEXTUAL
            layer_hit = "info_seek_no_resource"
            matched = [s for s in _INFO_STARTERS if text_lower.startswith(s)]

    selected = "page_query" if "page_query" in scores else None
    log_detection(logger, "intent.page", scores, selected)

    if selected:
        return DetectionResult(
            intent=selected,
            score=scores[selected],
            layer=layer_hit,
            matched_phrases=matched,
        )
    return DetectionResult()
