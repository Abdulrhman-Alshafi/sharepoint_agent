"""Page-purpose classification — scoring-based, pure Python.

Keyword-based fallback classifier for page purpose detection.
Used when LLM is unavailable or as a first-pass signal.

Layers (per purpose):
  - Each keyword that appears in the combined title+description contributes
    to that purpose's score.
  - Score normalised to [0.0, 1.0] by dividing by the keyword count per
    category (capped at 1.0).

Returns the ``PagePurpose`` with the highest score and its confidence.
"""

from __future__ import annotations

import logging
from typing import Tuple

from src.detection.base import log_detection

logger = logging.getLogger(__name__)

# Import PagePurpose lazily to avoid circular imports at module load time.
# Callers always have the domain package available.
try:
    from src.domain.value_objects.page_purpose import PagePurpose
    _PAGE_PURPOSE_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PAGE_PURPOSE_AVAILABLE = False

# ── Keyword groups per purpose ───────────────────────────────────────────────
# Layer 1: primary explicit keywords (weight ~0.9 per hit normalised to list len)
_KEYWORD_MAP: dict[str, tuple[str, ...]] = {
    "Home":          ("home", "welcome", "landing", "overview"),
    "Team":          ("team", "members", "staff", "group", "department"),
    "News":          ("news", "announcement", "update", "blog", "article", "press"),
    "Documentation": ("guide", "how-to", "documentation", "document", "help", "tutorial", "steps"),
    "ProjectStatus": ("project", "status", "progress", "update", "roadmap", "milestone"),
    "ResourceLibrary":("resource", "library", "download", "template", "guide", "asset"),
    "FAQ":           ("faq", "frequently", "question", "qa", "q&a", "answer", "common"),
    "Announcement":  ("announcement", "alert", "important", "urgent", "notice"),
}


def classify_page_purpose(title: str, description: str = "") -> Tuple[str, float]:
    """Classify page purpose from title and description using keyword scoring.

    This is the keyword-based fallback (no LLM required).

    Args:
        title:       Page title.
        description: Optional page description.

    Returns:
        ``(purpose_value, confidence)`` where *purpose_value* is the string
        value of the winning :class:`~src.domain.value_objects.page_purpose.PagePurpose`
        and *confidence* is in [0.0, 1.0].
    """
    combined = f"{title} {description}".lower()
    scores: dict[str, float] = {}

    for purpose_key, keywords in _KEYWORD_MAP.items():
        hits = sum(1 for kw in keywords if kw in combined)
        if hits:
            scores[purpose_key] = min(hits / len(keywords), 1.0)

    if not scores:
        log_detection(logger, "classification.page_purpose", {}, "Other")
        return "Other", 0.3

    selected = max(scores, key=scores.get)
    confidence = min(scores[selected], 1.0)

    log_detection(logger, "classification.page_purpose", scores, selected)
    return selected, confidence


def classify_page_purpose_enum(
    title: str,
    description: str = "",
) -> "Tuple[PagePurpose, float]":  # noqa: F821
    """Same as :func:`classify_page_purpose` but returns the enum value.

    Requires :mod:`src.domain.value_objects.page_purpose` to be importable.
    """
    from src.domain.value_objects.page_purpose import PagePurpose

    _str_to_enum = {p.value: p for p in PagePurpose}
    purpose_str, confidence = classify_page_purpose(title, description)
    purpose = _str_to_enum.get(purpose_str, PagePurpose.OTHER)
    return purpose, confidence
