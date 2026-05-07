"""List-item operation intent detection — scoring-based, pure Python."""

from __future__ import annotations

import logging

from src.detection.base import (
    DetectionResult,
    WEIGHT_EXPLICIT,
    WEIGHT_KEYWORD,
    WEIGHT_CONTEXTUAL,
    score_phrases,
    log_detection,
)

logger = logging.getLogger(__name__)

_ITEM_EXPLICIT_PHRASES = (
    "add item", "add a new item", "create item", "new item",
    "update item", "edit item", "modify item", "change item",
    "delete item", "remove item",
    "add list item", "create list item",
    "update list item", "edit list item",
    "delete list item", "remove list item",
    "add row", "add record", "insert record",
    "update row", "edit row", "new record",
    "delete row", "remove row", "drop record", "delete record", "remove item",
    "add data", "add entries", "add entries to", "populate list", "populate the list",
)

_OPERATION_KEYWORDS = (
    "add", "create", "insert",
    "update", "modify", "change", "edit", "set", "increase", "decrease",
    "delete", "remove",
    "show", "find", "list", "get", "display", "how many", "count",
    "sorted", "top", "first",
    "attach", "attachment", "file to item", "upload to item",
    "create view", "new view", "view showing", "view with",
)

_ITEM_INDICATORS = (
    "record", "item", "entry", "row", "data",
    "for", "from", "with",
    "salary", "employee", "task",
    "above", "below", "equal", "greater than", "less than",
    "sorted by", "order by", "top 10", "first 5",
)

_LIST_LEVEL_EXCLUSIONS = (
    "new list", "create list", "delete list",
    "add column", "remove column", "rename list",
    "document library", "entire list", "entire library", "delete the entire",
)


def detect_list_item_operation_intent(text: str) -> DetectionResult:
    """Detect list-item operation intent.

    Uses a 3-layer approach:
      L1 — explicit item-operation phrases (0.9)
      L2 — operation keyword + item indicator combo (0.6)
      L3 — item indicator alone as weak signal (0.3)

    List-level exclusion phrases always suppress detection.

    Returns:
        ``intent="list_item_operation"`` with confidence score, or ``intent=None``.
    """
    text_lower = text.lower()

    # Exclusion guard — list-level ops should not be treated as item ops
    for exc in _LIST_LEVEL_EXCLUSIONS:
        if exc in text_lower:
            log_detection(logger, "operations.list_item", {}, None,
                          {"excluded_by": 1.0})
            return DetectionResult()

    scores: dict[str, float] = {}
    layer_hit = ""
    matched: list[str] = []

    # Layer 1
    l1_score, l1_matched = score_phrases(text_lower, _ITEM_EXPLICIT_PHRASES, WEIGHT_EXPLICIT)
    if l1_score:
        scores["list_item_operation"] = l1_score
        layer_hit = "explicit_phrases"
        matched = l1_matched

    if "list_item_operation" not in scores:
        # Layer 2 — operation keyword AND item indicator
        op_score, op_matched = score_phrases(text_lower, _OPERATION_KEYWORDS, WEIGHT_KEYWORD)
        ind_score, ind_matched = score_phrases(text_lower, _ITEM_INDICATORS, WEIGHT_KEYWORD)
        if op_score and ind_score:
            scores["list_item_operation"] = WEIGHT_KEYWORD
            layer_hit = "operation+indicator"
            matched = op_matched + ind_matched

    if "list_item_operation" not in scores:
        # Layer 3 — item indicator as weak signal
        ind_score, ind_matched = score_phrases(text_lower, _ITEM_INDICATORS, WEIGHT_CONTEXTUAL)
        if ind_score:
            scores["list_item_operation"] = WEIGHT_CONTEXTUAL
            layer_hit = "item_indicator"
            matched = ind_matched

    selected = "list_item_operation" if scores else None
    log_detection(logger, "operations.list_item", scores, selected)

    if selected:
        return DetectionResult(
            intent=selected,
            score=scores[selected],
            layer=layer_hit,
            matched_phrases=matched,
        )
    return DetectionResult()
