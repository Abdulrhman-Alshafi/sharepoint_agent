"""Rate limiter singleton — imported by endpoint modules and wired into the app in main.py.

The limiter stores counters in Redis so that rate
limits are enforced consistently across multiple application instances.
When Redis is unavailable, falls back to in-memory storage.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request

from src.infrastructure.config import settings


def get_user_identifier(request: Request) -> str:
    """
    Extract user identifier for rate limiting.
    
    Priority:
    1. Authenticated user email (from state.current_user)
    2. IP address (fallback for unauthenticated requests)
    
    This enables per-user rate limiting instead of global limits.
    """
    # Try to get authenticated user from request state
    if hasattr(request.state, "current_user"):
        user = request.state.current_user
        if user:
            return f"user:{user}"
    
    # Fallback to IP address for unauthenticated requests
    return f"ip:{get_remote_address(request)}"


# Configure storage backend based on Redis availability
_storage_uri = None
try:
    import redis
    _r = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
    _r.ping()
    _storage_uri = settings.REDIS_URL
except Exception:
    pass  # Fall back to in-memory

# Per-user rate limiting enabled by default for production
# Uses user email when available, falls back to IP address
# When _storage_uri is set, slowapi uses Redis for distributed rate limiting
limiter = Limiter(
    key_func=get_user_identifier,
    enabled=True,
    storage_uri=_storage_uri,
)
