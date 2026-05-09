"""Clarification and search-hint resolution service.

Handles disambiguation when the query pipeline finds the same resource
in multiple sites, and re-runs queries scoped to a specific location
when the user provides a hint.

No FastAPI dependencies.
"""

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def resolve_clarification_pick(
    user_msg: str,
    candidates: List[Any],
    clarification_reason: str = "",
) -> Optional[Any]:
    """Match the user's reply to one of the pending clarification candidates.

    Handles:
    - Numeric choice: "1", "2" → index into candidates list.
    - Site-name match: "Optimum Partners Portal" ↔ candidate.site_name.
    - Resource-title match: candidate.title appears in the user message.
    - Resource-type match: user says "list", "library", or "page" during a
      multi-type tie disambiguation.

    Candidates can be dicts (from Redis deserialization) or objects with attributes.
    Returns the matched candidate, or None if no confident match.
    """
    msg_stripped = user_msg.strip()
    msg_lower = msg_stripped.lower()

    def _get(c, attr, default=""):
        """Get attribute from dict or object."""
        if isinstance(c, dict):
            return c.get(attr, default)
        return getattr(c, attr, default)

    # Numeric pick: "1", "2", …
    if msg_stripped.isdigit():
        idx = int(msg_stripped) - 1
        if 0 <= idx < len(candidates):
            return candidates[idx]

    # Site-name substring match (bidirectional)
    for c in candidates:
        site_name = (_get(c, "site_name") or "").lower()
        if not site_name:
            continue
        if site_name in msg_lower or msg_lower in site_name:
            return c
        # Word-level match
        words = [w for w in site_name.split() if len(w) > 2]
        if words and all(w in msg_lower for w in words):
            return c

    # Resource title match
    for c in candidates:
        title = (_get(c, "title") or "").lower()
        if title and title in msg_lower:
            return c

    # Resource-type match
    _type_aliases = {
        "list": "list", "lists": "list",
        "library": "library", "libraries": "library", "document library": "library",
        "page": "page", "pages": "page", "site page": "page",
    }
    for alias, rtype in _type_aliases.items():
        if alias in msg_lower:
            type_matches = [
                c for c in candidates
                if (_get(c, "resource_type") or "").lower() == rtype
            ]
            if type_matches:
                return type_matches[0]

    return None


def is_location_hint(msg: str) -> bool:
    """Return True when the user's message looks like a location hint."""
    from src.detection.matching.location_hint_detector import detect_location_hint
    return bool(detect_location_hint(msg))


async def resolve_search_hint(
    hint_msg: str,
    pending: Dict,
    session_id: str,
    raw_token: Optional[str],
    default_site_id: str,
    default_site_ids: Optional[list],
    page_ctx: dict,
    data_query_service: Any,
) -> Optional[Any]:
    """Re-run the original question scoped to the site/page named in hint_msg.

    Returns a ChatResponse or None if resolution failed.
    """
    from src.presentation.api import ServiceContainer, get_site_repository, get_list_repository, get_library_repository, get_page_repository, get_drive_repository
    from src.infrastructure.external_services.ai_data_query_service import AIDataQueryService
    from src.infrastructure.services.smart_resource_discovery import SmartResourceDiscoveryService
    from src.application.services import DataQueryApplicationService
    from src.presentation.api.schemas.chat_schemas import ChatResponse

    original_question = pending["original_question"]
    low = hint_msg.lower()

    # Try to resolve a site name from the hint
    target_site_id: Optional[str] = None
    target_site_ids: list = default_site_ids or []

    try:
        if raw_token:
            _hint_site_repo = get_site_repository(user_token=raw_token)
            all_sites = await _hint_site_repo.get_all_sites()
            _hint_tokens = set(re.findall(r"[a-z0-9]+", low))
            best_site = None
            best_score = 0
            for s in all_sites:
                s_name = (s.get("displayName") or s.get("name") or "").lower()
                s_tokens = set(re.findall(r"[a-z0-9]+", s_name))
                overlap = len(_hint_tokens & s_tokens)
                if overlap > best_score:
                    best_score = overlap
                    best_site = s
            if best_site and best_score > 0:
                target_site_id = best_site.get("id")
                target_site_ids = [target_site_id]
                logger.info(
                    "Search hint resolved to site: '%s' (%s)",
                    best_site.get("displayName"), target_site_id,
                )
    except Exception as _hint_err:
        logger.debug("Search hint site resolution failed: %s", _hint_err)

    try:
        if raw_token:
            _hint_site_repo = get_site_repository(user_token=raw_token)
            _hint_list_repo = get_list_repository(user_token=raw_token)
            _hint_library_repo = get_library_repository(user_token=raw_token)
            _hint_page_repo = get_page_repository(user_token=raw_token)
            _hint_drive_repo = get_drive_repository(user_token=raw_token)
            _hint_graph = getattr(_hint_site_repo, "graph_client", None)
            _hint_ai_client, _hint_ai_model = ServiceContainer.get_ai_client()
            _hint_discovery = SmartResourceDiscoveryService(
                site_repository=_hint_site_repo,
                list_repository=_hint_list_repo,
                library_repository=_hint_library_repo,
                page_repository=_hint_page_repo,
                ai_client=_hint_ai_client,
                ai_model=_hint_ai_model,
            )
            _hint_qsvc = DataQueryApplicationService(
                AIDataQueryService(
                    _hint_site_repo, _hint_list_repo, _hint_library_repo, _hint_page_repo, _hint_drive_repo,
                    _hint_graph, target_site_id or default_site_id,
                    smart_discovery_service=_hint_discovery,
                    ai_client=_hint_ai_client,
                    ai_model=_hint_ai_model,
                )
            )
        else:
            _hint_qsvc = data_query_service

        _hint_result = await _hint_qsvc.query_data(
            original_question,
            site_ids=target_site_ids or default_site_ids,
            **page_ctx,
        )
        return ChatResponse(
            intent="query",
            reply=_hint_result.answer,
            source_list=_hint_result.source_list,
            resource_link=_hint_result.resource_link,
            data_summary=_hint_result.data_summary,
            suggested_actions=_hint_result.suggested_actions,
            source_site_name=_hint_result.source_site_name or None,
            source_site_url=_hint_result.source_site_url or None,
            source_resource_type=_hint_result.source_resource_type or None,
            sources=_hint_result.sources if getattr(_hint_result, "sources", None) else None,
            session_id=session_id,
        )
    except Exception as _hint_run_err:
        logger.error("Search hint re-run failed: %s", _hint_run_err, exc_info=True)
        return None
