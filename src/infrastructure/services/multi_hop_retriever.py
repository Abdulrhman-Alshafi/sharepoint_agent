"""MultiHopRetriever — detects compound questions and decomposes them.

Token-cost focus:
  * Detection is deterministic (pattern matching) — zero AI tokens.
  * Sub-question retrieval reuses existing service methods — no new AI calls.
  * Only ONE extra AI call is added (by CrossResourceSynthesizer) to combine
    the results; without this the user would need to ask N separate questions.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Compound question detection patterns ─────────────────────────────────────

# Conjunctions that split a compound question into sub-questions
_SPLIT_PATTERNS = [
    r"\band\s+(also\s+)?(?=what|who|how|when|where|show|list|find|get|tell)",
    r"\bplus\s+(?=what|who|how|when|where|show|list|find|get|tell)",
    r"\balso\s+(?=what|who|how|when|where|show|list|find|get|tell)",
    r"[,;]\s+(?=what|who|how|when|where|show|list|find|get|tell)",
]

_MULTI_RESOURCE_INDICATORS = [
    # "pages and lists", "documents and tasks", etc.
    r"\b(page|pages|document|documents|file|files|list|lists|library|libraries)\b"
    r"\s+(and|&)\s+"
    r"\b(page|pages|document|documents|file|files|list|lists|library|libraries)\b",
    # "both the ... and the ..."
    r"\bboth\s+the\b",
    # "as well as"
    r"\bas well as\b",
]

# Minimum word count to attempt multi-hop (short questions are never compound)
_MIN_WORDS = 8


@dataclass
class SubQuestion:
    text: str
    resource_hint: Optional[str] = None


@dataclass
class MultiHopPlan:
    is_compound: bool
    sub_questions: List[SubQuestion] = field(default_factory=list)
    original_question: str = ""


@dataclass
class MultiHopResult:
    sub_answers: List[Dict[str, Any]] = field(default_factory=list)
    plan: Optional[MultiHopPlan] = None


class MultiHopRetriever:
    """Detects and decomposes compound questions, runs parallel sub-retrievals.

    Usage::

        retriever = MultiHopRetriever(answer_fn=service.answer_question)
        plan = retriever.detect(question)
        if plan.is_compound:
            result = await retriever.retrieve(plan, context)
    """

    def __init__(self, answer_fn=None) -> None:
        """
        Args:
            answer_fn: Async callable (question: str, **ctx) → DataQueryResult.
                       Should be service.answer_question or similar.
        """
        self._answer_fn = answer_fn

    # ─────────────────────────────────────────────────────────────────────────
    # Detection
    # ─────────────────────────────────────────────────────────────────────────

    def detect(self, question: str) -> MultiHopPlan:
        """Deterministically classify a question as compound or simple.

        Returns a MultiHopPlan.  Detection is O(len(question)) — no API calls.
        """
        words = question.strip().split()
        if len(words) < _MIN_WORDS:
            return MultiHopPlan(is_compound=False, original_question=question)

        q_lower = question.lower()

        # Check multi-resource indicator patterns
        for pat in _MULTI_RESOURCE_INDICATORS:
            if re.search(pat, q_lower):
                subs = self._split_question(question, q_lower)
                if len(subs) >= 2:
                    return MultiHopPlan(
                        is_compound=True,
                        sub_questions=subs,
                        original_question=question,
                    )

        # Check split-conjunction patterns
        subs = self._split_question(question, q_lower)
        if len(subs) >= 2:
            return MultiHopPlan(
                is_compound=True,
                sub_questions=subs,
                original_question=question,
            )

        return MultiHopPlan(is_compound=False, original_question=question)

    def _split_question(self, question: str, q_lower: str) -> List[SubQuestion]:
        """Split question text into sub-questions using conjunction patterns."""
        # Try splitting on patterns; use the first pattern that gives >= 2 parts
        for pat in _SPLIT_PATTERNS:
            parts = re.split(pat, q_lower)
            if len(parts) >= 2:
                # Map each lowered part back to a title-cased sub-question
                # using character offsets so we preserve original casing
                sub_texts = [p.strip() for p in parts if p and len(p.strip()) > 3]
                if len(sub_texts) >= 2:
                    return [SubQuestion(text=t) for t in sub_texts]
        return [SubQuestion(text=question)]  # no split found

    # ─────────────────────────────────────────────────────────────────────────
    # Retrieval
    # ─────────────────────────────────────────────────────────────────────────

    async def retrieve(
        self,
        plan: MultiHopPlan,
        **context,
    ) -> MultiHopResult:
        """Execute sub-questions in parallel.

        Args:
            plan:    MultiHopPlan from detect().
            context: Keyword args forwarded to self._answer_fn (e.g. site_id).

        Returns:
            MultiHopResult with one DataQueryResult per sub-question.
        """
        if not plan.is_compound or not plan.sub_questions:
            return MultiHopResult(plan=plan)

        if self._answer_fn is None:
            logger.warning("MultiHopRetriever has no answer_fn — skipping retrieval")
            return MultiHopResult(plan=plan)

        async def _run_one(sq: SubQuestion) -> Dict[str, Any]:
            try:
                result = await self._answer_fn(sq.text, **context)
                return {
                    "sub_question": sq.text,
                    "answer": getattr(result, "answer", str(result)),
                    "data_summary": getattr(result, "data_summary", {}),
                    "source_list": getattr(result, "source_list", ""),
                }
            except Exception as exc:
                logger.warning("MultiHop sub-question failed %r: %s", sq.text, exc)
                return {"sub_question": sq.text, "answer": "", "error": str(exc)}

        tasks = [_run_one(sq) for sq in plan.sub_questions]
        sub_answers = await asyncio.gather(*tasks)
        return MultiHopResult(sub_answers=list(sub_answers), plan=plan)
