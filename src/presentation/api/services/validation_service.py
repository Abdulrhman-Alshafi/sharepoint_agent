"""Validation service — common validation helpers.

Extracts shared validation patterns used across controllers and orchestrators.
"""

import logging
import json
from typing import Any, Dict, Optional

from src.infrastructure.config import settings
from src.detection.validation.confirmation_detector import detect_confirmation

logger = logging.getLogger(__name__)


def is_confirmation(message: str) -> bool:
    """Return True if the message is a confirmation reply."""
    return bool(detect_confirmation(message))


def extract_raw_token(request: Any) -> Optional[str]:
    """Extract the raw Bearer token from a FastAPI Request object."""
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    return token or None


def extract_page_context(body: Any) -> Dict[str, Optional[str]]:
    """Extract page context from a ChatRequest body."""
    if body.context:
        return {
            "context_site_id": body.context.site.id or None,
            "page_id": body.context.page.id or None,
            "page_url": body.context.page.url,
            "page_title": body.context.page.title or None,
        }
    return {"context_site_id": None, "page_id": None, "page_url": None, "page_title": None}


def extract_site_id(body: Any) -> str:
    """Extract effective site ID from a ChatRequest body."""
    if body.context and body.context.site.id:
        return body.context.site.id
    return body.site_id or settings.SITE_ID


def extract_upload_site_id(site_id: Optional[str], history_payload: Optional[str]) -> str:
    """Extract effective site ID for multipart upload requests.

    Resolution order:
    1) Explicit form field `site_id`
    2) Most recent site context from `history` JSON payload
    3) Global default site
    """
    explicit = (site_id or "").strip()
    if explicit:
        return explicit

    hist_site = _extract_site_id_from_history(history_payload)
    if hist_site:
        return hist_site

    return settings.SITE_ID


def _extract_site_id_from_history(history_payload: Optional[str]) -> Optional[str]:
    """Best-effort parser for history JSON to recover active site context."""
    if not history_payload or not history_payload.strip():
        return None

    try:
        parsed = json.loads(history_payload)
    except (TypeError, json.JSONDecodeError):
        return None

    entries = parsed if isinstance(parsed, list) else [parsed]
    for entry in reversed(entries):
        if not isinstance(entry, dict):
            continue

        # Common chat request context shape: { context: { site: { id } } }
        context = entry.get("context")
        if isinstance(context, dict):
            site = context.get("site")
            if isinstance(site, dict):
                sid = _normalize_site_id(site.get("id"))
                if sid:
                    return sid

        # Flat variants seen in request/response metadata
        for key in ("site_id", "siteId", "source_site_id"):
            sid = _normalize_site_id(entry.get(key))
            if sid:
                return sid

        data_summary = entry.get("data_summary")
        if isinstance(data_summary, dict):
            for key in ("site_id", "source_site_id"):
                sid = _normalize_site_id(data_summary.get(key))
                if sid:
                    return sid

    return None


def _normalize_site_id(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def extract_user_info(current_user: Any) -> tuple:
    """Extract (user_email, user_login_name) from current_user."""
    if isinstance(current_user, str):
        return current_user, current_user
    return current_user.get("email", ""), current_user.get("preferred_username", "")
