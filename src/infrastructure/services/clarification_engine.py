"""ClarificationEngine — decides when and what to ask the user.

Token-cost focus:
  * No AI calls — all logic is deterministic.
  * Triggers only when ConceptMapper confidence < 0.50 OR when multiple
    resource types match equally, preventing the LLM from guessing wrong.
  * A precise clarification saves tokens by avoiding a full retrieval that
    returns the wrong resource type.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ClarificationResult:
    needs_clarification: bool
    question: str = ""
    reason: str = ""   # debug / logging only


class ClarificationEngine:
    """Deterministic clarification logic — zero AI calls.

    Usage::

        engine = ClarificationEngine()
        result = engine.evaluate(mapping, candidates)
        if result.needs_clarification:
            return ChatResponse(..., needs_clarification=True,
                               clarification_question=result.question)
    """

    # Minimum confidence below which we ask for clarification
    _LOW_CONFIDENCE_THRESHOLD = 0.50

    # If the top-2 candidates have scores within this band, we call it a tie
    _TIE_BAND = 0.02

    def evaluate(
        self,
        mapping: Any,          # ConceptMappingResult — avoid hard import cycle
        candidates: List[Any], # List[ResourceCandidate]
    ) -> ClarificationResult:
        """Return a ClarificationResult.

        Decision order:
        1. If mapping.confidence < threshold → low-confidence question.
        2. If top candidates span multiple resource types AND are tied → ask.
        3. Otherwise → no clarification needed.
        """
        confidence = getattr(mapping, "confidence", 1.0)
        concepts = getattr(mapping, "concepts", [])
        is_vague = getattr(mapping, "is_vague", False)

        # ── Rule 1: low confidence + vague query ──────────────────────────────
        if confidence < self._LOW_CONFIDENCE_THRESHOLD and is_vague:
            topic = concepts[0] if concepts else "this"
            return ClarificationResult(
                needs_clarification=True,
                question=(
                    f"I want to make sure I find the right information. "
                    f"Are you looking for a **page**, a **list**, or a **library** "
                    f"related to *{topic}*?"
                ),
                reason="low_confidence_vague",
            )

        # ── Rule 2: multi-type tie in top candidates ──────────────────────────
        if len(candidates) >= 2:
            types = [getattr(c, "resource_type", None) for c in candidates[:3]]
            scores = [getattr(c, "relevance_score", 0.0) for c in candidates[:3]]
            unique_types = set(t for t in types if t)
            top_score = scores[0] if scores else 0.0
            second_score = scores[1] if len(scores) > 1 else 0.0
            is_tie = (top_score - second_score) <= self._TIE_BAND

            if len(unique_types) > 1 and is_tie:
                type_labels = " or a ".join(
                    f"**{t}**" for t in sorted(unique_types)
                )
                topic_phrase = (
                    f" about *{', '.join(concepts[:2])}*" if concepts else ""
                )
                return ClarificationResult(
                    needs_clarification=True,
                    question=(
                        f"I found several matching resources{topic_phrase}. "
                        f"Are you looking for a {type_labels}?"
                    ),
                    reason="multi_type_tie",
                )

        # ── Rule 3: multiple pages match equally ──────────────────────────────
        if len(candidates) >= 2:
            page_candidates = [
                c for c in candidates[:4]
                if getattr(c, "resource_type", None) == "page"
            ]
            if len(page_candidates) >= 2:
                scores = [getattr(c, "relevance_score", 0.0) for c in page_candidates]
                if scores[0] - scores[1] <= self._TIE_BAND and scores[0] < 0.6:
                    titles = [getattr(c, "title", "") for c in page_candidates[:3]]
                    title_list = ", ".join(f"*{t}*" for t in titles)
                    return ClarificationResult(
                        needs_clarification=True,
                        question=(
                            f"I found several pages that might match: {title_list}. "
                            f"Which one are you interested in?"
                        ),
                        reason="multi_page_tie",
                    )

        return ClarificationResult(needs_clarification=False)

    def should_clarify(
        self,
        mapping: Any,
        candidates: List[Any],
    ) -> bool:
        """Convenience wrapper — True if clarification is recommended."""
        return self.evaluate(mapping, candidates).needs_clarification

    def build_question(
        self,
        mapping: Any,
        candidates: List[Any],
    ) -> str:
        """Return the clarification question string, or '' if not needed."""
        result = self.evaluate(mapping, candidates)
        return result.question if result.needs_clarification else ""
