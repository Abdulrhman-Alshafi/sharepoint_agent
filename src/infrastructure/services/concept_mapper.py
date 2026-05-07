"""ConceptMapper — Human Intent Translation Layer (HITL).

Maps vague natural-language queries to business concepts and suggests which
SharePoint resource type the user likely wants.  No AI calls, no I/O.

Designed to be instantiated on demand (lightweight, stateless except for the
optional custom-ontology merge added in Phase 4).
"""

from __future__ import annotations

import re
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ConceptMappingResult:
    original_query  : str
    concepts        : List[str]       = field(default_factory=list)
    expanded_tokens : Set[str]        = field(default_factory=set)
    rewritten_query : str             = ""
    confidence      : float           = 0.5
    is_vague        : bool            = False
    resource_hint   : Optional[str]   = None  # "page" | "list" | "library" | "site" | None


# ─────────────────────────────────────────────────────────────────────────────
# Static ontology
# Maps lowercase trigger phrases to (concepts, resource_hint).
# Ordered from most-specific to least-specific so the first match wins.
# ─────────────────────────────────────────────────────────────────────────────

# _ONTOLOGY is now sourced from the detection package; kept as a dict for
# backward compatibility with any code that iterates it directly.
from src.detection.semantic.concept_mapper import ONTOLOGY as _DETECTION_ONTOLOGY

_ONTOLOGY: Dict[str, tuple] = {
    rule.phrase: (list(rule.concepts), rule.resource_type)
    for rule in _DETECTION_ONTOLOGY
}

# Words/phrases that suggest the hint is PAGE regardless of other signals
_PAGE_SIGNAL_CONCEPTS = {
    "announcements", "news", "events", "schedule", "welcome",
    "highlights", "spotlight", "newsletter", "launches", "hero",
    "banner", "updates", "calendar",
}

# Words that mark a query as vague (lower confidence)
_VAGUE_PRONOUNS = {"that", "it", "thing", "stuff", "those", "these", "them"}


def _tokenise(text: str) -> Set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


# ─────────────────────────────────────────────────────────────────────────────
# ConceptMapper
# ─────────────────────────────────────────────────────────────────────────────

class ConceptMapper:
    """Translate a raw user query into concepts + resource_hint.

    Phase 4 may inject a ``custom_ontology`` dict at class level — it is
    merged lazily on first use.
    """

    # Populated in Phase 4 by OntologyExpander; format same as _ONTOLOGY
    _custom_ontology: Dict[str, tuple] = {}
    _custom_loaded_at: float = 0.0
    _CUSTOM_TTL: float = 600.0  # reload every 10 minutes

    def map_query(
        self,
        query: str,
        learned_concepts: Optional[List[str]] = None,
    ) -> ConceptMappingResult:
        """Map a raw query to a ConceptMappingResult.

        Args:
            query:            Raw user message.
            learned_concepts: Optional list of concept strings returned by
                              ConceptMemory.lookup() — merged with static hits.
        """
        q_lower = query.lower().strip()
        q_tokens = _tokenise(q_lower)

        # ── 1. Check custom ontology (Phase 4) ────────────────────────
        merged_ontology = {**_ONTOLOGY, **self.__class__._custom_ontology}

        # ── 2. Find matching phrases (longest match wins) ─────────────
        concepts: List[str] = []
        resource_hint: Optional[str] = None
        matched_phrases: int = 0

        # Sort by phrase length descending so "upcoming events" beats "events"
        for phrase, (phrase_concepts, hint) in sorted(
            merged_ontology.items(), key=lambda kv: len(kv[0]), reverse=True
        ):
            if phrase in q_lower:
                if not concepts:
                    # First (longest) match sets the hint
                    resource_hint = hint
                concepts.extend(c for c in phrase_concepts if c not in concepts)
                matched_phrases += 1
                if matched_phrases >= 2:
                    break  # cap at 2 phrase matches

        # ── 3. Merge learned concepts ─────────────────────────────────
        if learned_concepts:
            concepts.extend(c for c in learned_concepts if c not in concepts)

        # ── 4. Infer resource_hint from concepts when not set ─────────
        if resource_hint is None and concepts:
            concept_set = set(concepts)
            if concept_set & _PAGE_SIGNAL_CONCEPTS:
                resource_hint = "page"

        # ── 5. Build expanded_tokens ──────────────────────────────────
        expanded_tokens: Set[str] = set(q_tokens)
        for concept in concepts:
            expanded_tokens |= _tokenise(concept)

        # ── 6. Rewrite query ──────────────────────────────────────────
        if concepts:
            rewritten_query = q_lower + " " + " ".join(concepts)
        else:
            rewritten_query = q_lower

        # ── 7. Confidence scoring ─────────────────────────────────────
        confidence = 0.5
        if matched_phrases >= 1:
            confidence += 0.2
        if matched_phrases >= 2:
            confidence += 0.2  # capped at +0.4 total

        word_count = len(q_lower.split())
        if word_count < 3 and matched_phrases == 0:
            confidence -= 0.15

        # Vague pronoun penalty
        has_vague = bool(q_tokens & _VAGUE_PRONOUNS)
        # Only penalise if there is no meaningful topic noun alongside the pronoun
        meaningful_tokens = q_tokens - _VAGUE_PRONOUNS - {"a", "the", "is", "are", "was"}
        if has_vague and not meaningful_tokens:
            confidence -= 0.2

        confidence = max(0.0, min(1.0, confidence))
        is_vague = confidence < 0.4 or (has_vague and not meaningful_tokens)

        return ConceptMappingResult(
            original_query=query,
            concepts=concepts,
            expanded_tokens=expanded_tokens,
            rewritten_query=rewritten_query,
            confidence=confidence,
            is_vague=is_vague,
            resource_hint=resource_hint,
        )

    @classmethod
    def load_custom_ontology(cls, custom: Dict[str, tuple]) -> None:
        """Called by OntologyExpander (Phase 4) to inject learned mappings."""
        cls._custom_ontology = custom
        cls._custom_loaded_at = time.time()
        logger.info("ConceptMapper: loaded %d custom ontology entries", len(custom))
