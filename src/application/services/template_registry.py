"""Template registry service.

Provides keyword-based template matching so handlers can detect when a user
wants a full pre-built workspace rather than a single bare site.
"""

from __future__ import annotations

from typing import List, Optional

from src.domain.entities.templates import BUILT_IN_TEMPLATES, SiteTemplate
from src.detection.classification.template_classifier import classify_template


def match_template(message: str) -> Optional[SiteTemplate]:
    """Return the best-matching template for *message*, or ``None``.

    Delegates to the scored :func:`~src.detection.classification.template_classifier.classify_template`
    so overlapping keyword sets are resolved by score rather than list order.
    """
    return classify_template(message, BUILT_IN_TEMPLATES)


def list_templates() -> List[SiteTemplate]:
    """Return all registered site templates."""
    return list(BUILT_IN_TEMPLATES)


def get_template(name: str) -> Optional[SiteTemplate]:
    """Return a template by exact name (case-insensitive), or ``None``."""
    low = name.lower()
    for template in BUILT_IN_TEMPLATES:
        if template.name.lower() == low:
            return template
    return None
