"""Central intent router — scoring-based, pure Python.

Runs all individual detectors, collects their scores, applies explicit
conflict-resolution rules, and returns the winning intent.

Priority order (when two detectors return the same score the ordering below
acts as the tiebreaker — higher in the list wins):
  1. page_query
  2. personal_query
  3. item_operation
  4. analyze
  5. update
  6. delete

Conflict rules:
  - ``analyze`` vs ``page_query``: if both score the same, ``page_query`` wins
    (information requests should default to page handler).
  - ``update`` vs ``item_operation``: if both hit, ``item_operation`` wins
    (more specific handler).
  - ``delete`` vs ``item_operation``: same — ``item_operation`` wins.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.detection.base import log_detection
from src.detection.intent.page_detector import detect_page_intent
from src.detection.intent.item_detector import detect_item_intent
from src.detection.intent.analyze_detector import detect_analyze_intent
from src.detection.intent.update_detector import detect_update_intent
from src.detection.intent.delete_detector import detect_delete_intent
from src.detection.operations.site_operation_detector import detect_site_operation_intent
from src.detection.operations.page_operation_detector import detect_page_operation_intent
from src.detection.operations.library_operation_detector import detect_library_operation_intent
from src.detection.operations.file_operation_detector import detect_file_operation_intent
from src.detection.operations.permission_operation_detector import detect_permission_operation_intent
from src.detection.operations.enterprise_operation_detector import detect_enterprise_operation_intent

logger = logging.getLogger(__name__)

# Lower index = higher priority in tiebreaks
_PRIORITY_ORDER = [
    "page_query",
    "personal_query",
    "item_operation",
    "analyze",
    "update",
    "delete",
    "site_operation",
    "page_operation",
    "library_operation",
    "file_operation",
    "permission_operation",
    "enterprise_operation",
]


def route_intent(text: str) -> Optional[str]:
    """Detect and route intent from a plain-text user message.

    Runs all detectors, builds a score map, applies conflict-resolution
    rules, and returns the highest-confidence intent name.

    Returns ``None`` when no detector fires with sufficient confidence
    (threshold ≥ 0.05) — the caller should fall through to the AI classifier.

    Possible return values:
        - ``"page_query"``
        - ``"personal_query"``
        - ``"item_operation"``
        - ``"analyze"``
        - ``"update"``
        - ``"delete"``
        - ``"site_operation"``
        - ``"page_operation"``
        - ``"library_operation"``
        - ``"file_operation"``
        - ``"permission_operation"``
        - ``"enterprise_operation"``
        - ``None``
    """
    # ── Run all detectors ────────────────────────────────────────────────
    page_r    = detect_page_intent(text)
    item_r    = detect_item_intent(text)
    analyze_r = detect_analyze_intent(text)
    update_r  = detect_update_intent(text)
    delete_r  = detect_delete_intent(text)
    site_r    = detect_site_operation_intent(text)
    page_op_r = detect_page_operation_intent(text)
    lib_op_r  = detect_library_operation_intent(text)
    file_op_r = detect_file_operation_intent(text)
    perm_op_r = detect_permission_operation_intent(text)
    ent_op_r  = detect_enterprise_operation_intent(text)

    scores: dict[str, float] = {}
    for result in (page_r, item_r, analyze_r, update_r, delete_r, site_r, page_op_r, lib_op_r, file_op_r, perm_op_r, ent_op_r):
        if result.is_detected():
            # A detector may produce multiple competing intents — keep highest
            existing = scores.get(result.intent, 0.0)
            if result.score > existing:
                scores[result.intent] = result.score

    if not scores:
        log_detection(logger, "intent.router", {}, None)
        return None

    # ── Explicit conflict resolution ──────────────────────────────────────
    conflicts: dict[str, float] = {}

    # Rule 1: item_operation beats update / delete at equal or higher score
    if "item_operation" in scores:
        for loser in ("update", "delete"):
            if loser in scores and scores["item_operation"] >= scores[loser]:
                conflicts[loser] = scores.pop(loser)

    # Rule 2: page_query beats analyze at equal score
    if "page_query" in scores and "analyze" in scores:
        if scores["page_query"] >= scores["analyze"]:
            conflicts["analyze"] = scores.pop("analyze")

    # ── Select winner ─────────────────────────────────────────────────────
    if not scores:
        log_detection(logger, "intent.router", {}, None, conflicts)
        return None

    # Highest score first; tiebreak by priority order
    selected = max(
        scores,
        key=lambda k: (
            scores[k],
            -_PRIORITY_ORDER.index(k) if k in _PRIORITY_ORDER else -99,
        ),
    )

    log_detection(logger, "intent.router", scores, selected, conflicts or None)
    return selected
