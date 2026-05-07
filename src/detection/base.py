"""Base types and utilities for the detection package.

Every detector in this package must:
1. Accept a plain ``str`` as input.
2. Return a ``DetectionResult`` with a ``score`` between 0.0 and 1.0.
3. Call ``log_detection`` before returning so scores are observable.

Layer weight constants (used by all detectors for consistency):
    WEIGHT_EXPLICIT   = 0.9  — direct, unambiguous phrase match
    WEIGHT_KEYWORD    = 0.6  — keyword-combination match
    WEIGHT_CONTEXTUAL = 0.3  — soft / inferred signal
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = [
    "DetectionResult",
    "WEIGHT_EXPLICIT",
    "WEIGHT_KEYWORD",
    "WEIGHT_CONTEXTUAL",
    "score_phrases",
    "score_any_token",
    "log_detection",
]

# ── Layer weight constants ───────────────────────────────────────────────────
WEIGHT_EXPLICIT: float = 0.9
WEIGHT_KEYWORD: float = 0.6
WEIGHT_CONTEXTUAL: float = 0.3


@dataclass
class DetectionResult:
    """Result of a single detector run.

    Attributes:
        intent: The detected intent/class name (e.g. ``"page_query"``).
                ``None`` means no detection.
        score:  Confidence score in [0.0, 1.0].
        layer:  Human-readable name of the layer that produced the highest
                contribution (e.g. ``"explicit_phrases"``, ``"keywords"``).
        matched_phrases: Phrases/tokens that contributed to the score.
        conflicts: Dict of competing intents and their scores when overlap
                   resolution was needed.
    """

    intent: Optional[str] = None
    score: float = 0.0
    layer: str = ""
    matched_phrases: List[str] = field(default_factory=list)
    conflicts: Dict[str, float] = field(default_factory=dict)

    # ── Convenience helpers ──────────────────────────────────────────────
    def is_detected(self, threshold: float = 0.05) -> bool:
        """Return True when ``score`` exceeds *threshold*."""
        return self.score >= threshold and self.intent is not None

    def __bool__(self) -> bool:  # noqa: D105
        return self.is_detected()


# ── Scoring utilities ────────────────────────────────────────────────────────

def score_phrases(
    text: str,
    phrases: Any,  # Iterable[str]
    weight: float,
) -> tuple[float, list[str]]:
    """Score *text* against a collection of phrases with the given *weight*.

    Returns:
        ``(score, matched)`` where *score* is the first match contribution
        (``weight``) and *matched* is the list of matching phrases found.
        Score is 0.0 when nothing matches.

    Notes:
        The function returns *weight* as soon as any phrase matches — it does
        NOT accumulate across multiple phrases.  Use separate calls per layer
        if you need additive scoring.
    """
    text_lower = text.lower()
    matched = [p for p in phrases if p in text_lower]
    if matched:
        return weight, matched
    return 0.0, []


def score_any_token(
    tokens: frozenset,
    phrase_set: frozenset,
    weight: float,
) -> tuple[float, list[str]]:
    """Score based on token-level intersection (faster for frozenset lookups).

    Returns:
        ``(score, matched)`` — same contract as :func:`score_phrases`.
    """
    matched = list(tokens & phrase_set)
    if matched:
        return weight, matched
    return 0.0, []


# ── Logging utility ──────────────────────────────────────────────────────────

def log_detection(
    logger: logging.Logger,
    domain: str,
    scores: Dict[str, float],
    selected: Optional[str],
    conflicts: Optional[Dict[str, float]] = None,
) -> None:
    """Emit a structured debug log entry for a detection decision.

    Args:
        logger:    The caller's logger.
        domain:    Detector domain name, e.g. ``"intent"``, ``"validation"``.
        scores:    Mapping of intent → confidence score for all candidates.
        selected:  The intent that was selected (or ``None``).
        conflicts: Optional sub-mapping of intents whose scores were close,
                   indicating a conflict that required explicit resolution.

    Example output::

        [IntentDetection] scores={'page_query': 0.9, 'analyze': 0.6},
            selected='page_query', conflicts=None
    """
    logger.debug(
        "[%sDetection] scores=%s, selected=%s, conflicts=%s",
        domain.title().replace("_", ""),
        scores,
        selected,
        conflicts,
    )
