"""Update intent detection — scoring-based, pure Python.

Distinguishes between:
- Schema-level updates (add column, rename list) → ``"update"``
- Record-level updates (update item field)        → ``"item_operation"``

Layers:
  1 — Trigger-word gate (must pass)
  2 — Explicit item/record indicators  → ``"item_operation"`` at WEIGHT_EXPLICIT
  3 — In-list positional patterns      → ``"item_operation"`` at WEIGHT_KEYWORD
  4 — Field-filter patterns            → ``"item_operation"`` at WEIGHT_CONTEXTUAL
                                         (only when no schema word present)
  5 — Default: schema-level update     → ``"update"`` at WEIGHT_KEYWORD
"""

from __future__ import annotations

import logging

from src.detection.base import (
    DetectionResult,
    WEIGHT_EXPLICIT,
    WEIGHT_KEYWORD,
    WEIGHT_CONTEXTUAL,
    score_phrases,
    score_any_token,
    log_detection,
)

logger = logging.getLogger(__name__)

# ── Layer 1: trigger gate ────────────────────────────────────────────────────
_UPDATE_TRIGGER_WORDS = frozenset(
    {"update", "modify", "change", "edit", "add column", "add to", "rename"}
)

# ── Layer 2: explicit item indicators ───────────────────────────────────────
_ITEM_TOKENS = frozenset({"item", "items", "record"})

# ── Layer 3: in-list positional patterns ────────────────────────────────────
_IN_LIST_PATTERNS = (
    "in this list", "from this list", "in the list", "from the list",
    "in that list", "from that list", "in my list", "from my list",
    "in it", "from it",
)

# ── Layer 4: field-filter patterns ──────────────────────────────────────────
_FIELD_FILTER_PATTERNS = (
    " is ", " whose ", "where ", "with name", "with title",
    "the one ", "the entry ", "the record ", "the row ",
    " field to ", " field ",
)

# ── Schema words (block layer 4 promotion) ──────────────────────────────────
_SCHEMA_WORDS = frozenset({"column", "add a ", "add column", "rename the list", "rename list"})


def detect_update_intent(text: str) -> DetectionResult:
    """Detect update intent and disambiguate schema vs record operations.

    Returns:
        ``intent="update"``          — schema-level resource update
        ``intent="item_operation"``  — record-level item update
        ``intent=None``              — no update intent detected
    """
    text_lower = text.lower()
    tokens = frozenset(text_lower.split())
    scores: dict[str, float] = {}
    layer_hit = ""
    matched: list[str] = []

    # ── Layer 1: must have a trigger word ────────────────────────────────
    gate_score, gate_matched = score_any_token(tokens, _UPDATE_TRIGGER_WORDS, WEIGHT_KEYWORD)
    if not gate_score:
        # Also check multi-word triggers
        multi_matched = [p for p in _UPDATE_TRIGGER_WORDS if p in text_lower and " " in p]
        if not multi_matched:
            log_detection(logger, "intent.update", {}, None)
            return DetectionResult()
        gate_matched = multi_matched

    # ── Layer 2: explicit item / record token ────────────────────────────
    item_tokens = tokens & _ITEM_TOKENS
    if item_tokens or "list item" in text_lower or "the item" in text_lower:
        scores["item_operation"] = WEIGHT_EXPLICIT
        layer_hit = "item_token"
        matched = list(item_tokens) or (["list item"] if "list item" in text_lower else ["the item"])

    # ── Layer 3: in-list positional patterns ─────────────────────────────
    if "item_operation" not in scores:
        l3_score, l3_matched = score_phrases(text_lower, _IN_LIST_PATTERNS, WEIGHT_KEYWORD)
        if l3_score:
            scores["item_operation"] = l3_score
            layer_hit = "in_list_patterns"
            matched = l3_matched

    # ── Layer 4: field-filter patterns (no schema words) ─────────────────
    if "item_operation" not in scores:
        has_schema = any(sw in text_lower for sw in _SCHEMA_WORDS)
        l4_score, l4_matched = score_phrases(text_lower, _FIELD_FILTER_PATTERNS, WEIGHT_CONTEXTUAL)
        if l4_score and not has_schema:
            scores["item_operation"] = l4_score
            layer_hit = "field_filter"
            matched = l4_matched

    # ── Layer 5: default — schema-level update ────────────────────────────
    if "item_operation" not in scores:
        scores["update"] = WEIGHT_KEYWORD
        layer_hit = "default_schema_update"
        matched = gate_matched

    selected = max(scores, key=scores.get) if scores else None
    conflicts = {k: v for k, v in scores.items() if k != selected} if len(scores) > 1 else None
    log_detection(logger, "intent.update", scores, selected, conflicts)

    if selected:
        return DetectionResult(
            intent=selected,
            score=scores[selected],
            layer=layer_hit,
            matched_phrases=matched,
            conflicts=conflicts or {},
        )
    return DetectionResult()
