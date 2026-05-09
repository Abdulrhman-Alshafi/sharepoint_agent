"""Synonym expander — grouped by semantic domain, pure Python.

Migrated and refactored from
``src/infrastructure/services/smart_resource_discovery.py`` ``_SYNONYMS`` dict.

Key changes:
  - Synonyms grouped by semantic domain (task, project, hr, doc, finance, social)
  - ``expand()`` public function; replaces the private ``_expand_with_synonyms()``
  - ``SYNONYMS`` canonical dict for use by new consumers

The infrastructure layer's ``_expand_with_synonyms()`` can import and delegate
to ``expand()`` for zero breaking changes.
"""

from __future__ import annotations

import re
import logging
from typing import Dict, List, Set

logger = logging.getLogger(__name__)

# ── Canonical synonym map, grouped by semantic domain ────────────────────────
SYNONYMS: Dict[str, List[str]] = {
    # ── Task management ──────────────────────────────────────────────────────
    "tasks":        ["task", "todos", "todo", "work items", "workitems",
                     "action items", "actions", "assignments", "tickets", "issues"],
    "task":         ["tasks", "todo", "work item", "action item", "assignment", "ticket"],
    "todos":        ["tasks", "task", "work items", "action items"],
    "issues":       ["tasks", "bugs", "tickets", "problems", "defects"],
    "tickets":      ["tasks", "issues", "requests", "support"],

    # ── Project management ───────────────────────────────────────────────────
    "milestones":   ["milestone", "deliverables", "deliverable", "checkpoints",
                     "goals", "targets"],
    "milestone":    ["milestones", "deliverable", "checkpoint", "goal", "target"],
    "projects":     ["project", "initiatives", "initiative", "programs", "programme"],
    "project":      ["projects", "initiative", "program"],
    "updates":      ["status", "progress", "report", "tracker", "log"],
    "status":       ["updates", "progress", "tracker", "report"],

    # ── HR ───────────────────────────────────────────────────────────────────
    "employees":    ["employee", "staff", "personnel", "team members", "resources", "people"],
    "employee":     ["employees", "staff", "personnel", "people", "team member"],
    "month":        ["monthly", "employeeofmonth", "recognition"],
    "onboarding":   ["onboard", "new hire", "orientation", "induction", "new employee"],
    "policies":     ["policy", "guidelines", "rules", "procedures", "handbook"],
    "hr":           ["human resources", "people", "personnel"],
    "handbook":     ["guide", "manual", "policy", "guidelines"],
    "training":     ["learning", "course", "courses", "education", "development"],

    # ── Document ─────────────────────────────────────────────────────────────
    "files":        ["documents", "docs", "attachments", "uploads", "resources"],
    "documents":    ["files", "docs", "attachments", "reports", "materials"],
    "reports":      ["report", "summaries", "analysis", "findings"],

    # ── Finance ──────────────────────────────────────────────────────────────
    "budget":       ["budgets", "finance", "financial", "spend", "costs", "expenses"],
    "kpi":          ["kpis", "metrics", "performance", "indicators", "targets", "goals"],
    "kpis":         ["kpi", "metrics", "performance indicators", "goals", "targets"],

    # ── Recognition / social ─────────────────────────────────────────────────
    "kudos":        ["kudo", "recognition", "shoutout", "shoutouts", "praise",
                     "award", "awards", "appreciation"],
    "kudo":         ["kudos", "recognition", "shoutout", "praise", "award", "appreciation"],
    "recognition":  ["kudos", "kudo", "shoutout", "praise", "award", "appreciation", "employeeofmonth", "monthly award", "employee of the month"],
    "employeeofmonth": ["employee", "month", "recognition", "award", "kudos", "monthly", "star", "best employee"],
    "award":        ["awards", "recognition", "kudos", "employee of the month", "prize", "achievement"],
    "awards":       ["award", "recognition", "kudos", "employee of the month", "prizes", "achievements"],
    "kudosposts":   ["kudos", "gave", "give", "given", "sent", "received",
                     "recognition", "shoutout"],
    "gave":         ["kudosposts", "sent", "submitted", "posted"],
    "give":         ["kudosposts", "send", "post"],
    "given":        ["kudosposts", "sent", "posted"],
    "kudoslikes":   ["like", "liked", "likes", "reaction", "reactions", "thumbs"],
    "liked":        ["kudoslikes", "reaction", "thumbs"],
}


def _tokenise(text: str) -> Set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def expand(term: str) -> List[str]:
    """Return synonym expansions for *term* (exact key lookup).

    Returns:
        List of synonym strings, empty if no synonyms found.
    """
    return list(SYNONYMS.get(term.lower(), []))


def expand_tokens(tokens: Set[str]) -> Set[str]:
    """Return *tokens* plus all their synonym tokens.

    Suitable as a drop-in replacement for the infrastructure layer's
    private ``_expand_with_synonyms(tokens)``.
    """
    expanded: Set[str] = set(tokens)
    for token in tokens:
        for synonym in SYNONYMS.get(token, []):
            expanded |= _tokenise(synonym)
    return expanded
