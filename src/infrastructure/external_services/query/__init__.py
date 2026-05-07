"""AI data query sub-package.

Public re-exports keep all existing import paths working.
"""
from src.infrastructure.external_services.query.service import AIDataQueryService
from src.infrastructure.external_services.query.prompts import ROUTER_PROMPT, QUERY_SYSTEM_PROMPT

__all__ = ["AIDataQueryService", "ROUTER_PROMPT", "QUERY_SYSTEM_PROMPT"]
