"""Webpart-type routing — scoring-based, pure Python.

Detects which SharePoint web-part type a user message refers to when
building or modifying a page.

Layers:
  1 — Multi-word exact phrases  → WEIGHT_EXPLICIT (0.9)
  2 — Single keyword match      → WEIGHT_KEYWORD  (0.6)

Returns one of the canonical webpart type strings:
    "Hero", "Image", "QuickLinks", "News", "People",
    "List", "DocumentLibrary", "Events", "Text"
or ``None`` when no signal is found.
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

# (webpart_type, layer, phrases, weight)
_RULES: list[tuple[str, str, tuple, float]] = [
    ("Hero",           "explicit", ("hero banner", "banner image"),   WEIGHT_EXPLICIT),
    ("Hero",           "keyword",  ("hero", "banner"),                WEIGHT_KEYWORD),
    ("Image",          "keyword",  ("image", "photo"),                WEIGHT_KEYWORD),
    ("QuickLinks",     "explicit", ("quick link", "quick links", "quicklink", "quicklinks"), WEIGHT_EXPLICIT),
    ("QuickLinks",     "keyword",  ("link",),                         WEIGHT_KEYWORD),
    ("News",           "explicit", ("news feed",),                    WEIGHT_EXPLICIT),
    ("News",           "keyword",  ("news",),                         WEIGHT_KEYWORD),
    ("People",         "explicit", ("team member", "team members"),   WEIGHT_EXPLICIT),
    ("People",         "keyword",  ("people", "members"),             WEIGHT_KEYWORD),
    ("List",           "keyword",  ("list",),                         WEIGHT_KEYWORD),
    ("DocumentLibrary","explicit", ("document library",),             WEIGHT_EXPLICIT),
    ("DocumentLibrary","keyword",  ("library",),                      WEIGHT_KEYWORD),
    ("Events",         "keyword",  ("events", "calendar"),            WEIGHT_KEYWORD),
]


def route_webpart(text: str) -> DetectionResult:
    """Detect the webpart type from a user message.

    Returns:
        ``DetectionResult`` with ``intent`` equal to a canonical webpart
        type string, or ``intent=None`` when no signal is found.
    """
    text_lower = text.lower()
    scores: dict[str, float] = {}
    layers: dict[str, str] = {}
    phrases_hit: dict[str, list[str]] = {}

    for wtype, layer, phrases, weight in _RULES:
        score, matched = score_phrases(text_lower, phrases, weight)
        if score and score > scores.get(wtype, 0.0):
            scores[wtype] = score
            layers[wtype] = layer
            phrases_hit[wtype] = matched

    selected = max(scores, key=scores.get) if scores else None
    log_detection(logger, "routing.webpart", scores, selected)

    if selected:
        return DetectionResult(
            intent=selected,
            score=scores[selected],
            layer=layers.get(selected, ""),
            matched_phrases=phrases_hit.get(selected, []),
        )
    return DetectionResult()
