"""Validation service — common validation helpers.

Extracts shared validation patterns used across controllers and orchestrators.
"""

import logging
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


def extract_user_info(current_user: Any) -> tuple:
    """Extract (user_email, user_login_name) from current_user."""
    if isinstance(current_user, str):
        return current_user, current_user
    return current_user.get("email", ""), current_user.get("preferred_username", "")
