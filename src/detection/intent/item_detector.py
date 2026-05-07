"""Item-operation and personal-query intent detection — scoring-based, pure Python.

Detects when a user wants to:
- Query personal data ("my tasks", "assigned to me")
- Add / create / insert items into a list
- Query / show / list items in a list

Layers:
  1 — Personal-query phrases  → WEIGHT_EXPLICIT (0.9)  — checked first
  2 — Item-add phrases        → WEIGHT_KEYWORD  (0.6)
  3 — Item-query phrases      → WEIGHT_KEYWORD  (0.6)
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

# ── Layer 1: personal query phrases ─────────────────────────────────────────
_PERSONAL_QUERY_PHRASES = (
    "assigned to me", "assigned to my", "tasks for me", "items assigned to me",
    "i gave", "i created", "i submitted", "i reported", "i assigned",
    "my tasks", "my items", "my issues", "my kudos", "my tickets",
    "my requests", "my records", "my entries",
    "what did i", "what have i", "did i create", "did i add",
    "comment on my", "replied to my", "any comments on my",
    "anyone comment", "who commented on my",
)

# ── Layer 2: item-add phrases ────────────────────────────────────────────────
_ITEM_ADD_PHRASES = (
    "add an item", "add a item", "add item",
    "add a new item", "add new item",
    "add an entry", "add a entry", "add entry",
    "add a new entry", "add new entry",
    "add a record", "add record",
    "add a new record", "add new record",
    "insert record", "insert item", "insert data",
    "create item", "create a item", "create an item",
    "new item to", "new record to", "new entry to",
    "add data", "add data to", "add data to this list",
    "add entries", "add entries to", "populate list", "populate the list",
)

# ── Layer 3: item-query phrases ──────────────────────────────────────────────
_ITEM_QUERY_PHRASES = (
    "all items in", "all items from", "show items in", "show items from",
    "list items in", "list items from", "get items in", "get items from",
    "show me all items", "show me items", "show me the items",
    "show all items", "get all items", "list all items",
    "items in the", "items from the", "view items in",
    "query items", "search items",
)


def detect_item_intent(text: str) -> DetectionResult:
    """Detect item-operation or personal-query intent.

    Returns a :class:`~src.detection.base.DetectionResult` with:
        - ``intent="personal_query"`` for personal data queries
        - ``intent="item_operation"`` for item CRUD
        - ``intent=None`` when no match

    Priority: personal_query > item_add > item_query
    """
    text_lower = text.lower()
    scores: dict[str, float] = {}
    layer_hit = ""
    matched: list[str] = []

    # ── Layer 1: personal query (highest priority) ───────────────────────
    l1_score, l1_matched = score_phrases(text_lower, _PERSONAL_QUERY_PHRASES, WEIGHT_EXPLICIT)
    if l1_score:
        scores["personal_query"] = l1_score
        layer_hit = "personal_phrases"
        matched = l1_matched

    # ── Layer 2: item add ────────────────────────────────────────────────
    if not scores:
        l2_score, l2_matched = score_phrases(text_lower, _ITEM_ADD_PHRASES, WEIGHT_KEYWORD)
        if l2_score:
            scores["item_operation"] = l2_score
            layer_hit = "item_add_phrases"
            matched = l2_matched

    # ── Layer 3: item query ──────────────────────────────────────────────
    if not scores:
        l3_score, l3_matched = score_phrases(text_lower, _ITEM_QUERY_PHRASES, WEIGHT_KEYWORD)
        if l3_score:
            scores["item_operation"] = l3_score
            layer_hit = "item_query_phrases"
            matched = l3_matched

    selected = max(scores, key=scores.get) if scores else None
    log_detection(logger, "intent.item", scores, selected)

    if selected:
        return DetectionResult(
            intent=selected,
            score=scores[selected],
            layer=layer_hit,
            matched_phrases=matched,
        )
    return DetectionResult()
