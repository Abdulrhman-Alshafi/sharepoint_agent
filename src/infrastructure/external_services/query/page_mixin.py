"""Mixin providing page web part content query handler for AIDataQueryService."""

import hashlib
import logging
from typing import Any, Dict, List, Optional

from src.domain.entities import DataQueryResult
from src.domain.entities.query import QuerySource
from src.infrastructure.external_services.query.prompts import QUERY_SYSTEM_PROMPT
from src.infrastructure.schemas.query_schemas import DataQueryResponseModel
from src.infrastructure.services.embedding_service import EmbeddingService
from src.infrastructure.services.section_index import SectionIndexService
from src.infrastructure.services.sharepoint.webpart_reader_service import WebPartReaderService
from src.infrastructure.services.webpart_index import WebPartIndexService
from src.infrastructure.services.context_normalizer import normalize_context_from_fields

logger = logging.getLogger(__name__)

# Hard limits to avoid overwhelming the LLM context window
_TOP_K_PAGES = 5
_TOP_K_SECTIONS = 10  # Phase 2: sections shown to LLM instead of full pages
_MAX_CHARS_PER_PAGE = 8000
_MAX_CHARS_PER_SECTION = 1500  # each section snippet in LLM context
_MIN_SCORE = 1  # pages must have at least this relevance score to be included


class PageQueryMixin:
    """Handler for page_content queries — reads SharePoint page web parts.

    Requires *self* to provide:
        self.sharepoint_repository  – SharePointRepository
        self.graph_client           – authenticated Graph client
        self.site_id                – default site ID
        self.client, self.model     – instructor AI client
    """

    # ─────────────────────────────────────────────────────────────────────────
    # Main handler
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_page_content_query(
        self,
        question: str,
        site_id: Optional[str],
        site_name: Optional[str],
        concept_mapping=None,
        page_id: Optional[str] = None,
        page_url: Optional[str] = None,
        page_title: Optional[str] = None,
    ) -> DataQueryResult:
        """Answer a question by reading web part content from SharePoint pages.

        Flow:
        1. Get all pages (metadata only) for the site.
        2. Pre-filter via WebPartIndex LIKE search on cached text.
        3. Score candidates by keyword relevance; keep top-K=5.
        4. Refresh stale cache entries via WebPartReaderService.
        5. Build truncated LLM context string.
        6. Call instructor AI and return DataQueryResult.

        Fallback 1: No pages in site → friendly message.
        Fallback 2: All extractions fail → list page titles only.
        """
        effective_site_id = site_id or self.site_id
        graph_client = self.graph_client
        reader = WebPartReaderService(self.graph_client)
        index = WebPartIndexService()
        section_index = SectionIndexService()
        embedder = EmbeddingService()

        # ── Step 1: Get all page metadata ────────────────────────────────────
        try:
            all_pages = await self.sharepoint_repository.get_all_pages(
                site_id=effective_site_id
            )
        except Exception as exc:
            logger.error("Failed to fetch pages for site %s: %s", effective_site_id, exc)
            all_pages = []

        if not all_pages:
            site_ctx = f" in the **{site_name}** site" if site_name else ""
            return DataQueryResult(
                answer=f"No pages were found{site_ctx}. There is no page content to search.",
                suggested_actions=["Show me all lists", "Show me all libraries"],
            )

        # ── Step 2: Pre-filter via cached index ──────────────────────────────
        question_lower = question.lower()
        cached_matches = await index.search_pages(question_lower, site_id=effective_site_id)
        cached_ids = {p["page_id"] for p in cached_matches}

        # Build full candidate list: cached hits first, then remaining pages
        cached_pages = [p for p in all_pages if (p.get("id") or "") in cached_ids]
        uncached_pages = [p for p in all_pages if (p.get("id") or "") not in cached_ids]
        candidates = cached_pages + uncached_pages

        # ── Step 3: Score by keyword relevance + concept bonus, keep top-K ──
        keywords = [w for w in question_lower.split() if len(w) > 3]
        concept_words: set = set()
        if concept_mapping and getattr(concept_mapping, "expanded_tokens", None):
            concept_words = concept_mapping.expanded_tokens

        scored: List[tuple] = []
        for page in candidates:
            title = (page.get("title") or page.get("name") or "").lower()
            kw_score = sum(1 for kw in keywords if kw in title)
            concept_bonus = sum(0.5 for cw in concept_words if cw in title)
            if (page.get("id") or "") in cached_ids:
                kw_score += 3
            scored.append((kw_score + concept_bonus, page))
        scored.sort(key=lambda x: x[0], reverse=True)
        top_pages = [page for score, page in scored[:_TOP_K_PAGES] if score >= _MIN_SCORE]
        if not top_pages:
            top_pages = [page for _, page in scored[:_TOP_K_PAGES]]

        # ── Priority page: current page goes to top regardless of score ──────
        _priority_page = None
        _root_home = (page_id or "").upper() == "ROOT_HOME"
        if page_id and not _root_home:
            _priority_page = next((p for p in all_pages if p.get("id") == page_id), None)
        elif page_url:
            _norm_url = page_url.rstrip("/").lower()
            _priority_page = next(
                (p for p in all_pages if p.get("webUrl", "").rstrip("/").lower() == _norm_url),
                None,
            )
        if not _priority_page and _root_home:
            # Match site root or Home.aspx
            _priority_page = next(
                (
                    p for p in all_pages
                    if p.get("webUrl", "").rstrip("/").lower().endswith("/home")
                    or "home.aspx" in p.get("webUrl", "").lower()
                ),
                None,
            )

        if _priority_page:
            _pri_id = _priority_page.get("id") or ""
            logger.info("Priority page pinned: id=%s title=%s", _pri_id, _priority_page.get("title"))
            top_pages = [_priority_page] + [
                p for p in top_pages if p.get("id") != _pri_id
            ][:_TOP_K_PAGES - 1]

        # ── Step 4: Refresh stale cache entries + index sections ─────────────
        for page in top_pages:
            _cur_page_id = page.get("id") or page.get("eTag", "").strip('"')
            if not _cur_page_id:
                continue
            _cur_page_title = page.get("title") or page.get("name") or "Untitled"
            _cur_page_url = page.get("webUrl", "")
            # Phase 7: pre-compute fingerprint from canvasLayout BEFORE extraction
            _fingerprint: Optional[str] = None
            try:
                import json as _json_fp
                _canvas_data = await reader.get_page_webparts(effective_site_id, _cur_page_id)
                _fingerprint = hashlib.sha256(
                    _json_fp.dumps(_canvas_data, sort_keys=True).encode()
                ).hexdigest()
            except Exception:
                pass
            stale = await index.is_page_stale(_cur_page_id, current_checksum=_fingerprint)

            # Also force a refresh when the cached text has no live item data yet
            # (i.e. was indexed before the list-enrichment feature was added),
            # OR when a countdown web part was indexed without its event title
            # (indexed before the richer extraction was added).
            if not stale:
                _cached_entry = await index.get_indexed_page(_cur_page_id)
                _cached_text = (_cached_entry or {}).get("extracted_text", "")
                _has_live_items = "Items:\n" in _cached_text or "- **" in _cached_text
                # A web part "has a list" if it has a GUID in props OR its
                # component ID is in the known custom-list map.
                from src.infrastructure.services.sharepoint.webpart_reader_service import (
                    _WEBPART_COMPONENT_LIST_MAP,
                )

                def _wp_has_list(wp: dict) -> bool:
                    if reader._extract_list_id_from_wp(wp):
                        return True
                    raw_cid = (
                        wp.get("webPartType")
                        or (wp.get("data") or {}).get("webPartType")
                        or ""
                    ).lower()
                    return raw_cid in _WEBPART_COMPONENT_LIST_MAP

                _has_list_wp = _canvas_data and any(_wp_has_list(wp) for wp in _canvas_data)
                if _has_list_wp and not _has_live_items:
                    logger.info(
                        "Page %s has list-backed web parts but no live items in cache — forcing re-index",
                        _cur_page_id,
                    )
                    stale = True
                # Countdown web parts: force re-index if cached text doesn't include
                # the "[Countdown Timer]" label added by the schema-agnostic extractor.
                # webPartType may be at the top level OR inside data — check both.
                if not stale and _canvas_data:
                    _has_countdown_wp = any(
                        "countdown" in (
                            (wp.get("webPartType") or "")
                            + ((wp.get("data") or {}).get("webPartType") or "")
                        ).lower()
                        for wp in _canvas_data
                    )
                    if _has_countdown_wp and "[Countdown Timer]" not in _cached_text:
                        logger.info(
                            "Page %s has countdown web part without [Countdown Timer] label in cache — forcing re-index",
                            _cur_page_id,
                        )
                        stale = True

            if stale:
                wps = _canvas_data if _fingerprint else await reader.get_page_webparts(effective_site_id, _cur_page_id)
                texts = [reader._extract_text_from_webpart(wp) for wp in wps]

                # ── Live list-item enrichment ─────────────────────────────────
                # For web parts that reference a SharePoint list (Announcements,
                # News, Highlighted Content, Events, List, etc.), fetch the
                # actual items and append them to the relevant section text so
                # the LLM sees real data instead of just web part configuration.
                try:
                    _list_enrichments = await reader.enrich_webparts_with_list_items(
                        effective_site_id, wps
                    )
                    if _list_enrichments:
                        from src.infrastructure.services.sharepoint.webpart_reader_service import (
                            _WEBPART_COMPONENT_LIST_MAP,
                        )
                        _has_component_map_wps = any(
                            (
                                wp.get("webPartType")
                                or (wp.get("data") or {}).get("webPartType")
                                or ""
                            ).lower() in _WEBPART_COMPONENT_LIST_MAP
                            for wp in wps
                        )
                        _component_name_to_id: dict = {}
                        if _has_component_map_wps:
                            try:
                                from src.infrastructure.services.query_resilience import with_retry
                                _lists_resp = await with_retry(
                                    lambda: graph_client.get(
                                        f"/sites/{effective_site_id}/lists"
                                        f"?$select=id,displayName,name&$top=500"
                                    ),
                                    max_attempts=2, delay=0.5,
                                    label="page_mixin list_name_cache",
                                )
                                for _lst in _lists_resp.get("value") or []:
                                    _lid_val = _lst.get("id", "")
                                    _component_name_to_id[_lst.get("displayName", "").lower()] = _lid_val
                                    _component_name_to_id[_lst.get("name", "").lower()] = _lid_val
                            except Exception as _cache_exc:
                                logger.debug("page_mixin: list name cache failed: %s", _cache_exc)

                        def _resolve_wp_list_id(wp: dict) -> Optional[str]:
                            """Return the list GUID for this web part via GUID scan or component map."""
                            lid = reader._extract_list_id_from_wp(wp)
                            if lid:
                                return lid
                            raw_cid = (
                                wp.get("webPartType")
                                or (wp.get("data") or {}).get("webPartType")
                                or ""
                            ).lower()
                            known_names = _WEBPART_COMPONENT_LIST_MAP.get(raw_cid)
                            if known_names and _component_name_to_id:
                                for lname in known_names:
                                    resolved = _component_name_to_id.get(lname.lower())
                                    if resolved:
                                        return resolved
                            return None

                        for _wp_idx, _wp in enumerate(wps):
                            _lid = _resolve_wp_list_id(_wp)
                            if _lid and _lid in _list_enrichments:
                                _enrichment_block = _list_enrichments[_lid]
                                _existing = texts[_wp_idx] if _wp_idx < len(texts) else ""
                                texts[_wp_idx] = (
                                    (_existing + "\n\n" if _existing else "")
                                    + "Items:\n" + _enrichment_block
                                )
                except Exception as _enrich_exc:
                    logger.debug("List enrichment failed for page %s: %s", _cur_page_id, _enrich_exc)

                extracted = "\n\n".join(t for t in texts if t)
                await index.index_page(
                    page_id=_cur_page_id,
                    site_id=effective_site_id,
                    page_title=_cur_page_title,
                    page_url=_cur_page_url,
                    extracted_text=extracted,
                    webpart_count=len(wps),
                )
                # Phase 2: Index each web part as a section
                try:
                    for wp_idx, wp in enumerate(wps):
                        section_id = f"{_cur_page_id}__wp_{wp_idx}"
                        meta = reader.get_section_metadata(wp)
                        content = texts[wp_idx] if wp_idx < len(texts) else ""
                        if content:
                            checksum = hashlib.sha256(content.encode()).hexdigest()
                            if await section_index.is_section_stale(section_id, checksum):
                                await section_index.index_section(
                                    section_id=section_id,
                                    page_id=_cur_page_id,
                                    page_title=_cur_page_title,
                                    site_id=effective_site_id,
                                    section_title=meta["section_title"],
                                    webpart_type=meta["webpart_type"],
                                    content_text=content,
                                    checksum=checksum,
                                )
                except Exception as sec_exc:
                    logger.debug("Phase 2 section indexing failed: %s", sec_exc)

        # ── Step 5a: Attempt semantic retrieval from SectionIndex ─────────────
        query_embedding = await embedder.embed_text(question)
        semantic_sections: List[Dict[str, Any]] = []
        if query_embedding:
            semantic_sections = await section_index.search_sections_semantic(
                query_embedding, site_id=effective_site_id, top_k=_TOP_K_SECTIONS
            )
        # Fallback: keyword section search
        if not semantic_sections:
            semantic_sections = await section_index.search_sections_keyword(
                question_lower, site_id=effective_site_id, top_k=_TOP_K_SECTIONS
            )

        # ── Step 5b: Build LLM context ───────────────────────────────────────
        context_parts: List[str] = []
        fallback_titles: List[str] = []

        if semantic_sections:
            # Phase 2 path: use section-level snippets — much smaller context = fewer tokens
            for sec in semantic_sections:
                page_title = sec.get("page_title") or "Untitled"
                sec_title = sec.get("section_title") or ""
                text = (sec.get("content_text") or "")[:_MAX_CHARS_PER_SECTION]
                header = f"## {page_title}" + (f" › {sec_title}" if sec_title else "")
                context_parts.append(f"{header}\n{text}")
                fallback_titles.append(page_title)
        else:
            # Phase 1 / legacy path: full page text
            for page in top_pages:
                page_id = page.get("id") or page.get("eTag", "").strip('"')
                page_title = page.get("title") or page.get("name") or "Untitled"
                page_url = page.get("webUrl", "")
                fallback_titles.append(page_title)
                cached = await index.get_indexed_page(page_id) if page_id else None
                text = (cached or {}).get("extracted_text", "") or ""
                if not text:
                    continue
                truncated = text[:_MAX_CHARS_PER_PAGE]
                if len(text) > _MAX_CHARS_PER_PAGE:
                    truncated += "\n... [content truncated]"
                link = f" ({page_url})" if page_url else ""
                context_parts.append(f"## Page: {page_title}{link}\n{truncated}")

        if not context_parts:
            # Fallback: no extracted text available — list titles
            titles_md = "\n".join(f"- **{t}**" for t in fallback_titles) or "No pages found."
            site_ctx = f" in the **{site_name}** site" if site_name else ""
            return DataQueryResult(
                answer=(
                    f"I found the following pages{site_ctx} but could not read their "
                    f"web part content:\n\n{titles_md}\n\n"
                    "Please make sure the pages have published content."
                ),
                data_summary={"page_count": len(all_pages), "readable_count": 0},
                suggested_actions=["Show me all pages", "Show me all lists"],
            )

        page_context = "\n\n---\n\n".join(context_parts)
        site_ctx = f" in the **{site_name}** site" if site_name else ""
        showing_note = (
            f"(Showing content from top {len(context_parts)} of {len(all_pages)} "
            f"pages most relevant to your question)"
        )

        intent_hint = ""
        if concept_mapping and getattr(concept_mapping, "concepts", None):
            intent_hint = f"[User intent: {', '.join(concept_mapping.concepts)}]\n\n"

        # ── Phase 10 pre-verification: check section coverage BEFORE AI call ─
        _norm_ctx = normalize_context_from_fields(
            context_site_id=effective_site_id,
            page_id=page_id,
            page_url=page_url,
            page_title=page_title,
        )
        _page_sections = [
            s for s in semantic_sections if page_id and s.get("page_id") == page_id
        ] if page_id else semantic_sections

        _page_context_available = bool(_page_sections)
        if page_id and not _page_sections:
            logger.warning(
                "Pre-verification: no sections indexed for page_id=%s — broadening to site level",
                page_id,
            )
            _page_sections = semantic_sections
            _page_context_available = False

        # ── Phase 9: Structured context block (dual injection) ────────────────
        try:
            from src.infrastructure.external_services.query.service import (
                _build_context_block,
                _build_reply_anchor,
            )
            _ctx_block = _build_context_block(_norm_ctx)
            _reply_anchor = _build_reply_anchor(_norm_ctx) if _page_context_available else ""
        except Exception:
            _ctx_block = ""
            _reply_anchor = ""

        data_prompt = (
            f"{QUERY_SYSTEM_PROMPT}\n\n"
            f"{_ctx_block}"
            f"{intent_hint}"
            f"SharePoint Page Content{site_ctx}:\n"
            f"{showing_note}\n\n"
            f"{page_context}\n\n"
            f"User Question: {question}"
            f"{_reply_anchor}"
        )

        # ── Step 6: AI call ──────────────────────────────────────────────────
        # Collect sources from sections/pages used
        _sources: List[QuerySource] = []
        _seen_source_ids: set = set()
        if semantic_sections:
            for _s in semantic_sections:
                _pid = _s.get("page_id") or ""
                if _pid and _pid not in _seen_source_ids:
                    _seen_source_ids.add(_pid)
                    _sources.append(QuerySource(
                        type="page",
                        id=_pid,
                        title=_s.get("page_title") or "",
                        url="",
                    ))
        else:
            for _pg in top_pages:
                _pid = _pg.get("id") or ""
                if _pid and _pid not in _seen_source_ids:
                    _seen_source_ids.add(_pid)
                    _sources.append(QuerySource(
                        type="page",
                        id=_pid,
                        title=_pg.get("title") or _pg.get("name") or "",
                        url=_pg.get("webUrl") or "",
                    ))

        try:
            kwargs = {
                "messages": [{"role": "user", "content": data_prompt}],
                "response_model": DataQueryResponseModel,
            }
            if self.model:
                kwargs["model"] = self.model
            final_response = self.client.chat.completions.create(**kwargs)
            return DataQueryResult(
                answer=final_response.answer,
                data_summary={
                    "pages_analyzed": len(context_parts),
                    "total_pages": len(all_pages),
                },
                source_list="Pages",
                suggested_actions=final_response.suggested_actions,
                sources=_sources,
            )
        except Exception as exc:
            logger.error("Page content AI call failed: %s", exc)
            return DataQueryResult(
                answer=(
                    f"I found page content but encountered an error generating "
                    f"the answer: {exc}"
                ),
                suggested_actions=["Try a more specific question", "Show me all pages"],
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Utility: score a set of pages for relevance (shared with discovery)
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _score_page(page: Dict[str, Any], keywords: List[str]) -> int:
        """Return a keyword-overlap relevance score for a page."""
        title = (page.get("title") or page.get("name") or "").lower()
        return sum(1 for kw in keywords if kw in title)
