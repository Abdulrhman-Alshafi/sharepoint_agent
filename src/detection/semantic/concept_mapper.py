"""Concept mapper — structured ontology with ConceptRule objects, pure Python.

Migrated and refactored from
``src/infrastructure/services/concept_mapper.py`` _ONTOLOGY flat dict.

Key changes:
  - Each entry is a ``ConceptRule`` dataclass (typed, IDE-friendly)
  - Resource types use string literals grouped by category
  - ``map_concepts()`` is a free function; no class instantiation required
  - Confidence is scored (0.0–1.0) based on match quality

The original ``ConceptMapper`` class still uses the ``_ONTOLOGY`` dict in
the infrastructure layer — the infrastructure layer's class continues to work
unchanged.  This module is the canonical source of truth for the ontology data
and the free-function API used by new consumers.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConceptRule:
    """A single ontology mapping rule.

    Attributes:
        phrase:       Lowercase trigger phrase (longest-match wins).
        concepts:     Expanded concept tokens for search / rewrite.
        resource_type: Suggested SharePoint resource type hint.
        weight:       Optional override confidence weight (0.0–1.0).
    """
    phrase: str
    concepts: Tuple[str, ...]
    resource_type: Optional[str] = None  # "page" | "list" | "library" | "site" | None
    weight: float = 0.9


# ── Ontology rules (ordered from most-specific to least-specific) ────────────
ONTOLOGY: Tuple[ConceptRule, ...] = (
    # ── Page / intranet content ──────────────────────────────────────────────
    ConceptRule("what's new",             ("announcements", "updates", "news"),        "page"),
    ConceptRule("whats new",              ("announcements", "updates", "news"),        "page"),
    ConceptRule("what is new",            ("announcements", "updates", "news"),        "page"),
    ConceptRule("what's happening",       ("events", "announcements", "updates"),      "page"),
    ConceptRule("whats happening",        ("events", "announcements", "updates"),      "page"),
    ConceptRule("what is happening",      ("events", "announcements", "updates"),      "page"),
    ConceptRule("latest news",            ("news", "announcements", "recent"),         "page"),
    ConceptRule("recent news",            ("news", "announcements", "recent"),         "page"),
    ConceptRule("upcoming events",        ("events", "calendar", "schedule"),          "page"),
    ConceptRule("scheduled events",       ("events", "calendar", "schedule"),          "page"),
    ConceptRule("company news",           ("news", "announcements", "company"),        "page"),
    ConceptRule("team spotlight",         ("team", "spotlight", "people", "highlight"),"page"),
    ConceptRule("recent launches",        ("launches", "announcements", "releases"),   "page"),
    ConceptRule("team news",              ("news", "team", "updates"),                 "page"),
    ConceptRule("intranet news",          ("news", "announcements", "updates"),        "page"),
    ConceptRule("what's on the intranet", ("news", "events", "updates"),               "page"),
    ConceptRule("whats on the intranet",  ("news", "events", "updates"),               "page"),
    ConceptRule("deadlines",              ("events", "calendar", "due date"),          "page"),
    ConceptRule("welcome message",        ("welcome", "introduction", "about"),        "page"),
    ConceptRule("hero banner",            ("hero", "banner", "highlights"),            "page"),
    ConceptRule("quick links",            ("links", "shortcuts", "navigation"),        "page"),
    ConceptRule("highlights",             ("highlights", "featured", "announcements"), "page"),
    ConceptRule("newsletter",             ("newsletter", "news", "updates"),           "page"),

    # ── Library / document content ───────────────────────────────────────────
    ConceptRule("hr stuff",        ("hr", "policies", "onboarding", "employees"),  "library"),
    ConceptRule("hr docs",         ("hr", "policies", "documents", "employees"),   "library"),
    ConceptRule("hr documents",    ("hr", "policies", "documents", "employees"),   "library"),
    ConceptRule("onboarding info", ("onboarding", "new hire", "orientation"),       "library"),
    ConceptRule("onboarding docs", ("onboarding", "orientation", "documents"),      "library"),
    ConceptRule("training materials", ("training", "learning", "course"),           "library"),
    ConceptRule("training docs",   ("training", "learning", "documents"),           "library"),
    ConceptRule("policies",        ("policy", "guidelines", "procedures"),          "library"),
    ConceptRule("company policies",("policy", "guidelines", "handbook"),            "library"),
    ConceptRule("employee handbook",("handbook", "policy", "employees"),            "library"),
    ConceptRule("compliance docs", ("compliance", "policy", "regulations"),         "library"),
    ConceptRule("legal documents", ("legal", "contracts", "agreements"),            "library"),

    # ── List content ─────────────────────────────────────────────────────────
    ConceptRule("tasks",           ("tasks", "work items", "assignments"),           "list"),
    ConceptRule("my tasks",        ("tasks", "work items", "assignments"),           "list"),
    ConceptRule("open tasks",      ("tasks", "work items", "assignments"),           "list"),
    ConceptRule("issues",          ("issues", "bugs", "tickets", "problems"),        "list"),
    ConceptRule("open issues",     ("issues", "bugs", "tickets", "problems"),        "list"),
    ConceptRule("milestones",      ("milestones", "deliverables", "checkpoints"),    "list"),
    ConceptRule("project milestones",("milestones", "deliverables", "project"),      "list"),
    ConceptRule("budget",          ("budget", "finance", "costs", "expenses"),       "list"),
    ConceptRule("who works here",  ("employees", "staff", "team members"),           "list"),
    ConceptRule("staff list",      ("employees", "staff", "team members"),           "list"),
    ConceptRule("team members",    ("team", "staff", "employees", "members"),        "list"),
    ConceptRule("requests",        ("requests", "tickets", "issues", "support"),     "list"),
    ConceptRule("support tickets", ("tickets", "support", "issues", "requests"),     "list"),
    ConceptRule("action items",    ("tasks", "actions", "work items"),               "list"),
    ConceptRule("kudos",           ("kudos", "recognition", "praise", "awards"),     "list"),
    ConceptRule("kudo",            ("kudos", "recognition", "praise"),               "list"),
    ConceptRule("recognition",     ("recognition", "kudos", "praise", "awards"),     "list"),
    ConceptRule("kudos i gave",    ("kudos", "recognition", "praise"),               "list"),
    ConceptRule("kudos i received",("kudos", "recognition", "praise"),               "list"),
    ConceptRule("kudos that i gave",   ("kudos", "recognition", "praise"),           "list"),
    ConceptRule("kudos that i received",("kudos", "recognition", "praise"),          "list"),

    # ── Site structure ────────────────────────────────────────────────────────
    ConceptRule("org structure",   ("sites", "structure", "hierarchy", "organization"), "site"),
    ConceptRule("site structure",  ("sites", "structure", "hierarchy"),               "site"),

    # ── Vague pronouns — no concepts, no hint ────────────────────────────────
    ConceptRule("that thing", (), None, weight=0.1),
    ConceptRule("the thing",  (), None, weight=0.1),
    ConceptRule("it",         (), None, weight=0.1),
    ConceptRule("that stuff", (), None, weight=0.1),
    ConceptRule("some stuff", (), None, weight=0.1),
)

# Lookup dict: phrase → rule  (longest-match handled via sorted iteration)
_PHRASE_TO_RULE: Dict[str, ConceptRule] = {r.phrase: r for r in ONTOLOGY}

_PAGE_SIGNAL_CONCEPTS: frozenset[str] = frozenset({
    "announcements", "news", "events", "schedule", "welcome",
    "highlights", "spotlight", "newsletter", "launches", "hero",
    "banner", "updates", "calendar",
})

_VAGUE_PRONOUNS: frozenset[str] = frozenset({"that", "it", "thing", "stuff", "those", "these", "them"})


def _tokenise(text: str) -> Set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def map_concepts(
    query: str,
    learned_concepts: Optional[List[str]] = None,
) -> Tuple[List[str], Optional[str], float, Set[str]]:
    """Map *query* to concepts, resource_hint, confidence, and expanded tokens.

    Args:
        query:            Raw user message.
        learned_concepts: Optional pre-learned concept strings to merge.

    Returns:
        ``(concepts, resource_hint, confidence, expanded_tokens)``
    """
    q_lower = query.lower().strip()
    q_tokens = _tokenise(q_lower)

    concepts: List[str] = []
    resource_hint: Optional[str] = None
    confidence: float = 0.5
    matched: int = 0

    # Longest-match first
    for rule in sorted(ONTOLOGY, key=lambda r: len(r.phrase), reverse=True):
        if rule.phrase in q_lower:
            if not concepts:
                resource_hint = rule.resource_type
                confidence = rule.weight
            for c in rule.concepts:
                if c not in concepts:
                    concepts.append(c)
            matched += 1
            if matched >= 2:
                break

    if learned_concepts:
        for c in learned_concepts:
            if c not in concepts:
                concepts.append(c)

    if resource_hint is None and concepts:
        if set(concepts) & _PAGE_SIGNAL_CONCEPTS:
            resource_hint = "page"

    # Is vague?
    if q_tokens & _VAGUE_PRONOUNS and not concepts:
        confidence = 0.1

    expanded_tokens: Set[str] = set(q_tokens)
    for concept in concepts:
        expanded_tokens |= _tokenise(concept)

    logger.debug(
        "[SemanticConceptMapper] query=%r concepts=%s hint=%s confidence=%.2f",
        query, concepts, resource_hint, confidence,
    )
    return concepts, resource_hint, confidence, expanded_tokens
