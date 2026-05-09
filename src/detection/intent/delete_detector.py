"""Delete intent detection — scoring-based, pure Python.

Handles:
- Explicit triggers: delete / remove / drop
- Common typos: delte, delet, deleet, etc.
- File-extension detection → routes to file handler (None)
- Pronoun-based delete ("delete it", "remove this")
- Confirmation patterns ("yes, delete X")
- Item vs resource disambiguation

Layers:
  1 — Trigger/typo gate (must pass)
  2 — Explicit item/record tokens   → ``"item_operation"`` at WEIGHT_EXPLICIT
  3 — In-list positional patterns   → ``"item_operation"`` at WEIGHT_KEYWORD
  4 — File extension / "file" token → ``None`` (route to file handler)
  5 — Explicit resource word        → ``"delete"`` at WEIGHT_EXPLICIT
  6 — Field-filter patterns         → ``"item_operation"`` at WEIGHT_CONTEXTUAL
  7 — Confirmation ("yes, delete X") → ``"delete"`` at WEIGHT_KEYWORD
      Pronoun ("delete it/this")     → ``"item_operation"`` at WEIGHT_KEYWORD
  8 — Default (no resource keyword)  → ``"item_operation"`` at WEIGHT_CONTEXTUAL
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

# ── Layer 1: trigger words and typos ────────────────────────────────────────
_DELETE_TRIGGER_WORDS = frozenset({"delete", "remove", "drop"})
_DELETE_TYPOS = frozenset({"delte", "delet", "deleet", "deelte", "dleet", "delt"})

# ── Layer 2: item/record tokens ──────────────────────────────────────────────
_ITEM_TOKENS = frozenset({"item", "items"})

# ── Layer 3: in-list patterns ────────────────────────────────────────────────
_IN_LIST_PATTERNS = (
    "in this list", "from this list", "in the list", "from the list",
    "in that list", "from that list", "in my list", "from my list",
    "in it", "from it",
)

# ── Layer 4: file signals ─────────────────────────────────────────────────────
_FILE_EXTS = frozenset({
    ".docx", ".xlsx", ".pdf", ".pptx", ".csv", ".txt", ".png", ".jpg",
    ".jpeg", ".zip", ".doc", ".xls", ".ppt", ".msg", ".gif", ".mp4",
})

# ── Layer 5: explicit resource words ─────────────────────────────────────────
_DELETE_RESOURCE_WORDS = frozenset({"list", "site", "page", "library"})

# ── Layer 6: field-filter patterns ──────────────────────────────────────────
_FIELD_FILTER_PATTERNS = (
    " is ", " whose ", "where ", "with name", "with title",
    "the one ", "the entry ", "the record ", "the row ",
    "named ", "called ", "titled ",
)

# ── Layer 7: pronouns ─────────────────────────────────────────────────────────
_PRONOUN_REF = frozenset({"it", "this", "that", "these", "those", "them"})


def detect_delete_intent(text: str) -> DetectionResult:
    """Detect delete intent and disambiguate resource vs item vs file.

    Returns:
        ``intent="delete"``          — resource deletion (list, site, page, library)
        ``intent="item_operation"``  — list-item deletion
        ``intent=None``              — file deletion (let file handler take over)
                                       or no delete intent detected
    """
    text_lower = text.lower()
    tokens = frozenset(text_lower.split())
    scores: dict[str, float] = {}
    layer_hit = ""
    matched: list[str] = []

    # ── Layer 1: gate — must have trigger or typo ─────────────────────────
    has_trigger, trig_m = score_any_token(tokens, _DELETE_TRIGGER_WORDS, WEIGHT_KEYWORD)
    has_typo, typo_m = score_any_token(tokens, _DELETE_TYPOS, WEIGHT_KEYWORD)
    if not has_trigger and not has_typo:
        log_detection(logger, "intent.delete", {}, None)
        return DetectionResult()
    gate_matched = trig_m or typo_m

    # ── Layer 2: explicit item/record token → item handler ────────────────
    if _ITEM_TOKENS & tokens or "list item" in text_lower:
        scores["item_operation"] = WEIGHT_EXPLICIT
        layer_hit = "item_token"
        matched = list(_ITEM_TOKENS & tokens) or ["list item"]

    # ── Layer 3: in-list positional patterns → item handler ───────────────
    if "item_operation" not in scores:
        l3_score, l3_matched = score_phrases(text_lower, _IN_LIST_PATTERNS, WEIGHT_KEYWORD)
        if l3_score:
            scores["item_operation"] = l3_score
            layer_hit = "in_list_patterns"
            matched = l3_matched

    # ── Layer 4: file signals → route to file handler (return None) ───────
    if "item_operation" not in scores:
        has_ext = any(ext in text_lower for ext in _FILE_EXTS)
        has_file_token = "file" in tokens
        if has_ext or has_file_token:
            log_detection(logger, "intent.delete", {"file_handler": 1.0}, None)
            return DetectionResult()  # file handler owns this

    # ── Layer 5: explicit resource word → definitely delete ───────────────
    if "item_operation" not in scores:
        res_tokens = tokens & _DELETE_RESOURCE_WORDS
        if res_tokens:
            scores["delete"] = WEIGHT_EXPLICIT
            layer_hit = "resource_word"
            matched = list(res_tokens)

    # ── Layer 6: field-filter patterns → item operation ───────────────────
    if not scores:
        l6_score, l6_matched = score_phrases(text_lower, _FIELD_FILTER_PATTERNS, WEIGHT_CONTEXTUAL)
        if l6_score:
            scores["item_operation"] = l6_score
            layer_hit = "field_filter"
            matched = l6_matched

    # ── Layer 7: confirmation or pronoun ──────────────────────────────────
    if not scores:
        is_confirm = any(c in text_lower for c in ("yes,", "yess,", "yep,", "yeah,")) or any(text_lower.startswith(c) for c in ("yes ", "yess ", "yep ", "yeah "))
        has_pronoun = bool(tokens & _PRONOUN_REF)
        if is_confirm:
            # Explicit confirmation ("yes, delete X") — keep as resource-delete
            scores["delete"] = WEIGHT_KEYWORD
            layer_hit = "confirm"
            matched = gate_matched
        elif has_pronoun:
            # "delete it/this/that" — almost always referring to an item
            scores["item_operation"] = WEIGHT_KEYWORD
            layer_hit = "pronoun_item"
            matched = gate_matched

    # ── Layer 8: default — no resource word present → route to delete orchestrator ─
    if not scores:
        scores["delete"] = WEIGHT_CONTEXTUAL
        layer_hit = "default_delete"
        matched = gate_matched

    selected = max(scores, key=scores.get) if scores else None
    conflicts = {k: v for k, v in scores.items() if k != selected} if len(scores) > 1 else None
    log_detection(logger, "intent.delete", scores, selected, conflicts)

    if selected:
        return DetectionResult(
            intent=selected,
            score=scores[selected],
            layer=layer_hit,
            matched_phrases=matched,
            conflicts=conflicts or {},
        )
    return DetectionResult()
