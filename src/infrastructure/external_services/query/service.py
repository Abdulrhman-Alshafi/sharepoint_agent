"""AIDataQueryService — query router that inherits from focused mixin classes.

Each mixin handles one concern:
    MetadataQueryMixin  – metadata / site queries (_handle_metadata_count, filtered_meta, etc.)
    LibraryQueryMixin   – library & document queries
    DataQueryMixin      – specific list data + Graph-search fallback
"""

import logging
from typing import Any, Dict, List, Optional
import time as _time
import re as _re

from src.domain.entities import DataQueryResult
from src.domain.services import DataQueryService
from src.domain.repositories import SharePointRepository
from src.domain.exceptions import DataQueryException
from src.infrastructure.external_services.ai_client_factory import get_instructor_client
from src.infrastructure.schemas.query_schemas import (
    RouterResponse,
    DataQueryResponseModel,
    QueryIntent,
    ResourceType,
)
from src.infrastructure.external_services.query_intelligence import (
    ResourceTypeDetector,
    KeywordFilter,
    QueryAnalyzer,
    format_resource_list,
)
from src.infrastructure.external_services.site_resolver import SiteResolver
from src.infrastructure.external_services.document_intelligence import DocumentIntelligenceService
from src.infrastructure.external_services.library_intelligence import LibraryIntelligenceService
from src.infrastructure.services.document_index import DocumentIndexService
from src.infrastructure.services.duplicate_name_resolver import DuplicateNameResolver
from src.infrastructure.config import settings
from src.infrastructure.services.sharepoint.search_service import SearchService
from src.infrastructure.services.concept_mapper import ConceptMapper
from src.infrastructure.services.concept_memory import ConceptMemory
from src.infrastructure.services.context_normalizer import normalize_context_from_fields, NormalizedContext
from src.infrastructure.services.query_telemetry import log_query_trace

# Mixin imports
from src.infrastructure.external_services.query.metadata_mixin import MetadataQueryMixin
from src.infrastructure.external_services.query.library_mixin import LibraryQueryMixin
from src.infrastructure.external_services.query.data_mixin import DataQueryMixin
from src.infrastructure.external_services.query.page_mixin import PageQueryMixin
from src.infrastructure.external_services.query.prompts import ROUTER_PROMPT
from src.infrastructure.external_services.query.helpers import find_list_by_name

logger = logging.getLogger(__name__)


_DEFAULT_SITE_ALIAS_RE = _re.compile(
    r"\b(?:in|on|from|at)\s+(?:the\s+)?(?:main|default|current|this)\s+(?:site|list)\b",
    _re.IGNORECASE,
)


class AIDataQueryService(
    MetadataQueryMixin,
    LibraryQueryMixin,
    DataQueryMixin,
    PageQueryMixin,
    DataQueryService,
):
    """Implementation of data querying using flexible AI (RAG reasoning loop).

    The class is intentionally thin — all handler methods live in the mixins
    above.  This class owns:
      * __init__  (wires all dependencies)
      * answer_question  (main routing loop)
      * _run_smart_discovery  (cross-resource discovery pipeline)
      * _RESOURCE_SPECIFIC_INTENTS  (set used by the routing loop)
    """

    # Intents that require a *specific* resource — smart discovery applies here
    _RESOURCE_SPECIFIC_INTENTS = {
        QueryIntent.SPECIFIC_DATA,
        QueryIntent.LIBRARY_CONTENT,
        QueryIntent.DOCUMENT_SEARCH,
        QueryIntent.DATA_EXTRACTION,
        QueryIntent.CONTENT_SUMMARY,
        QueryIntent.LIBRARY_COMPARISON,
        QueryIntent.PAGE_CONTENT,
    }

    # Keywords that promote a PAGE resource_type to PAGE_CONTENT intent
    # (kept for backward compat; logic delegated to detection.routing.page_content_router)

    def __init__(
        self,
        sharepoint_repository: SharePointRepository,
        graph_client,
        site_id: str,
        smart_discovery_service=None,
        ai_client=None,
        ai_model: Optional[str] = None,
    ):
        self.sharepoint_repository = sharepoint_repository
        self.graph_client = graph_client
        self.site_id = site_id
        self.search_service = SearchService(graph_client)
        if ai_client is not None:
            self.client = ai_client
            self.model = ai_model
        else:
            try:
                self.client, self.model = get_instructor_client()
            except Exception as exc:
                raise DataQueryException(f"Failed to initialize AI client: {exc}")

        self._smart_discovery = smart_discovery_service
        self._duplicate_resolver = DuplicateNameResolver()

        # Intelligence services
        self.document_intelligence = DocumentIntelligenceService()
        self.library_intelligence = LibraryIntelligenceService()
        self.document_index = DocumentIndexService()

        # Query context tracking for follow-up questions (keyed by session_id)
        self._session_context: dict = {}  # session_id -> {last_list_id, last_list_name, last_site_id, last_site_name}
        # Legacy single-session fields kept for backward compat (no session_id callers)
        self._last_list_id: Optional[str] = None
        self._last_list_name: Optional[str] = None
        self._last_site_id: Optional[str] = None
        self._last_site_name: Optional[str] = None

    # ─────────────────────────────────────────────────────────────────────────
    # Main routing entry point
    # ─────────────────────────────────────────────────────────────────────────

    async def answer_question(
        self,
        question: str,
        site_ids=None,
        page_id: Optional[str] = None,
        page_url: Optional[str] = None,
        page_title: Optional[str] = None,
        context_site_id: Optional[str] = None,
    ) -> DataQueryResult:
        """Execute intelligent reasoning loop with smart filtering and classification."""
        _start_ts = _time.monotonic()
        _telemetry_intent = "unknown"
        _telemetry_resources: list = []
        _telemetry_page_hit = False
        _telemetry_fallback = False

        # Build a normalised context object from the forwarded fields
        _norm_ctx = normalize_context_from_fields(
            context_site_id=context_site_id,
            page_id=page_id,
            page_url=page_url,
            page_title=page_title,
        )

        try:
            # Strip [Current user: ...] prefix injected by chat.py for personal queries.
            # It provides user identity context for data retrieval but must not influence
            # intent routing or resource ranking (it causes the router to pick wrong lists).
            import re as _re_svc
            _user_ctx_re = _re_svc.compile(r'^\[Current user:[^\]]*\]\s*', _re_svc.IGNORECASE)
            _user_ctx_match = _user_ctx_re.match(question)
            _user_ctx_block = _user_ctx_match.group(0) if _user_ctx_match else ""
            _routing_question = _user_ctx_re.sub("", question).strip()

            # Step 1: Resolve vague follow-ups using stored context
            # Only match when the follow-up phrase appears at the START of the message
            # to avoid false positives in the middle of longer sentences.
            question_lower = _routing_question.lower().lstrip()
            _FOLLOWUP_STARTS = (
                "tell me more", "more about", "about it", "more info", "details",
                "tell me about it", "what about it", "more on that", "elaborate",
            )
            is_followup = any(question_lower.startswith(phrase) for phrase in _FOLLOWUP_STARTS)
            if is_followup and self._last_list_name:
                if self._last_site_name:
                    _routing_question = f"tell me about {self._last_list_name} list in {self._last_site_name} site"
                else:
                    _routing_question = f"tell me about {self._last_list_name} list"
                logger.info("Follow-up detected, using context: %s", _routing_question)

            # HITL: Translate human language → enriched query 
            _original_question = question
            import asyncio as _asyncio
            _learned = await ConceptMemory().lookup(_routing_question.lower())
            _mapping = ConceptMapper().map_query(_routing_question, learned_concepts=_learned)
            # Use rewritten routing question for router/ranking; preserve full enriched
            # question (with user ctx) for actual data retrieval calls.
            _routing_question = _mapping.rewritten_query
            question = _user_ctx_block + _routing_question  # full enriched (user ctx + rewritten)
            # Inject resource_hint as a soft signal to the AI router
            _router_hint_prefix = ""
            if _mapping.resource_hint:
                _router_hint_prefix = f"[Resource hint: {_mapping.resource_hint}]\n"
            logger.debug(
                "HITL mapping: hint=%s, concepts=%s, confidence=%.2f",
                _mapping.resource_hint, _mapping.concepts, _mapping.confidence,
            )

            # Phase 5: Detect compound (multi-hop) questions — zero AI tokens
            try:
                from src.infrastructure.services.multi_hop_retriever import MultiHopRetriever
                from src.infrastructure.services.cross_resource_synthesizer import CrossResourceSynthesizer
                _mh_retriever = MultiHopRetriever(answer_fn=self.answer_question)
                _mh_plan = _mh_retriever.detect(question)
                if _mh_plan.is_compound:
                    logger.info(
                        "Multi-hop question detected (%d sub-questions)",
                        len(_mh_plan.sub_questions),
                    )
                    _mh_result = await _mh_retriever.retrieve(_mh_plan)
                    _combined = await CrossResourceSynthesizer(
                        client=self.client, model=self.model
                    ).synthesize(_mh_result, question)
                    return DataQueryResult(
                        answer=_combined,
                        data_summary={"multi_hop": True, "sub_questions": len(_mh_plan.sub_questions)},
                        suggested_actions=["Ask a follow-up question"],
                    )
            except Exception as _mh_exc:
                logger.debug("Multi-hop detection skipped (non-fatal): %s", _mh_exc)

            # Step 2: Get all sites for site resolution.
            all_sites = await self.sharepoint_repository.get_all_sites()

            # Step 3: Try deterministic site extraction
            # If context_site_id is provided, use it directly without SiteResolver
            extracted_site_name = None
            target_site_id = None
            target_site_name = None
            target_site_url = None

            extracted_site_name = SiteResolver.extract_site_mention(_routing_question)
            _has_default_site_alias = bool(_DEFAULT_SITE_ALIAS_RE.search(_routing_question))

            if context_site_id:
                # Start from request context, but allow explicit site in user query to override it.
                target_site_id = context_site_id
                for _s in all_sites:
                    if _s.get("id") == context_site_id:
                        target_site_name = _s.get("displayName") or _s.get("name")
                        target_site_url = _s.get("webUrl", "")
                        break

                if extracted_site_name:
                    site_info = SiteResolver.resolve_site_name(extracted_site_name, all_sites)
                    if site_info:
                        target_site_id, target_site_name, target_site_url = site_info
                        logger.info(
                            "Overriding context site with explicit site '%s' -> %s (ID: %s)",
                            extracted_site_name, target_site_name, target_site_id,
                        )
                    else:
                        logger.info(
                            "Extracted token '%s' did not match any site — keeping context site.",
                            extracted_site_name,
                        )
                elif _has_default_site_alias:
                    logger.info(
                        "Detected default-site alias in question; using context_site_id=%s (name=%s)",
                        context_site_id,
                        target_site_name,
                    )
                else:
                    logger.info("Using context_site_id=%s directly (name=%s)", context_site_id, target_site_name)
            else:
                if extracted_site_name:
                    site_info = SiteResolver.resolve_site_name(extracted_site_name, all_sites)
                    if site_info:
                        target_site_id, target_site_name, target_site_url = site_info
                        logger.info(
                            "Resolved site '%s' to %s (ID: %s)",
                            extracted_site_name, target_site_name, target_site_id,
                        )
                    else:
                        logger.info(
                            "Extracted token '%s' did not match any site — treating as list context.",
                            extracted_site_name,
                        )
                        extracted_site_name = None

            # Step 4: Fetch lists for the resolved/default site
            all_lists = await self.sharepoint_repository.get_all_lists(site_id=target_site_id)
            if not all_lists:
                site_context = f" in the {target_site_name} site" if target_site_name else ""
                return DataQueryResult(
                    answer=f"I couldn't find any lists{site_context} to answer your question."
                )

            list_summaries = [
                {
                    "id": lst.get("id"),
                    "name": lst.get("displayName"),
                    "description": lst.get("description", ""),
                }
                for lst in all_lists
            ]

            # Step 5: Deterministic list-name match → treat as specific_data
            direct_match = find_list_by_name(_routing_question, list_summaries)
            if direct_match:
                return await self._handle_specific_data_query(
                    question, direct_match, all_lists, target_site_id, target_site_name
                )

            # Step 6: AI router to classify intent
            _ctx_block = _build_context_block(_norm_ctx)
            _reply_anchor = _build_reply_anchor(_norm_ctx)
            router_prompt = (
                f"{ROUTER_PROMPT}\n\n"
                f"{_ctx_block}"
                f"Available Lists:\n{list_summaries}\n\n"
                f"{_router_hint_prefix}Current Question: {_routing_question}"
                f"{_reply_anchor}"
            )
            kwargs = {
                "messages": [{"role": "user", "content": router_prompt}],
                "response_model": RouterResponse,
            }
            if self.model:
                kwargs["model"] = self.model
            route = self.client.chat.completions.create(**kwargs)

            # Step 7: Resolve site from router response if not already resolved
            if route.site_name and not target_site_id:
                site_info = SiteResolver.resolve_site_name(route.site_name, all_sites)
                if site_info:
                    target_site_id, target_site_name, target_site_url = site_info
                    logger.info(
                        "Router detected site '%s', resolved to %s",
                        route.site_name, target_site_name,
                    )
                    all_lists = await self.sharepoint_repository.get_all_lists(site_id=target_site_id)
                    list_summaries = [
                        {
                            "id": lst.get("id"),
                            "name": lst.get("displayName"),
                            "description": lst.get("description", ""),
                        }
                        for lst in all_lists
                    ]

            logger.info(
                "Query intent: %s, resource_type: %s, site: %s",
                route.intent, route.resource_type, target_site_name or "default",
            )

            # ── Router list_id sanity check ───────────────────────────────────
            if route.list_id and route.intent == QueryIntent.SPECIFIC_DATA:
                import re as _re_san
                from src.infrastructure.services.smart_resource_discovery import (
                    _SYNONYMS as _SYN, _tokenise as _san_tokenise,
                )
                _sanity_match = next(
                    (l for l in list_summaries if l["id"] == route.list_id), None
                )
                if _sanity_match:
                    _ln_toks = _san_tokenise(_sanity_match.get("name") or "")
                    _qr_toks = _san_tokenise(question)
                    # Expand list-name tokens with synonyms
                    _exp_ln: set = set(_ln_toks)
                    for _t in _ln_toks:
                        for _syn in _SYN.get(_t, []):
                            _exp_ln |= _san_tokenise(_syn)
                    # Expand question tokens with synonyms
                    _exp_qr: set = set(_qr_toks)
                    for _t in _qr_toks:
                        for _syn in _SYN.get(_t, []):
                            _exp_qr |= _san_tokenise(_syn)
                    _has_overlap = bool(_ln_toks & _exp_qr or _qr_toks & _exp_ln)
                    if not _has_overlap:
                        logger.info(
                            "Router list_id sanity FAILED: '%s' doesn't match question tokens — "
                            "nullifying list_id so smart discovery runs across all sites",
                            _sanity_match.get("name"),
                        )
                        route = RouterResponse(
                            intent=route.intent,
                            resource_type=route.resource_type,
                            site_name=route.site_name,
                            semantic_target=route.semantic_target,
                            list_id=None,
                            filter_keywords=route.filter_keywords,
                            library_names=route.library_names,
                            search_query=route.search_query,
                            data_query=route.data_query,
                            is_meta_query=route.is_meta_query,
                        )

            # ── Metadata-describe: asking about current site ──────────────────
            if route.intent == QueryIntent.METADATA_DESCRIBE and route.resource_type == ResourceType.SITE:
                return await self._handle_site_info_query(question)

            # ── Search ────────────────────────────────────────────────────────
            if route.intent == QueryIntent.SEARCH:
                return await self._handle_search_query(route.search_query or question)

            # ── Sites listing ─────────────────────────────────────────────────
            if route.resource_type == ResourceType.SITE:
                return await self._handle_all_sites_query()

            # ── Pages ─────────────────────────────────────────────────────────
            if route.resource_type == ResourceType.PAGE:
                # Smart upgrade: content-seeking questions → PAGE_CONTENT
                from src.detection.routing.page_content_router import detect_page_content_upgrade
                if (
                    route.intent != QueryIntent.PAGE_CONTENT
                    and detect_page_content_upgrade(question)
                ):
                    route = RouterResponse(
                        intent=QueryIntent.PAGE_CONTENT,
                        resource_type=ResourceType.PAGE,
                        site_name=route.site_name,
                        semantic_target=route.semantic_target,
                        search_query=route.search_query,
                    )

                if route.intent == QueryIntent.PAGE_CONTENT:
                    return await self._handle_page_content_query(
                        question, target_site_id, target_site_name, concept_mapping=_mapping,
                        page_id=page_id, page_url=page_url, page_title=page_title,
                    )

                try:
                    if route.search_query:
                        pages = await self.sharepoint_repository.search_pages(
                            route.search_query, site_id=target_site_id
                        )
                        answer = f"Found **{len(pages)}** {'page' if len(pages) == 1 else 'pages'} matching '{route.search_query}':\n\n"
                        answer += "\n".join(
                            f"- **{p.get('title', p.get('name', 'Untitled'))}**" for p in pages
                        )
                        suggested = ["Show me all pages", "Show me details for a specific page"]
                    else:
                        pages = await self.sharepoint_repository.get_all_pages(site_id=target_site_id)
                        answer = f"There are **{len(pages)}** {'page' if len(pages) == 1 else 'pages'} in this site.\n\n"
                        answer += "\n".join(
                            f"- **{p.get('title', p.get('name', 'Untitled'))}**" for p in pages
                        )
                        suggested = ["Search for a page", "Show me details for the Home page"]
                    return DataQueryResult(
                        answer=answer,
                        data_summary={"page_count": len(pages)},
                        suggested_actions=suggested,
                    )
                except Exception as exc:
                    logger.error("Failed to query pages: %s", exc)
                    return DataQueryResult(
                        answer="I encountered an error retrieving pages from your site.",
                        suggested_actions=["Try again later", "Show me all lists"],
                    )

            # ── Metadata intents — current site only ─────────────────────────
            if route.intent == QueryIntent.METADATA_COUNT:
                return await self._handle_metadata_count(
                    question, all_lists, route, target_site_name, target_site_id, target_site_url
                )

            elif route.intent == QueryIntent.FILTERED_META:
                return await self._handle_filtered_meta(
                    question, all_lists, route, target_site_name, target_site_url,
                    site_id=target_site_id,
                )

            elif route.intent == QueryIntent.FULL_META:
                return await self._handle_full_meta(
                    all_lists, route, target_site_name, target_site_url,
                    site_id=target_site_id,
                )

            # ── Smart cross-resource discovery ────────────────────────────────
            if route.intent in self._RESOURCE_SPECIFIC_INTENTS and self._smart_discovery:
                discovery_result = await self._run_smart_discovery(
                    question=question,
                    route=route,
                    target_site_id=target_site_id,
                    target_site_name=target_site_name,
                    all_sites=all_sites,
                    site_ids=site_ids,
                    concept_mapping=_mapping,
                    page_id=page_id,
                    context_site_id=context_site_id,
                )
                if discovery_result is not None:
                    return discovery_result

            # ── Fallback: original intent routing (single-site, name-based) ──
            if route.intent == QueryIntent.LIBRARY_CONTENT:
                if route.library_names:
                    library_name = route.library_names[0]
                    all_libs = await self.sharepoint_repository.get_all_document_libraries(
                        site_id=target_site_id
                    )
                    matched_lib = next(
                        (lib for lib in all_libs if library_name.lower() in lib.get("displayName", "").lower()),
                        None,
                    )
                    if matched_lib:
                        return await self._handle_library_content_query(
                            question, matched_lib.get("id"), matched_lib.get("displayName")
                        )
                return DataQueryResult(
                    answer="I couldn't identify which library you're asking about. Please specify a library name.",
                    suggested_actions=["Show me all libraries"],
                )

            elif route.intent == QueryIntent.DOCUMENT_SEARCH:
                return await self._handle_document_search_query(route.search_query or question)

            elif route.intent == QueryIntent.DATA_EXTRACTION:
                data_query = route.data_query or question
                library_id = None
                library_name = None
                if route.library_names:
                    library_name = route.library_names[0]
                    all_libs = await self.sharepoint_repository.get_all_document_libraries(
                        site_id=target_site_id
                    )
                    matched_lib = next(
                        (lib for lib in all_libs if library_name.lower() in lib.get("displayName", "").lower()),
                        None,
                    )
                    if matched_lib:
                        library_id = matched_lib.get("id")
                return await self._handle_data_extraction_query(data_query, library_id, library_name)

            elif route.intent == QueryIntent.LIBRARY_COMPARISON:
                if route.library_names and len(route.library_names) >= 2:
                    return await self._handle_library_comparison_query(route.library_names)
                return DataQueryResult(
                    answer="I need at least two library names to compare. Please specify which libraries you'd like to compare.",
                    suggested_actions=["Show me all libraries"],
                )

            elif route.intent == QueryIntent.CONTENT_SUMMARY:
                if route.library_names:
                    library_name = route.library_names[0]
                    all_libs = await self.sharepoint_repository.get_all_document_libraries(
                        site_id=target_site_id
                    )
                    matched_lib = next(
                        (lib for lib in all_libs if library_name.lower() in lib.get("displayName", "").lower()),
                        None,
                    )
                    if matched_lib:
                        return await self._handle_content_summary_query(
                            matched_lib.get("id"), matched_lib.get("displayName")
                        )
                return DataQueryResult(
                    answer="I couldn't identify which library to summarize. Please specify a library name.",
                    suggested_actions=["Show me all libraries"],
                )

            elif route.intent == QueryIntent.PAGE_CONTENT:
                return await self._handle_page_content_query(
                    question, target_site_id, target_site_name, concept_mapping=_mapping,
                    page_id=page_id, page_url=page_url, page_title=page_title,
                )

            elif route.intent == QueryIntent.SPECIFIC_DATA:
                if not route.list_id:
                    # No exact list ID — try semantic/fuzzy discovery if smart discovery is available
                    topic = route.semantic_target or question
                    if self._smart_discovery:
                        logger.info(
                            "SPECIFIC_DATA has no list_id; running smart discovery for topic=%r",
                            topic,
                        )
                        discovery_result = await self._run_smart_discovery(
                            question=question,
                            route=route,
                            target_site_id=target_site_id,
                            target_site_name=target_site_name,
                            all_sites=all_sites,
                            site_ids=site_ids,
                            concept_mapping=_mapping,
                            page_id=page_id,
                            context_site_id=context_site_id,
                        )
                        if discovery_result is not None:
                            return discovery_result
                    # Smart discovery unavailable or returned nothing — ask for clarification
                    topic_hint = f" related to **{route.semantic_target}**" if route.semantic_target else ""
                    return DataQueryResult(
                        answer=(
                            f"I couldn't find a list{topic_hint} in your SharePoint site. "
                            "Could you clarify which list you'd like to query, or would you like me to show all available lists?"
                        ),
                        data_summary={"needs_location_hint": True},
                        suggested_actions=[
                            "Show me all lists",
                            "Show me all document libraries",
                            "What sites do we have?",
                        ],
                    )
                matched_list = next((l for l in list_summaries if l["id"] == route.list_id), None)
                if not matched_list:
                    return DataQueryResult(
                        answer="I couldn't find the list you're referring to.",
                        suggested_actions=["Show me all lists"],
                    )
                return await self._handle_specific_data_query(
                    question, matched_list, all_lists, target_site_id, target_site_name
                )

            # Default fallback
            _result = await self._handle_full_meta(all_lists, route, target_site_name, site_id=target_site_id)
            if _mapping.concepts:
                import asyncio as _asyncio2
                _asyncio2.create_task(
                    ConceptMemory().record(_original_question.lower(), _mapping.concepts)
                )
            return _result

        except Exception as exc:
            logger.error("Failed to execute data query: %s", exc)
            raise DataQueryException(f"Failed to execute data query reasoning loop: {exc}")
        finally:
            _latency = (_time.monotonic() - _start_ts) * 1000
            log_query_trace(
                site_id=context_site_id or self.site_id or "",
                page_id=page_id,
                intent=_telemetry_intent,
                resources_accessed=_telemetry_resources,
                page_hit=_telemetry_page_hit,
                fallback_used=_telemetry_fallback,
                latency_ms=round(_latency, 2),
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Smart discovery orchestration
    # ─────────────────────────────────────────────────────────────────────────

    async def _run_smart_discovery(
        self, question: str, route, target_site_id, target_site_name, all_sites, site_ids=None,
        concept_mapping=None,
        page_id: Optional[str] = None,
        context_site_id: Optional[str] = None,
    ):
        """Run the smart discovery pipeline and return a DataQueryResult, or None to fall through."""
        from src.infrastructure.config import settings as _settings

        if target_site_id:
            discovery_site_ids = [target_site_id]
        elif site_ids:
            discovery_site_ids = list(site_ids)[: _settings.MAX_DISCOVERY_SITES]
        else:
            discovery_site_ids = [
                s.get("id") for s in all_sites if s.get("id")
            ][: _settings.MAX_DISCOVERY_SITES]

        if not discovery_site_ids:
            return None

        logger.info(
            "Smart discovery: querying %d site(s) for intent=%s",
            len(discovery_site_ids),
            route.intent,
        )

        # Intents that prefer document libraries over lists
        _LIBRARY_INTENTS = {
            QueryIntent.LIBRARY_CONTENT,
            QueryIntent.DOCUMENT_SEARCH,
            QueryIntent.DATA_EXTRACTION,
            QueryIntent.CONTENT_SUMMARY,
            QueryIntent.LIBRARY_COMPARISON,
        }
        # Intents that prefer lists over libraries
        _LIST_INTENTS = {QueryIntent.SPECIFIC_DATA}

        preferred_type: Optional[str] = None
        if route.intent in _LIBRARY_INTENTS:
            preferred_type = "library"
        elif route.intent in _LIST_INTENTS:
            preferred_type = "list"

        # Use semantic_target as a focused ranking signal ONLY when its words
        # actually overlap with the original question.  When the router was given
        # only the default-site list summaries it can pick the wrong resource
        # (e.g. "Meeting Notes" for a "kudos" query) — in that case fall back to
        # the original question which carries the real user intent.
        if getattr(route, "semantic_target", None):
            import re as _re_sd
            _target_tokens = set(_re_sd.findall(r"[a-z0-9]+", route.semantic_target.lower()))
            _q_tokens_sd = set(_re_sd.findall(r"[a-z0-9]+", question.lower()))
            ranking_question = (
                route.semantic_target if _target_tokens & _q_tokens_sd else question
            )
        else:
            ranking_question = question

        try:
            candidates = await self._smart_discovery.discover_all_resources(discovery_site_ids)
            if not candidates:
                from src.infrastructure.services.duplicate_name_resolver import DuplicateNameResolver as _DNR
                return DataQueryResult(
                    answer=_DNR.build_not_found_prompt(question),
                    data_summary={"needs_location_hint": True},
                    suggested_actions=[
                        "Show me all lists",
                        "Show me all document libraries",
                        "What sites do we have?",
                    ],
                )

            ranked = await self._smart_discovery.rank_candidates(
                ranking_question, candidates,
                preferred_resource_type=preferred_type,
                context_page_id=page_id,
                context_site_id=context_site_id,
            )
            if not ranked:
                return None

            # Phase 3: Clarification check — zero AI tokens
            try:
                from src.infrastructure.services.clarification_engine import ClarificationEngine
                _clar_result = ClarificationEngine().evaluate(concept_mapping, ranked)
                if _clar_result.needs_clarification:
                    logger.info(
                        "Clarification triggered: reason=%s", _clar_result.reason
                    )
                    return DataQueryResult(
                        answer=_clar_result.question,
                        data_summary={"clarification_reason": _clar_result.reason},
                        suggested_actions=["Yes, that one", "No, show me all options"],
                        clarification_candidates=ranked[:10],
                    )
            except Exception:
                pass  # clarification is best-effort

            # Duplicate detection
            duplicates = self._duplicate_resolver.find_duplicates(ranked[:10], threshold=1)
            if duplicates:
                top_dup = duplicates[0]
                clarification = self._duplicate_resolver.build_clarification_prompt(top_dup)
                logger.info(
                    "Duplicate name '%s' found in %d sites — surfacing clarification",
                    top_dup.normalised_title,
                    len({c.site_id for c in top_dup.candidates}),
                )
                return DataQueryResult(
                    answer=clarification,
                    data_summary={"duplicate_name": top_dup.normalised_title},
                    suggested_actions=[
                        f"{i+1}. {c.site_name}" for i, c in enumerate(top_dup.candidates)
                    ],
                    clarification_candidates=top_dup.candidates,
                )

            best_score = ranked[0].relevance_score
            if best_score < _settings.SEARCH_FALLBACK_THRESHOLD:
                logger.info(
                    "All candidates score below %.2f — triggering Graph Search fallback",
                    _settings.SEARCH_FALLBACK_THRESHOLD,
                )
                return await self._handle_graph_search_fallback(question)

            winner = await self._smart_discovery.select_best_candidate(ranking_question, ranked)
            if winner is None:
                return None

            logger.info(
                "Smart discovery winner: '%s' (%s) in site '%s' (score=%.3f)",
                winner.title, winner.resource_type, winner.site_name, winner.relevance_score,
            )

            # Phase 13: find sibling resources for richer context
            siblings = []
            try:
                siblings = await self._smart_discovery.find_sibling_resources(winner, candidates)
                if siblings:
                    logger.info("Sibling resources found: %s", [s.title for s in siblings])
            except Exception as _sib_exc:
                logger.debug("Sibling discovery failed: %s", _sib_exc)

            if winner.resource_type == "list":
                matched_list = {"id": winner.resource_id, "name": winner.title, "description": ""}
                result = await self._handle_specific_data_query(
                    question, matched_list, [], winner.site_id, winner.site_name,
                    resource_web_url=winner.web_url,
                    sibling_resources=siblings,
                )
            else:
                result = await self._handle_library_content_query(
                    question, winner.resource_id, winner.title,
                    site_id=winner.site_id, site_name=winner.site_name,
                    resource_web_url=winner.web_url,
                    sibling_resources=siblings,
                )

            result.source_site_name = winner.site_name
            result.source_site_url = winner.site_url
            result.source_resource_type = winner.resource_type
            return result

        except Exception as exc:
            logger.warning("Smart discovery failed (%s); falling through to legacy routing", exc)
            return None


# ─────────────────────────────────────────────────────────────────────────────
# Context block helpers (Phase 9)
# ─────────────────────────────────────────────────────────────────────────────

import json as _json


def _build_context_block(ctx: "NormalizedContext") -> str:
    """Serialise NormalizedContext as a JSON block injected at the TOP of prompts."""
    if not ctx.site_id and not ctx.page_id:
        return ""
    data = {
        "context": {
            "site": {"id": ctx.site_id, "url": ctx.site_url},
            "page": {"id": ctx.page_id, "url": ctx.page_url, "title": ctx.page_title},
            "flags": {"force_page_priority": bool(ctx.page_id)},
        }
    }
    return f"[CURRENT CONTEXT]\n{_json.dumps(data, indent=2)}\n\n"


def _build_reply_anchor(ctx: "NormalizedContext") -> str:
    """Short reminder injected at the BOTTOM of prompts to counter mid-prompt amnesia."""
    if not ctx.page_id:
        return ""
    label = ctx.page_title or ctx.page_id
    return (
        f"\nREPLY PREFERENCE: Ground your answer in the specific data from \"{label}\""
        f" (id={ctx.page_id}) found in the [CURRENT CONTEXT] block above.\n"
    )
