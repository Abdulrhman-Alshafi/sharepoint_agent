"""Domain service interface for smart cross-resource discovery.

This abstract class defines the contract for discovering, ranking, and
selecting the best-matching SharePoint list or document library for a
given natural-language question.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from src.domain.value_objects.resource_candidate import ResourceCandidate


class ISmartResourceDiscoveryService(ABC):
    """Interface for smart cross-resource discovery across multiple SP sites."""

    @abstractmethod
    async def discover_all_resources(self, site_ids: List[str]) -> List[ResourceCandidate]:
        """Discover all lists and libraries across the given sites.

        Args:
            site_ids: List of SharePoint site IDs to inspect.

        Returns:
            Flat list of ResourceCandidate objects (lists + libraries).
        """
        pass

    @abstractmethod
    async def rank_candidates(
        self, question: str, candidates: List[ResourceCandidate],
        preferred_resource_type: Optional[str] = None,
    ) -> List[ResourceCandidate]:
        """Rank candidates by relevance to *question*.

        Scoring happens in two passes:
        * Pass 1 — instant title/token similarity (no extra API calls).
          Synonym expansion is applied so "tasks" matches "Work Items", etc.
        * Pass 2 — column-schema similarity for the top-20 candidates.

        Args:
            question:               The user's natural-language question.
            candidates:             Full list of ResourceCandidates to rank.
            preferred_resource_type: Optional ``"list"`` or ``"library"``.
                                    Adds a 0.15 score bonus to candidates of
                                    that type so resource-specific intents
                                    (e.g. library_content) prefer the correct
                                    resource kind when scores are close.

        Returns:
            Candidates sorted descending by ``relevance_score``; at most top-5.
        """
        pass

    @abstractmethod
    async def select_best_candidate(
        self,
        question: str,
        ranked_candidates: List[ResourceCandidate],
    ) -> Optional[ResourceCandidate]:
        """Pick the single best candidate for *question*.

        If ``candidates[0].relevance_score >= settings.CANDIDATE_SCORE_THRESHOLD``
        the winner is returned immediately (no AI call).  Otherwise a small AI
        prompt decides among the candidates.

        Args:
            question:          The user's natural-language question.
            ranked_candidates: Top-ranked candidates from ``rank_candidates``.

        Returns:
            The selected ``ResourceCandidate``, or ``None`` if the list is empty.
        """
        pass
