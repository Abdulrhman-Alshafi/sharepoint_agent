"""Shared utilities for presentation layer handlers.

Provides:
- ``get_logger`` re-export so handlers don't import ``logging`` directly.
- ``error_response`` helper that logs an unhandled exception and returns a
  consistent :class:`~src.presentation.api.schemas.chat_schemas.ChatResponse`.
- ``domain_error_response`` that converts any ``DomainException`` into a
  structured ``ChatResponse`` with error_code, category, and recovery hint.
- ``PendingAction`` / ``store_pending_action`` / ``pop_pending_action`` for
  confirmation-gated destructive operations.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from src.infrastructure.logging import get_logger
from src.infrastructure.correlation import get_correlation_id
from src.domain.exceptions import (
    DomainException,
    PermissionDeniedException,
    AuthenticationException,
    RateLimitError,
    ExternalTimeoutError,
    ExternalServiceUnavailableError,
    CircuitBreakerOpenError,
)
from src.presentation.api.schemas.chat_schemas import ChatResponse

__all__ = [
    "get_logger",
    "error_response",
    "domain_error_response",
    "permission_denied_response",
    "auth_expired_response",
    "PendingAction",
    "store_pending_action",
    "pop_pending_action",
]

# ---------------------------------------------------------------------------
# Pending-action store (in-memory, per-process, 60-second TTL)
# Use TTLCache when cachetools is available to prevent stale entry accumulation.
# ---------------------------------------------------------------------------

try:
    from cachetools import TTLCache
    _pending_actions: Any = TTLCache(maxsize=10_000, ttl=60)
except ImportError:
    _pending_actions: Dict[str, Any] = {}


@dataclass
class PendingAction:
    """A destructive action awaiting user confirmation."""
    action_type: str          # e.g. "delete_site", "empty_recycle_bin"
    resource_name: str        # human-readable name shown in the prompt
    callable: Callable        # async callable that executes the action
    expires_at: float = field(default_factory=lambda: time.monotonic() + 60.0)

    def is_expired(self) -> bool:
        return time.monotonic() > self.expires_at


def store_pending_action(session_id: str, action: PendingAction) -> None:
    """Store a pending action for *session_id*, replacing any previous one."""
    _pending_actions[session_id] = action


def pop_pending_action(session_id: str) -> Optional[PendingAction]:
    """Return and remove the pending action for *session_id*, or ``None``.

    Expired actions are discarded and ``None`` is returned.
    """
    action = _pending_actions.pop(session_id, None)
    if action is not None and action.is_expired():
        return None
    return action


# ---------------------------------------------------------------------------
# Error response helpers
# ---------------------------------------------------------------------------

# Pre-built emoji map for error categories
_ERROR_ICONS = {
    "auth": "🔑",
    "permission": "🔒",
    "validation": "⚠️",
    "service": "⏳",
    "internal": "❌",
}


def error_response(
    logger,
    intent: str,
    message_template: str,
    error: Exception,
    *,
    error_code: Optional[str] = None,
    error_category: str = "internal",
    recovery_hint: Optional[str] = None,
    session_id: Optional[str] = None,
) -> ChatResponse:
    """Log *error* and return a ``ChatResponse`` with a user-friendly message.

    Args:
        logger: A logger instance (created via :func:`get_logger`).
        intent: The ``ChatResponse.intent`` value (e.g. ``"chat"``, ``"delete"``).
        message_template: Human-readable message.  Use ``{error}`` as a
            placeholder if you want to include the exception text.
        error: The caught exception.
        error_code: Machine-readable error code (defaults to exception class name).
        error_category: "auth" | "permission" | "validation" | "service" | "internal".
        recovery_hint: User-facing recovery suggestion.
        session_id: Optional session ID to include in the response.

    Returns:
        A :class:`ChatResponse` with ``intent`` and the formatted ``reply``.

    Example::

        except Exception as e:
            return error_response(logger, "chat", "Sorry, couldn't do that: {error}", e)
    """
    logger.error("%s", error, exc_info=True)
    cid = get_correlation_id()

    icon = _ERROR_ICONS.get(error_category, "❌")
    
    if error_category == "internal":
        reply = f"{icon} An unexpected system error occurred while processing your request."
    else:
        reply = f"{icon} {message_template.format(error=str(error))}"

    if not recovery_hint:
        recovery_hint = "If this problem persists, please contact your administrator."

    return ChatResponse(
        intent=intent,
        reply=reply,
        error_code=error_code or error.__class__.__name__,
        error_category=error_category,
        recovery_hint=recovery_hint,
        correlation_id=cid,
        session_id=session_id,
    )


def domain_error_response(
    exc: DomainException,
    intent: str = "chat",
    session_id: Optional[str] = None,
) -> ChatResponse:
    """Convert any :class:`DomainException` to a user-friendly ``ChatResponse``.

    Automatically sets error_code, error_category, recovery_hint, and
    correlation_id from the exception's attributes.
    """
    icon = _ERROR_ICONS.get(exc.error_category, "❌")
    reply = f"{icon} {exc.message}"

    return ChatResponse(
        intent=intent,
        reply=reply,
        error_code=exc.error_code,
        error_category=exc.error_category,
        recovery_hint=exc.recovery_hint,
        correlation_id=get_correlation_id(),
        session_id=session_id,
    )


def permission_denied_response(
    session_id: Optional[str] = None,
) -> ChatResponse:
    """Standardized response for PermissionDeniedException."""
    return ChatResponse(
        intent="chat",
        reply="🔒 **Access Denied** — You don't have permission to access or modify this resource. "
              "Please contact your SharePoint administrator to request the necessary access.",
        error_code="PERMISSION_DENIED",
        error_category="permission",
        recovery_hint="Contact your SharePoint administrator to request the necessary access.",
        correlation_id=get_correlation_id(),
        session_id=session_id,
    )


def auth_expired_response(
    session_id: Optional[str] = None,
) -> ChatResponse:
    """Standardized response for AuthenticationException."""
    return ChatResponse(
        intent="chat",
        reply="🔑 **Session Expired** — Your authentication token is no longer valid. "
              "Please refresh the page and sign in again.",
        error_code="AUTH_EXPIRED",
        error_category="auth",
        recovery_hint="Please refresh the page and sign in again.",
        correlation_id=get_correlation_id(),
        session_id=session_id,
    )
