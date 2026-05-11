import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import redis
from src.infrastructure.config import settings

logger = logging.getLogger(__name__)


class SecurityStore:
    """Unified security store backed by Redis.

    REDIS IS MANDATORY. All data is stored in Redis so that it is shared
    across pods / restarts. In-memory fallback has been removed to ensure
    consistent state in distributed environments.

    All public methods are synchronous and thread-safe. Redis operations
    use a synchronous ``redis.Redis`` client to keep the auth hot-path
    simple (no ``await`` needed in middleware / dependencies).
    """

    # Key prefixes for Redis namespacing
    _PFX_AUTH_FAIL = "sec:auth_fail:"
    _PFX_AUTH_BLOCK = "sec:auth_block:"
    _PFX_OBO = "sec:obo:"
    _PFX_TOKEN = "sec:token:"

    def __init__(self) -> None:
        """Initialize Redis connection.
        
        Raises:
            RuntimeError: If Redis connection fails.
        """
        logger.info("SecurityStore: Initializing mandatory Redis connection...")
        try:
            self._redis = redis.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            # Verify connection immediately
            self._redis.ping()
            logger.info("SecurityStore: Successfully connected to Redis at %s", settings.REDIS_URL)
        except Exception as exc:
            logger.error("SecurityStore: CRITICAL - Redis connection failed: %s", exc)
            raise RuntimeError(
                f"Redis connection failed at {settings.REDIS_URL}. "
                "SecurityStore requires a working Redis instance for rate-limiting and OBO token caching. "
                "Ensure Redis is running and REDIS_URL is correct."
            ) from exc

    # ── property ──────────────────────────────────────────────────────────
    @property
    def is_distributed(self) -> bool:
        """Always True as this store is now strictly Redis-backed."""
        return True

    # =====================================================================
    # Auth failure tracking
    # =====================================================================

    def record_auth_failure(self, ip: str) -> None:
        """Record an authentication failure for *ip*."""
        key = f"{self._PFX_AUTH_FAIL}{ip}"
        pipe = self._redis.pipeline()
        pipe.rpush(key, str(time.time()))
        pipe.expire(key, 120)  # auto-clean after 2 min
        pipe.execute()

    def get_auth_failure_count(self, ip: str, window_seconds: int) -> int:
        """Return the number of auth failures for *ip* within the rolling window."""
        key = f"{self._PFX_AUTH_FAIL}{ip}"
        cutoff = str(time.time() - window_seconds)
        # Read all timestamps, count those within window
        entries = self._redis.lrange(key, 0, -1) or []
        return sum(1 for ts in entries if float(ts) >= float(cutoff))

    def block_ip(self, ip: str, block_seconds: int) -> None:
        """Block *ip* for *block_seconds*."""
        key = f"{self._PFX_AUTH_BLOCK}{ip}"
        self._redis.setex(key, block_seconds, "1")
        # Clear failure log
        self._redis.delete(f"{self._PFX_AUTH_FAIL}{ip}")

    def is_ip_blocked(self, ip: str) -> Tuple[bool, int]:
        """Check if *ip* is currently blocked.

        Returns ``(is_blocked, retry_after_seconds)``.
        """
        key = f"{self._PFX_AUTH_BLOCK}{ip}"
        ttl = self._redis.ttl(key)
        if ttl and ttl > 0:
            return True, ttl
        return False, 0

    def clear_auth_state(self, ip: str) -> None:
        """Clear all auth failure and block state for *ip*."""
        self._redis.delete(
            f"{self._PFX_AUTH_FAIL}{ip}",
            f"{self._PFX_AUTH_BLOCK}{ip}",
        )

    # =====================================================================
    # OBO token cache
    # =====================================================================

    def get_obo_token(self, assertion_hash: str) -> Optional[str]:
        """Return cached OBO token or ``None``."""
        return self._redis.get(f"{self._PFX_OBO}{assertion_hash}")

    def set_obo_token(self, assertion_hash: str, token: str, ttl_seconds: int) -> None:
        """Cache an OBO token with TTL."""
        self._redis.setex(f"{self._PFX_OBO}{assertion_hash}", ttl_seconds, token)

    def invalidate_obo_token(self, assertion_hash: str) -> None:
        """Force-evict a cached OBO token (e.g. after permission change)."""
        self._redis.delete(f"{self._PFX_OBO}{assertion_hash}")

    # =====================================================================
    # Token validation payload cache
    # =====================================================================

    def get_token_payload(self, token_hash: str) -> Optional[Dict[str, Any]]:
        """Return cached token payload or ``None``."""
        raw = self._redis.get(f"{self._PFX_TOKEN}{token_hash}")
        if raw:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return None
        return None

    def set_token_payload(
        self, token_hash: str, payload: Dict[str, Any], ttl_seconds: int = 300
    ) -> None:
        """Cache a validated token payload with TTL (default 5 min)."""
        raw = json.dumps(payload)
        self._redis.setex(f"{self._PFX_TOKEN}{token_hash}", ttl_seconds, raw)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
security_store = SecurityStore()
