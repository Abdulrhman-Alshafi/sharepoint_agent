"""Request-scoped correlation ID using contextvars.

Every incoming request gets a unique correlation ID that flows through all log
entries, error responses, and outbound service calls.  The frontend can also
pass ``X-Request-ID`` to correlate its own logs with the backend.
"""

import contextvars
import uuid
from typing import Optional

# ContextVar holds the correlation ID for the current async task / thread.
_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)


def new_correlation_id() -> str:
    """Generate a new correlation ID and store it in the current context."""
    cid = uuid.uuid4().hex[:12]  # 12-char hex — short enough for logs
    _correlation_id.set(cid)
    return cid


def set_correlation_id(cid: str) -> None:
    """Set an externally-provided correlation ID (e.g. from X-Request-ID)."""
    _correlation_id.set(cid)


def get_correlation_id() -> str:
    """Return the current correlation ID, or empty string if not set."""
    return _correlation_id.get()
