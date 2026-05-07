"""Duplicate-name resolver for cross-site resource discovery.

When the same resource name (list, library, page, …) is found in more
than one site, the agent must NOT silently pick one.  This module
provides utilities to detect those collisions and generate the
clarification prompt that is shown to the user.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.domain.value_objects.resource_candidate import ResourceCandidate


@dataclass
class DuplicateGroup:
    """A group of candidates that share the same normalised title."""

    normalised_title: str
    candidates: List[ResourceCandidate] = field(default_factory=list)

    @property
    def is_duplicate(self) -> bool:
        """True when the name exists in more than one distinct site."""
        site_ids = {c.site_id for c in self.candidates}
        return len(site_ids) > 1


class DuplicateNameResolver:
    """Detects cross-site name collisions and produces clarification prompts.

    Usage::

        resolver = DuplicateNameResolver()
        duplicates = resolver.find_duplicates(candidates)
        if duplicates:
            prompt = resolver.build_clarification_prompt(duplicates[0])
            return ChatResponse(reply=prompt, requires_input=True)
    """

    # ─────────────────────────────────────────────────────────────────
    # Detection
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _normalise(title: str) -> str:
        """Lower-case and strip whitespace for comparison."""
        return title.lower().strip()

    def find_duplicates(
        self,
        candidates: List[ResourceCandidate],
        threshold: int = 1,
    ) -> List[DuplicateGroup]:
        """Return groups of candidates whose name appears in more than
        ``threshold`` distinct sites.

        Args:
            candidates:  Full list of discovered ResourceCandidates.
            threshold:   Min number of *different* sites that must share a
                         name before it is flagged (default: 1 → flag any
                         cross-site collision).

        Returns:
            List of :class:`DuplicateGroup`, sorted by normalised title.
            Empty list when no conflicts exist.
        """
        bucket: Dict[str, List[ResourceCandidate]] = defaultdict(list)
        for c in candidates:
            key = self._normalise(c.title)
            bucket[key].append(c)

        duplicates = []
        for norm_title, group in sorted(bucket.items()):
            distinct_sites = {c.site_id for c in group}
            if len(distinct_sites) > threshold:
                duplicates.append(DuplicateGroup(normalised_title=norm_title, candidates=group))

        return duplicates

    # ─────────────────────────────────────────────────────────────────
    # Clarification prompt
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def build_clarification_prompt(group: DuplicateGroup) -> str:
        """Return the Markdown clarification message for a duplicate group.

        The returned string is ready to be set as the ``reply`` of a
        ``ChatResponse`` with ``requires_input=True``.

        Format::

            I found multiple items named "FAQs" across the hub:

            1. HR Site — https://contoso.sharepoint.com/sites/hr/lists/faqs
            2. Support Site — https://contoso.sharepoint.com/sites/support/...

            Which one would you like to work with?
        """
        display_title = group.candidates[0].title if group.candidates else group.normalised_title

        lines = [
            f'I found multiple items named **"{display_title}"** across the hub:\n',
        ]
        for i, candidate in enumerate(group.candidates, start=1):
            site_name = candidate.site_name or "Unknown Site"
            url = candidate.web_url or candidate.site_url or "(no URL)"
            lines.append(f"{i}. **{site_name}** — {url}")

        lines.append("\nWhich one would you like to work with?")
        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────
    # Not-found prompt
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def build_not_found_prompt(resource_name: str) -> str:
        """Return the Markdown not-found message.

        Used when the requested item cannot be located anywhere in the hub.

        Format::

            I couldn't find "Project Tracker" anywhere in the current hub.
            Can you tell me which site it belongs to, or provide the site URL?
        """
        return (
            f'I couldn\'t find **"{resource_name}"** anywhere in the current hub.\n'
            "Can you tell me which site it belongs to, or provide the site URL?"
        )
