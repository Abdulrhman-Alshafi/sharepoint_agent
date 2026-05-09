"""Infrastructure implementation of SmartResourceDiscoveryService.

This service discovers all SharePoint lists and document libraries across
multiple sites, ranks them by relevance to a user question (using title
similarity first, then column-schema similarity for the top-20), and
selects the single best candidate.

Ranking is done in two passes to avoid excessive Graph API calls:
  * Pass 1 — instant Jaccard + substring scoring against resource titles.
  * Pass 2 — fetch column schemas for the top-20 and add column-match score.

The final ``select_best_candidate`` step skips an AI call when the winning
score is already ≥ CANDIDATE_SCORE_THRESHOLD (default 0.5); otherwise a
small AI prompt breaks the tie.
"""

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

from src.domain.services.smart_resource_discovery import ISmartResourceDiscoveryService
from src.domain.value_objects.resource_candidate import ResourceCandidate
from src.infrastructure.config import settings
from src.infrastructure.services.section_index import SectionIndexService

logger = logging.getLogger(__name__)

# _SYNONYMS is now sourced from the detection package; kept as an alias for
# any code that still references it directly.
from src.detection.semantic.synonym_expander import SYNONYMS as _SYNONYMS


def _expand_with_synonyms(tokens: set) -> set:
    """Return *tokens* plus any synonym tokens from the detection package."""
    from src.detection.semantic.synonym_expander import expand_tokens
    return expand_tokens(tokens)



_CANDIDATE_SCORE_THRESHOLD: float = getattr(settings, "CANDIDATE_SCORE_THRESHOLD", 0.5)
_MAX_PASS1_CANDIDATES: int = 20   # schema fetch only for top-N after pass 1
_TOP_CANDIDATES: int = 5          # final shortlist returned to caller


def _tokenise(text: str) -> set:
    """Lower-case word tokens, stripping punctuation.

    Also splits camelCase/PascalCase identifiers so that e.g.
    ``KudosPosts`` yields ``{"kudos", "posts", "kudosposts"}`` and
    ``EmployeeOfMonth`` yields ``{"employee", "of", "month", "employeeofmonth"}``.
    """
    # Standard word split (handles spaces, underscores, hyphens)
    raw = set(re.findall(r"[a-z0-9]+", text.lower()))
    # camelCase / PascalCase split: insert boundary before each uppercase run
    camel_split = set(
        re.findall(r"[a-z0-9]+", re.sub(r"([A-Z]+)", r" \1", text).lower())
    )
    return raw | camel_split


def _title_score(question_tokens: set, title: str) -> float:
    """Pass-1: Jaccard + substring bonus, normalised to 0–0.6."""
    title_tokens = _tokenise(title)
    if not title_tokens or not question_tokens:
        return 0.0

    intersection = question_tokens & title_tokens
    union = question_tokens | title_tokens
    jaccard = len(intersection) / len(union)

    # 0.3 bonus if any question token appears as a substring of the title
    title_lower = title.lower()
    substring_bonus = 0.3 if any(t in title_lower for t in question_tokens) else 0.0

    raw = jaccard + substring_bonus
    # Cap at 1.0 before normalising to 0–0.6
    return min(raw, 1.0) * 0.6


def _column_score(question_tokens: set, column_names: List[str]) -> float:
    """Pass-2: fraction of question tokens that match any column display name.
    Normalised to 0–0.4.
    """
    if not question_tokens or not column_names:
        return 0.0
    col_token_set: set = set()
    for col in column_names:
        col_token_set |= _tokenise(col)
    matches = sum(1 for t in question_tokens if t in col_token_set)
    return (matches / len(question_tokens)) * 0.4


class SmartResourceDiscoveryService(ISmartResourceDiscoveryService):
    """Discovers and ranks SharePoint resources across all accessible sites."""

    def __init__(
        self,
        site_repository,
        list_repository,
        library_repository,
        page_repository,
        ai_client=None,
        ai_model: Optional[str] = None,
    ):
        """Initialise the service.

        Args:
            site_repository: Repository for site operations.
            list_repository: Repository for list operations.
            library_repository: Repository for library operations.
            page_repository: Repository for page operations.
            ai_model:     Model string forwarded to the AI client when calling.
        """
        self._site_repo = site_repository
        self._list_repo = list_repository
        self._library_repo = library_repository
        self._page_repo = page_repository
        self._ai_client = ai_client
        self._ai_model = ai_model

    # ─────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────

    async def discover_all_resources(self, site_ids: Optional[List[str]] = None) -> List[ResourceCandidate]:
        """Discover all lists and libraries across provided *site_ids* in parallel.
        """
        if not site_ids:
            site_ids = []

        if not site_ids:
            logger.warning("SmartDiscovery: no site IDs available for discovery")
            return []

        # Build site info cache: site_id → {name, url}
        site_info_map: Dict[str, Dict[str, str]] = {}
        try:
            all_sites = await self._site_repo.get_all_sites()
            for s in all_sites:
                site_info_map[s.get("id", "")] = {
                    "name": s.get("displayName") or s.get("name", "Unknown"),
                    "url": s.get("webUrl", ""),
                }
        except Exception as exc:
            logger.warning("Could not fetch all-sites info for discovery: %s", exc)

        async def fetch_site(site_id: str) -> List[ResourceCandidate]:
            """Fetch lists + libraries for one site, ignoring errors."""
            candidates: List[ResourceCandidate] = []
            site_meta = site_info_map.get(site_id, {})
            _raw_site_name = (site_meta.get("name") or "").strip()
            # Never expose a raw GUID as the human-visible site name
            site_name = (
                _raw_site_name
                if _raw_site_name and not re.match(r"^[0-9a-fA-F]{8}-", _raw_site_name)
                else "SharePoint"
            )
            site_url = site_meta.get("url", "")

            # ── Lists ──────────────────────────────────────────────────
            try:
                lists = await self._list_repo.get_all_lists(site_id=site_id)
                for lst in lists:
                    # Skip built-in system lists (hidden flag)
                    if lst.get("list", {}).get("hidden", False):
                        continue
                    candidates.append(
                        ResourceCandidate(
                            resource_id=lst.get("id", ""),
                            resource_type="list",
                            title=lst.get("displayName", lst.get("name", "")),
                            site_id=site_id,
                            site_name=site_name,
                            site_url=site_url,
                            web_url=lst.get("webUrl", ""),
                        )
                    )
            except Exception as exc:
                logger.warning("Failed to fetch lists for site %s: %s", site_id, exc)

            # ── Document libraries ─────────────────────────────────────
            try:
                libraries = await self._library_repo.get_all_document_libraries(site_id=site_id)
                for lib in libraries:
                    if lib.get("list", {}).get("hidden", False):
                        continue
                    candidates.append(
                        ResourceCandidate(
                            resource_id=lib.get("id", ""),
                            resource_type="library",
                            title=lib.get("displayName", lib.get("name", "")),
                            site_id=site_id,
                            site_name=site_name,
                            site_url=site_url,
                            web_url=lib.get("webUrl", ""),
                        )
                    )
            except Exception as exc:
                logger.warning("Failed to fetch libraries for site %s: %s", site_id, exc)

            # ── Pages ──────────────────────────────────────────────────
            try:
                pages = await self._page_repo.get_all_pages(site_id=site_id)
                for page in pages:
                    page_id = page.get("id") or page.get("eTag", "").strip('"')
                    if not page_id:
                        continue
                    candidates.append(
                        ResourceCandidate(
                            resource_id=page_id,
                            resource_type="page",
                            title=page.get("title") or page.get("name") or "Untitled",
                            site_id=site_id,
                            site_name=site_name,
                            site_url=site_url,
                            web_url=page.get("webUrl", ""),
                        )
                    )
            except Exception as exc:
                logger.warning("Failed to fetch pages for site %s: %s", site_id, exc)

            return candidates

        # Bounded concurrency: at most 5 sites fetched in parallel
        _semaphore = asyncio.Semaphore(5)

        async def _bounded_fetch(site_id: str) -> List[ResourceCandidate]:
            async with _semaphore:
                return await fetch_site(site_id)

        # Parallel fetch for all sites
        results = await asyncio.gather(*(_bounded_fetch(sid) for sid in site_ids))
        # Flatten
        all_candidates: List[ResourceCandidate] = []
        for site_results in results:
            all_candidates.extend(site_results)

        logger.info(
            "Discovery complete — found %d resources across %d site(s)",
            len(all_candidates),
            len(site_ids),
        )
        return all_candidates

    async def rank_candidates(
        self, question: str, candidates: List[ResourceCandidate],
        preferred_resource_type: Optional[str] = None,
        context_page_id: Optional[str] = None,
        context_site_id: Optional[str] = None,
    ) -> List[ResourceCandidate]:
        """Two-pass ranking.  Returns at most *_TOP_CANDIDATES* results.

        Args:
            question:               The user's natural-language question.
            candidates:             Full list of ResourceCandidates to rank.
            preferred_resource_type: When ``"list"`` or ``"library"``, apply a
                                    0.15 bonus to candidates of that type so
                                    they rank higher when scores are close.
        """
        if not candidates:
            return []

        q_tokens = _tokenise(question)
        # Expand with synonyms so "tasks" can match "Work Items", etc.
        q_tokens_expanded = _expand_with_synonyms(q_tokens)

        # Query-specialisation guardrails:
        # "employee of the month" should prefer dedicated recognition resources
        # and avoid defaulting to kudos feeds unless the user explicitly asked
        # for kudos.
        _q_lower = question.lower()
        _is_employee_of_month_query = (
            "employee of the month" in _q_lower
            or "employeeofmonth" in q_tokens
            or ({"employee", "month"} <= q_tokens)
        )
        _explicit_kudos_query = "kudos" in q_tokens or "kudo" in q_tokens

        # HITL Phase 1: merge ConceptMapper expanded tokens + resource_hint
        try:
            from src.infrastructure.services.concept_mapper import ConceptMapper
            _mapping = ConceptMapper().map_query(question)
            q_tokens_expanded |= _mapping.expanded_tokens
            if _mapping.resource_hint and not preferred_resource_type:
                preferred_resource_type = _mapping.resource_hint
        except Exception:
            pass  # never break ranking if ConceptMapper fails

        # ── Pass 1: title scoring (no API calls) ──────────────────────
        pass1: List[ResourceCandidate] = []
        for c in candidates:
            score = _title_score(q_tokens_expanded, c.title)
            _title_toks = _tokenise(c.title)

            if _is_employee_of_month_query:
                if "employeeofmonth" in _title_toks or ({"employee", "month"} <= _title_toks):
                    # Massive boost for recognition/employee-of-month resources
                    score = 0.95
                    logger.info(
                        "Employee-of-month BOOST: '%s' (contains employee+month pattern) → score=0.95",
                        c.title
                    )
                if not _explicit_kudos_query and ("kudos" in _title_toks or "kudo" in _title_toks):
                    # Severe penalty for kudos resources in employee-of-month queries
                    score = 0.0
                    logger.info(
                        "Employee-of-month PENALTY: '%s' (kudos in title, not explicit kudos query) → score=0.0",
                        c.title
                    )

            if _title_toks and _title_toks.issubset(q_tokens_expanded):
                score = min(score + 0.4, 1.0)
            # Resource-type preference bonus
            if preferred_resource_type and c.resource_type == preferred_resource_type:
                score = min(score + 0.15, 1.0)
            # Current-page pin (Phase 3)
            if context_page_id and c.resource_id == context_page_id:
                score = min(score + 1.0, 2.0)
            # Current-site boost (Phase 3)
            if context_site_id and c.site_id == context_site_id:
                score = min(score + 0.3, 2.0)
            pass1.append(
                ResourceCandidate(
                    resource_id=c.resource_id,
                    resource_type=c.resource_type,
                    title=c.title,
                    site_id=c.site_id,
                    site_name=c.site_name,
                    site_url=c.site_url,
                    web_url=c.web_url,
                    column_names=c.column_names,
                    relevance_score=score,
                )
            )
        pass1.sort(key=lambda x: x.relevance_score, reverse=True)
        top20 = pass1[:_MAX_PASS1_CANDIDATES]

        # ── Pass 2: column schema scoring (API calls for top-20 only, bounded) ──
        _schema_semaphore = asyncio.Semaphore(5)

        async def _bounded_schema(c: ResourceCandidate) -> ResourceCandidate:
            async with _schema_semaphore:
                return await self._fetch_column_names(c)

        schema_tasks = [_bounded_schema(c) for c in top20]
        enriched = await asyncio.gather(*schema_tasks)

        pass2: List[ResourceCandidate] = []
        for c_enriched in enriched:
            col_score = _column_score(q_tokens_expanded, c_enriched.column_names)
            final_score = c_enriched.relevance_score + col_score
            pass2.append(
                ResourceCandidate(
                    resource_id=c_enriched.resource_id,
                    resource_type=c_enriched.resource_type,
                    title=c_enriched.title,
                    site_id=c_enriched.site_id,
                    site_name=c_enriched.site_name,
                    site_url=c_enriched.site_url,
                    web_url=c_enriched.web_url,
                    column_names=c_enriched.column_names,
                    relevance_score=final_score,
                )
            )

        pass2.sort(key=lambda x: x.relevance_score, reverse=True)
        top5 = pass2[:_TOP_CANDIDATES]

        # ── Phase 2: Semantic re-rank of top-5 (0 AI tokens — embeddings cached) ──
        try:
            from src.infrastructure.services.embedding_service import EmbeddingService
            _embedder = EmbeddingService()
            _q_emb = await _embedder.embed_text(question)
            if _q_emb:
                reranked: List[ResourceCandidate] = []
                for c in top5:
                    _title_col = f"{c.title} {' '.join(c.column_names or [])}".strip()
                    _c_emb = await _embedder.embed_text(_title_col)
                    sem_score = EmbeddingService.cosine_similarity(_q_emb, _c_emb) if _c_emb else 0.0
                    reranked.append(
                        ResourceCandidate(
                            resource_id=c.resource_id,
                            resource_type=c.resource_type,
                            title=c.title,
                            site_id=c.site_id,
                            site_name=c.site_name,
                            site_url=c.site_url,
                            web_url=c.web_url,
                            column_names=c.column_names,
                            relevance_score=0.7 * sem_score + 0.3 * c.relevance_score,
                        )
                    )
                reranked.sort(key=lambda x: x.relevance_score, reverse=True)
                top5 = reranked
        except Exception:
            pass  # semantic re-rank is best-effort; never break ranking

        # ── Pass 2.5 — Section-level keyword boost ────────────────────────────
        try:
            _sec_idx = SectionIndexService()
            _boosted_ids = set()
            _unique_sites = {c.site_id for c in top5 if c.site_id}
            for sid in _unique_sites:
                _sec_hits = await _sec_idx.search_sections_keyword(question, sid, top_k=20)
                if _sec_hits:
                    _boosted_ids.update(s.get("page_id") for s in _sec_hits if s.get("page_id"))
            
            if _boosted_ids:
                top5 = [
                    ResourceCandidate(
                        resource_id=c.resource_id,
                        resource_type=c.resource_type,
                        title=c.title,
                        site_id=c.site_id,
                        site_name=c.site_name,
                        site_url=c.site_url,
                        web_url=c.web_url,
                        column_names=c.column_names,
                        relevance_score=min(c.relevance_score + 0.7, 2.0)
                        if c.resource_id in _boosted_ids
                        else c.relevance_score,
                    )
                    for c in top5
                ]
                top5.sort(key=lambda x: x.relevance_score, reverse=True)
        except Exception:
            pass  # section boost is best-effort

        logger.debug(
            "Ranked candidates for question %r (preferred_type=%s): %s",
            question,
            preferred_resource_type or "any",
            [(c.title, c.resource_type, round(c.relevance_score, 3)) for c in top5],
        )
        return top5

    async def select_best_candidate(
        self,
        question: str,
        ranked_candidates: List[ResourceCandidate],
    ) -> Optional[ResourceCandidate]:
        """Return the best candidate, using an AI tiebreaker if score is low."""
        if not ranked_candidates:
            return None

        best = ranked_candidates[0]

        # No candidate has any meaningful score — refuse to guess
        if best.relevance_score == 0.0:
            logger.info(
                "All candidates scored 0.0 for question %r — returning None to avoid wrong match",
                question,
            )
            return None

        # Confident match — no AI call needed
        if best.relevance_score >= _CANDIDATE_SCORE_THRESHOLD:
            logger.info(
                "Confident match: '%s' (score=%.3f)", best.title, best.relevance_score
            )
            return best

        # Low-confidence — ask the AI to pick
        if self._ai_client is None:
            logger.warning(
                "No AI client available for tie-breaking; returning top candidate '%s'",
                best.title,
            )
            return best

        logger.info(
            "Low-confidence match (score=%.3f), invoking AI tiebreaker", best.relevance_score
        )
        try:
            candidate_descriptions = "\n".join(
                f"{i+1}. [{c.resource_type}] \"{c.title}\" in site \"{c.site_name}\""
                f"  — columns: {', '.join(c.column_names[:10]) or 'unknown'}"
                for i, c in enumerate(ranked_candidates)
            )
            prompt = (
                f"A user asked: \"{question}\"\n\n"
                "Below are SharePoint resources that might contain the answer.\n"
                "Reply with ONLY the number (1, 2, 3 …) of the resource most likely to have the answer.\n\n"
                f"{candidate_descriptions}"
            )
            kwargs: Dict[str, Any] = {
                "messages": [{"role": "user", "content": prompt}],
            }
            if self._ai_model:
                kwargs["model"] = self._ai_model

            # Use a plain completion (no instructor schema) to get a simple digit
            response = self._ai_client.chat.completions.create(**kwargs, timeout=10.0)
            raw = response.choices[0].message.content.strip()
            idx = int(re.search(r"\d+", raw).group()) - 1
            if 0 <= idx < len(ranked_candidates):
                chosen = ranked_candidates[idx]
                logger.info(
                    "AI tiebreaker chose: '%s' (index=%d)", chosen.title, idx
                )
                return chosen
        except Exception as exc:
            logger.warning("AI tiebreaker failed (%s); using top-ranked candidate", exc)

        return best

    # ─────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────

    async def _fetch_column_names(self, candidate: ResourceCandidate) -> ResourceCandidate:
        """Fetch column display names for a candidate and return enriched copy."""
        # If already populated, skip
        if candidate.column_names:
            return candidate

        column_names: List[str] = []
        try:
            if candidate.resource_type == "list":
                columns = await self._list_repo.get_list_columns(
                    candidate.resource_id, site_id=candidate.site_id
                )
                column_names = [
                    c.get("displayName", c.get("name", ""))
                    for c in columns
                    if not c.get("hidden", False)
                ]
            else:  # library
                schema = await self._library_repo.get_library_schema(
                    candidate.resource_id, site_id=candidate.site_id
                )
                column_names = [
                    c.get("displayName", c.get("name", ""))
                    for c in schema.get("columns", [])
                    if not c.get("hidden", False)
                ]
        except Exception as exc:
            logger.debug(
                "Could not fetch columns for '%s' (%s): %s",
                candidate.title,
                candidate.resource_id,
                exc,
            )

        return ResourceCandidate(
            resource_id=candidate.resource_id,
            resource_type=candidate.resource_type,
            title=candidate.title,
            site_id=candidate.site_id,
            site_name=candidate.site_name,
            site_url=candidate.site_url,
            web_url=candidate.web_url,
            column_names=column_names,
            relevance_score=candidate.relevance_score,
        )

    # ─────────────────────────────────────────────────────────────────
    # Sibling resource discovery (Phase 13)
    # ─────────────────────────────────────────────────────────────────

    _SIBLING_MAX_CANDIDATES = 10
    _SIBLING_MAX = 5
    _SIBLING_COL_CACHE_TTL = 86400  # 24 hours
    _sibling_col_cache: Dict[str, Any] = {}
    _sibling_col_cache_ts: Dict[str, float] = {}

    async def find_sibling_resources(
        self,
        winner: ResourceCandidate,
        all_candidates: List[ResourceCandidate],
    ) -> List[ResourceCandidate]:
        """Find related (sibling) resources to the winning candidate.

        Stage 1 — name-prefix filter: candidates whose title shares a leading
                   token with the winner's title.
        Stage 2 — column-schema validation: fetch columns (with 24h TTL cache)
                   and apply FK / related-column heuristic.

        Returns at most _SIBLING_MAX ResourceCandidate objects.
        """
        try:
            winner_prefix = self._normalised_title(winner.title).split()[0] if winner.title else ""
            if not winner_prefix:
                return []

            # Stage 1: name-prefix filter
            stage1 = [
                c for c in all_candidates
                if c.resource_id != winner.resource_id
                and self._normalised_title(c.title).startswith(winner_prefix)
            ][: self._SIBLING_MAX_CANDIDATES]

            if not stage1:
                return []

            # Stage 2: column validation in parallel
            enriched = await asyncio.gather(
                *[self._get_columns_cached(c) for c in stage1],
                return_exceptions=True,
            )
            siblings: List[ResourceCandidate] = []
            winner_cols = set(self._normalised_title(col) for col in (winner.column_names or []))
            # Flat (no-space) normalised form for compound-name detection
            winner_norm_flat = self._normalised_title(winner.title).replace(" ", "")
            for item in enriched:
                if isinstance(item, Exception) or not isinstance(item, ResourceCandidate):
                    continue
                cand_norm_flat = self._normalised_title(item.title).replace(" ", "")
                is_compound_pair = (
                    cand_norm_flat.startswith(winner_norm_flat)
                    or winner_norm_flat.startswith(cand_norm_flat)
                )
                if is_compound_pair or self._is_related(winner_cols, item):
                    siblings.append(item)
                if len(siblings) >= self._SIBLING_MAX:
                    break
            return siblings
        except Exception as exc:
            logger.debug("find_sibling_resources failed: %s", exc)
            return []

    async def _get_columns_cached(self, candidate: ResourceCandidate) -> ResourceCandidate:
        """Return column-enriched candidate; result is cached for 24h TTL."""
        import time as _time
        _key = candidate.resource_id
        _now = _time.time()
        if _key in self._sibling_col_cache:
            if _now - self._sibling_col_cache_ts.get(_key, 0) < self._SIBLING_COL_CACHE_TTL:
                return self._sibling_col_cache[_key]
        result = await self._fetch_column_names(candidate)
        self._sibling_col_cache[_key] = result
        self._sibling_col_cache_ts[_key] = _now
        return result

    @staticmethod
    def _is_related(winner_cols: set, candidate: ResourceCandidate) -> bool:
        """Return True if candidate shares ≥1 column name with the winner."""
        candidate_cols = set(
            SmartResourceDiscoveryService._normalised_title(col)
            for col in (candidate.column_names or [])
        )
        return bool(winner_cols & candidate_cols)

    @staticmethod
    def _normalised_title(text: str) -> str:
        """Lower-case, strip punctuation, collapse whitespace."""
        return re.sub(r"[^a-z0-9 ]", "", (text or "").lower()).strip()
