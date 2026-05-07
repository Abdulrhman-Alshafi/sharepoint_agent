"""Confirmation detection — scoring-based, pure Python.

Detects when a user message is a confirmation reply (e.g. "yes", "confirm",
"yes, delete it").

Layers:
  1 — Exact token match against known confirmation words → WEIGHT_EXPLICIT
  2 — Prefix match against known confirmation prefixes   → WEIGHT_KEYWORD
  3 — Regex pattern match                                → WEIGHT_CONTEXTUAL
"""

from __future__ import annotations

import logging
import re

from src.detection.base import (
    DetectionResult,
    WEIGHT_EXPLICIT,
    WEIGHT_KEYWORD,
    WEIGHT_CONTEXTUAL,
    log_detection,
)

logger = logging.getLogger(__name__)

# ── Layer 1: exact token match ───────────────────────────────────────────────
_CONFIRM_EXACT = frozenset({"yes", "yes.", "confirm", "confirmed", "ok", "okay", "sure", "proceed"})

# ── Layer 2: prefix match ────────────────────────────────────────────────────
_CONFIRM_PREFIXES = (
    "confirm",
    "yes, delete",
    "yes, remove",
    "yes delete",
    "yes remove",
    "yes, proceed",
    "yes proceed",
    "yes, create",
    "yes create",
    "yes, do it",
    "yes do it",
    "go ahead",
    "yes, go",
)

# ── Layer 3: regex patterns ──────────────────────────────────────────────────
_CONFIRM_PATTERNS = (
    re.compile(r"^yes[,\s]"),
    re.compile(r"^(sure|ok|okay|confirmed|proceed|go ahead)\b"),
)


def detect_confirmation(text: str) -> DetectionResult:
    """Detect whether a message is a confirmation reply.

    Returns:
        ``intent="confirm"`` with appropriate score when detected,
        ``intent=None`` otherwise.
    """
    stripped = text.strip()
    lower = stripped.lower()
    scores: dict[str, float] = {}
    layer_hit = ""
    matched: list[str] = []

    # ── Layer 1: exact token ─────────────────────────────────────────────
    if lower in _CONFIRM_EXACT:
        scores["confirm"] = WEIGHT_EXPLICIT
        layer_hit = "exact_token"
        matched = [lower]

    # ── Layer 2: prefix match ─────────────────────────────────────────────
    if "confirm" not in scores:
        for prefix in _CONFIRM_PREFIXES:
            if lower.startswith(prefix):
                scores["confirm"] = WEIGHT_KEYWORD
                layer_hit = "prefix_match"
                matched = [prefix]
                break

    # ── Layer 3: regex pattern ────────────────────────────────────────────
    if "confirm" not in scores:
        for pattern in _CONFIRM_PATTERNS:
            if pattern.match(lower):
                scores["confirm"] = WEIGHT_CONTEXTUAL
                layer_hit = "regex_pattern"
                matched = [pattern.pattern]
                break

    selected = "confirm" if scores else None
    log_detection(logger, "validation.confirmation", scores, selected)

    if selected:
        return DetectionResult(
            intent=selected,
            score=scores[selected],
            layer=layer_hit,
            matched_phrases=matched,
        )
    return DetectionResult()
