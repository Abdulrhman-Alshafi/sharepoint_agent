"""Template classification — scoring-based, pure Python.

Matches a user message against a list of SiteTemplates using their
keyword lists, replacing the flat `any(keyword in low for keyword in
template.keywords)` pattern with a scored approach.

Layers:
  1 — Keyword hit count → score = hits / len(keywords), capped at 1.0
  2 — When tied, the template with more matching keywords wins

Returns the best-matching template or None.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, List, Optional

from src.detection.base import log_detection

if TYPE_CHECKING:
    pass  # SiteTemplate imported lazily

logger = logging.getLogger(__name__)


def classify_template(message: str, templates: List[Any]) -> Optional[Any]:
    """Return the best-matching template for *message*, or ``None``.

    Args:
        message:   The user's message.
        templates: List of ``SiteTemplate``-like objects with a ``.name``
                   attribute and a ``.keywords`` list of strings.

    Returns:
        The ``SiteTemplate`` with the highest keyword overlap score,
        or ``None`` when no template matches.
    """
    low = message.lower()
    scores: dict[str, float] = {}
    hits_map: dict[str, int] = {}
    template_by_name: dict[str, Any] = {}

    for tmpl in templates:
        keywords = getattr(tmpl, "keywords", [])
        if not keywords:
            continue
        hits = sum(1 for kw in keywords if kw in low)
        if hits:
            score = hits / len(keywords)
            scores[tmpl.name] = score
            hits_map[tmpl.name] = hits
            template_by_name[tmpl.name] = tmpl

    if not scores:
        log_detection(logger, "classification.template", {}, None)
        return None

    # Tiebreak: more absolute keyword hits wins
    selected_name = max(
        scores,
        key=lambda n: (scores[n], hits_map[n]),
    )

    log_detection(logger, "classification.template", scores, selected_name)
    return template_by_name[selected_name]
