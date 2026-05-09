"""Mixin providing specific-data and search-fallback handlers for AIDataQueryService."""

import json
import logging
from typing import List, Optional

from src.domain.entities import DataQueryResult
from src.domain.value_objects.resource_candidate import ResourceCandidate
from src.infrastructure.external_services.query.prompts import QUERY_SYSTEM_PROMPT
from src.infrastructure.schemas.query_schemas import DataQueryResponseModel
from src.infrastructure.services.list_item_index import ListItemIndexService

logger = logging.getLogger(__name__)


class DataQueryMixin:
    """Handlers for specific_data and Graph-search fallback.

    Requires *self* to provide:
        self.list_repository
        self.site_repository
        self.search_service  – SearchService
        self.client, self.model – instructor AI client
        self._last_list_id, self._last_list_name   – context tracking
        self._last_site_id,  self._last_site_name
    """

    async def _handle_specific_data_query(
        self,
        question: str,
        matched_list: dict,
        all_lists: list,
        site_id: str = None,
        site_name: str = None,
        resource_web_url: str = None,
        sibling_resources: Optional[List[ResourceCandidate]] = None,
    ) -> DataQueryResult:
        """Handle queries about data within a specific list."""
        target_list_id = matched_list["id"]
        target_list_name = matched_list["name"]
        target_list_url = (
            next((l.get("webUrl", "") for l in all_lists if l.get("id") == target_list_id), "")
            or resource_web_url
            or ""
        )
        site_context = f" in the **{site_name}** site" if site_name else ""
        # Guard: never expose a bare GUID as a site name in user-facing messages
        import re as _re_dm
        if site_name and _re_dm.match(r"^[0-9a-fA-F]{8}-", site_name):
            site_context = ""
        logger.info(
            "Querying data from list: '%s'%s (id=%s)",
            target_list_name,
            f" in {site_name}" if site_name else "",
            target_list_id,
        )

        items_raw = await self.list_repository.get_list_items(target_list_id, site_id=site_id)
        items = [item.get("fields", {}) for item in items_raw]

        # ── Resolve personOrGroup LookupId fields → display names ─────────
        # SharePoint returns person fields as e.g. {"EmployeeLookupId": 42}
        # which is meaningless to the AI.  Resolve to human-readable names.
        try:
            from src.infrastructure.services.person_field_resolver import resolve_person_fields
            _columns = await self.list_repository.get_list_columns(
                target_list_id, site_id=site_id
            )
            items = await resolve_person_fields(
                items, _columns, self.graph_client,
                site_id or self.site_id,
            )
        except Exception as _pf_err:
            logger.debug("Person field resolution skipped (non-fatal): %s", _pf_err)

        # ── Cache result for future requests ──────────────────────────
        try:
            _index = ListItemIndexService()
            await _index.index_list(target_list_id, site_id or "", target_list_name, items)
        except Exception:
            pass  # caching failure is non-fatal

        # Save context even for empty lists
        self._last_list_id = target_list_id
        self._last_list_name = target_list_name
        self._last_site_id = site_id
        self._last_site_name = site_name

        if len(items) == 0:
            # Never expose the internal list name — it may be a camelCase identifier
            # like 'KudosComments' that the user never configured and doesn't recognise.
            return DataQueryResult(
                answer=(
                    "There are currently no items matching your request. "
                    "Would you like me to help you add some data?"
                ),
                data_summary={"items_analyzed": 0, "list_empty": True},
                source_list=target_list_name,
                resource_link=target_list_url,
                suggested_actions=[
                    "Add some sample items",
                    "Show me all available lists",
                    "What else can I help you with?",
                ],
            )

        # ── Document library detection ──────────────────────────────────
        # If the matched "list" is actually a document library, the items
        # only contain file metadata (name, size, modified date) — NOT the
        # content inside the files.  Any specific question about a library's
        # data requires reading the actual files, so we always redirect to
        # _handle_data_extraction_query which downloads and parses them.
        _DOC_LIBRARY_FIELDS = {"FileLeafRef", "File_x0020_Size", "FileSizeDisplay", "DocIcon"}
        is_document_library = any(
            _DOC_LIBRARY_FIELDS & set(item.keys()) for item in items[:3]
        )
        if is_document_library:
            logger.info(
                "Detected document library '%s' — redirecting to data extraction "
                "for file content reading",
                target_list_name,
            )
            return await self._handle_data_extraction_query(
                question, target_list_id, target_list_name
            )

        # ── Top-K filtering: score items by keyword relevance ─────────────
        _keywords = [w for w in question.lower().split() if len(w) > 3]
        _TOP_K = 50
        if _keywords and len(items) > _TOP_K:
            def _item_score(item: dict) -> int:
                item_str = json.dumps(item).lower()
                return sum(1 for kw in _keywords if kw in item_str)
            items = sorted(items, key=_item_score, reverse=True)[:_TOP_K]
            _showing_prefix = f"Showing top {len(items)} of {len(items_raw)} items most relevant to your question.\n\n"
        else:
            _showing_prefix = ""

        # Truncate total context at 12000 chars; siblings trimmed first
        _MAIN_BUDGET = 12000
        _context_str = str(items)
        _sibling_blocks = ""
        if sibling_resources:
            _sib_parts = []
            for _sib in sibling_resources:
                try:
                    _sib_items_raw = await self.list_repository.get_list_items(
                        _sib.resource_id, site_id=_sib.site_id
                    )
                    _sib_items = [i.get("fields", {}) for i in _sib_items_raw]
                    _sib_str = str(_sib_items)[:2000]
                    _sib_parts.append(f"\n\n--- Related list: '{_sib.title}' ---\n{_sib_str}")
                except Exception:
                    pass
            _sibling_blocks = "".join(_sib_parts)

        _total = len(_context_str) + len(_sibling_blocks)
        if _total > _MAIN_BUDGET:
            # trim siblings first
            _available_for_siblings = max(0, _MAIN_BUDGET - len(_context_str))
            _sibling_blocks = _sibling_blocks[:_available_for_siblings]
        if len(_context_str) > _MAIN_BUDGET:
            _context_str = _context_str[:_MAIN_BUDGET] + "..."

        data_prompt = (
            f"{QUERY_SYSTEM_PROMPT}\n\n"
            f"{_showing_prefix}"
            f"Data from list '{target_list_name}':\n{_context_str}"
            f"{_sibling_blocks}\n\n"
            f"User Question: {question}"
        )
        kwargs = {
            "messages": [{"role": "user", "content": data_prompt}],
            "response_model": DataQueryResponseModel,
        }
        if self.model:
            kwargs["model"] = self.model
        final_response = self.client.chat.completions.create(**kwargs)

        logger.info(
            "Saved query context: list=%s, site=%s", target_list_name, site_name or "default"
        )
        return DataQueryResult(
            answer=final_response.answer,
            data_summary={
                "items_analyzed": len(items),
                "sibling_lists_included": [s.title for s in (sibling_resources or [])],
            },
            source_list=target_list_name,
            resource_link=target_list_url,
            suggested_actions=final_response.suggested_actions,
        )

    async def _handle_graph_search_fallback(self, question: str) -> DataQueryResult:
        """Use Microsoft Graph Search as a fallback when no candidate is confident."""
        try:
            hits = await self.search_service.search_sharepoint(
                question, entity_types=["listItem", "driveItem"]
            )
            if not hits:
                return DataQueryResult(
                    answer="I couldn't find any data related to your question across all SharePoint resources.",
                    suggested_actions=[
                        "Try a different search term",
                        "Show me all lists",
                        "Show me all document libraries",
                    ],
                )

            lines = []
            for hit in hits[:10]:
                resource = hit.get("resource", {})
                name = resource.get("name") or resource.get("fields", {}).get("Title") or "Untitled"
                web_url = resource.get("webUrl", "")
                summary = hit.get("summary", "")
                if web_url:
                    lines.append(
                        f"- **[{name}]({web_url})** — {summary}" if summary else f"- **[{name}]({web_url})**"
                    )
                else:
                    lines.append(f"- **{name}**" + (f" — {summary}" if summary else ""))

            answer = (
                f"I searched across all SharePoint resources and found **{len(hits)}** related result(s):\n\n"
                + "\n".join(lines)
            )
            return DataQueryResult(
                answer=answer,
                data_summary={"search_hits": len(hits)},
                suggested_actions=[
                    "Show me more details about one of these results",
                    "Try a more specific question",
                ],
            )
        except Exception as exc:
            logger.error("Graph Search fallback failed: %s", exc)
            return DataQueryResult(
                answer="I encountered an error searching across SharePoint. Please try rephrasing your question.",
                suggested_actions=["Show me all lists", "Show me all document libraries"],
            )
