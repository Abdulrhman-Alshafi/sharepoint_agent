"""Backwards-compatible shim — all logic has been moved to the query/ sub-package.

Split rationale (was 1698 lines):
    query/prompts.py         – ROUTER_PROMPT, QUERY_SYSTEM_PROMPT
    query/helpers.py         – parse_site_info, find_list_by_name
    query/hub_mixin.py       – _handle_hub_* methods
    query/metadata_mixin.py  – _handle_metadata_count, _handle_filtered_meta, etc.
    query/library_mixin.py   – _handle_library_content_query, document queries, search
    query/data_mixin.py      – _handle_specific_data_query, _handle_graph_search_fallback
    query/service.py         – AIDataQueryService (answer_question + _run_smart_discovery)
"""
from src.infrastructure.external_services.query.service import AIDataQueryService  # noqa: F401
from src.infrastructure.external_services.query.prompts import (  # noqa: F401
    ROUTER_PROMPT,
    QUERY_SYSTEM_PROMPT,
)
from src.infrastructure.external_services.query.helpers import (  # noqa: F401
    parse_site_info as _parse_site_info,
    find_list_by_name as _find_list_by_name,
)

__all__ = [
    "AIDataQueryService",
    "ROUTER_PROMPT",
    "QUERY_SYSTEM_PROMPT",
    "_parse_site_info",
    "_find_list_by_name",
]
