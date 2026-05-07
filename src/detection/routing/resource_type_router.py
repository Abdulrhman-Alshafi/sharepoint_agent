"""Resource-type routing — scoring-based, pure Python.

Detects which SharePoint resource type the user wants to provision/create:
SITE, PAGE, LIBRARY, LIST, GROUP, VIEW, or CONTENT_TYPE.

Layers per resource type:
  1 — Multi-word specific phrases (high confidence) → WEIGHT_EXPLICIT (0.9)
  2 — Single keyword match                          → WEIGHT_KEYWORD  (0.6)

Conflict resolution:
  - If PAGE and SITE both score, PAGE wins (more specific ask).
  - If LIST and LIBRARY both score, LIBRARY wins (more specific).
  - If CONTENT_TYPE scores, it takes priority over LIST.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.detection.base import (
    DetectionResult,
    WEIGHT_EXPLICIT,
    WEIGHT_KEYWORD,
    score_phrases,
    log_detection,
)

logger = logging.getLogger(__name__)

# Each entry: (resource_type_str, layer, phrases/keywords, weight)
_RULES: list[tuple[str, str, tuple, float]] = [
    # ── SITE ──────────────────────────────────────────────────────────────
    ("SITE", "explicit", (
        "sharepoint site", "create a site", "create site", "new site",
        "team site", "communication site", "intranet", "workspace",
        "site called", "site named",
    ), WEIGHT_EXPLICIT),

    # ── PAGE — must check before SITE to win on ties ──────────────────────
    ("PAGE", "explicit", (
        "sharepoint page", "site page", "landing page", "web page",
        "create a page", "create page", "new page",
        "page called", "page named", "dashboard",
    ), WEIGHT_EXPLICIT),

    # ── LIBRARY ───────────────────────────────────────────────────────────
    ("LIBRARY", "explicit", (
        "document library", "file storage", "doc library",
        "upload files", "file repository", "create library",
        "new library",
    ), WEIGHT_EXPLICIT),
    ("LIBRARY", "keyword", ("library",), WEIGHT_KEYWORD),

    # ── CONTENT_TYPE ──────────────────────────────────────────────────────
    ("CONTENT_TYPE", "explicit", (
        "content type", "document type",
    ), WEIGHT_EXPLICIT),

    # ── LIST — checked after LIBRARY so "library" doesn't also match LIST ─
    ("LIST", "explicit", (
        "create a list", "create list", "new list",
        "list called", "list named",
        "task tracker", "tracker", "directory",
        "inventory", "registry",
    ), WEIGHT_EXPLICIT),
    ("LIST", "keyword", (" list ",), WEIGHT_KEYWORD),

    # ── GROUP ─────────────────────────────────────────────────────────────
    ("GROUP", "explicit", (
        "permission group", "access group", "sharepoint group",
        "security group",
    ), WEIGHT_EXPLICIT),
    ("GROUP", "keyword", ("group",), WEIGHT_KEYWORD),

    # ── VIEW ──────────────────────────────────────────────────────────────
    ("VIEW", "explicit", (
        "filtered view", "custom view",
    ), WEIGHT_EXPLICIT),
    ("VIEW", "keyword", ("view",), WEIGHT_KEYWORD),
]

# Conflict rules: when both present, first member wins
_CONFLICT_PRIORITY = [
    ("PAGE", "SITE"),         # "site page" → PAGE
    ("LIBRARY", "LIST"),      # "document library" → LIBRARY
    ("CONTENT_TYPE", "LIST"), # "content type" → CONTENT_TYPE
]

# Guard against false positives: these messages should NOT match SITE
_SITE_FALSE_POSITIVE = ("site page",)

# Same for PAGE
_PAGE_FALSE_POSITIVE = ("list page", "library page")


def route_resource_type(text: str) -> DetectionResult:
    """Detect which SharePoint resource type the user wants to create.

    Returns:
        ``DetectionResult`` with ``intent`` equal to one of:
        ``"SITE"``, ``"PAGE"``, ``"LIBRARY"``, ``"LIST"``, ``"GROUP"``,
        ``"VIEW"``, ``"CONTENT_TYPE"``, or ``None`` when no match.
    """
    text_lower = text.lower()
    scores: dict[str, float] = {}
    layers: dict[str, str] = {}
    phrases_hit: dict[str, list[str]] = {}

    for resource, layer, phrases, weight in _RULES:
        score, matched = score_phrases(text_lower, phrases, weight)
        if score and score > scores.get(resource, 0.0):
            scores[resource] = score
            layers[resource] = layer
            phrases_hit[resource] = matched

    # ── False-positive guards ─────────────────────────────────────────────
    if "SITE" in scores and any(fp in text_lower for fp in _SITE_FALSE_POSITIVE):
        del scores["SITE"]

    if "PAGE" in scores and any(fp in text_lower for fp in _PAGE_FALSE_POSITIVE):
        del scores["PAGE"]

    # ── Conflict resolution ───────────────────────────────────────────────
    conflicts: dict[str, float] = {}
    for winner, loser in _CONFLICT_PRIORITY:
        if winner in scores and loser in scores:
            if scores[winner] >= scores[loser]:
                conflicts[loser] = scores.pop(loser)

    selected = max(scores, key=scores.get) if scores else None
    log_detection(logger, "routing.resource_type", scores, selected, conflicts or None)

    if selected:
        return DetectionResult(
            intent=selected,
            score=scores[selected],
            layer=layers.get(selected, ""),
            matched_phrases=phrases_hit.get(selected, []),
            conflicts=conflicts,
        )
    return DetectionResult()


def route_resource_type_str(text: str) -> Optional[str]:
    """Convenience wrapper returning intent string or None."""
    return route_resource_type(text).intent
