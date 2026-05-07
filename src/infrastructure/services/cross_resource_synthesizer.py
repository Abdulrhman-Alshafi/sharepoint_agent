"""CrossResourceSynthesizer — merges multi-hop sub-answers into one response.

Token-cost focus:
  * ONE AI call for the entire compound question, regardless of how many
    sub-questions were answered.
  * Each sub-answer is pre-truncated to _MAX_SUB_ANSWER_CHARS to prevent
    LLM context explosion.
  * The synthesizer prompt is tightly scoped — no redundant system preamble.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

_MAX_SUB_ANSWER_CHARS = 1200  # per sub-answer before truncation

_SYNTHESIS_PROMPT = """\
You are a helpful SharePoint assistant. Below are the answers to several \
sub-questions that together answer a compound user request. \
Combine them into a single clear, concise response. \
Do NOT repeat the sub-questions. \
Do NOT add information not present in the sub-answers below.

Sub-answers:
{sub_answers_block}

Original user question: {original_question}

Your combined answer:"""


class CrossResourceSynthesizer:
    """Combines multiple DataQueryResult answers into one unified AI response.

    Usage::

        synth = CrossResourceSynthesizer(client=self.client, model=self.model)
        result = await synth.synthesize(multi_hop_result, original_question)
    """

    def __init__(self, client: Any, model: Optional[str] = None) -> None:
        self._client = client
        self._model = model

    async def synthesize(
        self,
        multi_hop_result: Any,  # MultiHopResult
        original_question: str,
    ) -> str:
        """Merge sub-answers with a single AI call.  Returns plain answer string."""
        from src.infrastructure.schemas.query_schemas import DataQueryResponseModel

        sub_answers = getattr(multi_hop_result, "sub_answers", [])
        if not sub_answers:
            return "I couldn't gather enough information to answer your question."

        # Build compact sub-answer block
        lines = []
        for i, item in enumerate(sub_answers, 1):
            sq = item.get("sub_question", f"Sub-question {i}")
            ans = (item.get("answer") or "No answer available.")[:_MAX_SUB_ANSWER_CHARS]
            if len(item.get("answer", "")) > _MAX_SUB_ANSWER_CHARS:
                ans += " ...[truncated]"
            lines.append(f"[{i}] {sq}\n→ {ans}")
        sub_answers_block = "\n\n".join(lines)

        prompt = _SYNTHESIS_PROMPT.format(
            sub_answers_block=sub_answers_block,
            original_question=original_question,
        )

        try:
            kwargs = {
                "messages": [{"role": "user", "content": prompt}],
                "response_model": DataQueryResponseModel,
            }
            if self._model:
                kwargs["model"] = self._model
            response = self._client.chat.completions.create(**kwargs)
            return response.answer
        except Exception as exc:
            logger.error("CrossResourceSynthesizer AI call failed: %s", exc)
            # Graceful degradation: join sub-answers as bullet list
            bullets = "\n".join(
                f"- {item.get('answer', '')}" for item in sub_answers if item.get("answer")
            )
            return bullets or "I found some relevant information but could not combine it."
