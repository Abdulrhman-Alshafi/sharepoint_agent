"""Redis-backed (or in-memory fallback) distributed security store.

Provides a single interface for:
- Auth failure tracking and IP blocking (rate-limit auth attempts)
- OBO token caching
- Token validation payload caching

All data is stored in Redis so that it is shared
across pods / restarts.  When Redis is unavailable the store degrades
gracefully to thread-safe in-memory dicts (suitable for dev / single-instance).
"""

import hashlib
import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from src.infrastructure.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Attempt to import redis; fall back silently
# ---------------------------------------------------------------------------
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.info("redis package not installed — security store will use in-memory backend")


class SecurityStore:
    """Unified security store with Redis or in-memory backend.

    All public methods are synchronous and thread-safe.  Redis operations
    use a synchronous ``redis.Redis`` client to keep the auth hot-path
    simple (no ``await`` needed in middleware / dependencies).
    """

    # Key prefixes for Redis namespacing
    _PFX_AUTH_FAIL = "sec:auth_fail:"
    _PFX_AUTH_BLOCK = "sec:auth_block:"
    _PFX_OBO = "sec:obo:"
    _PFX_TOKEN = "sec:token:"

    def __init__(self) -> None:
        self._redis: Optional["redis.Redis"] = None
        self._use_redis = False

        if REDIS_AVAILABLE:
            try:
                self._redis = redis.Redis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=3,
                )
                self._redis.ping()
                self._use_redis = True
                logger.info("SecurityStore: connected to Redis at %s", settings.REDIS_URL)
            except Exception as exc:
                logger.warning(
                    "SecurityStore: Redis connection failed (%s) — falling back to in-memory",
                    exc,
                )
                self._redis = None

        if not self._use_redis:
            if not REDIS_AVAILABLE:
                logger.warning(
                    "'redis' package is not installed. "
                    "Install with: pip install redis>=5.0.0"
                )
            logger.warning(
                "SecurityStore: running in-memory mode. "
                "Rate limits and auth blocks will NOT persist across restarts "
                "and will NOT be shared across multiple instances."
            )

        # --- In-memory fallback structures ---
        self._lock = threading.Lock()
        # Auth failure: ip -> list of monotonic timestamps
        self._mem_failures: Dict[str, List[float]] = {}
        # Auth block: ip -> blocked_until (monotonic)
        self._mem_blocked: Dict[str, float] = {}
        # OBO cache: hash -> (token, expiry_monotonic)
        self._mem_obo: Dict[str, Tuple[str, float]] = {}
        # Token validation cache: hash -> (payload_json, expiry_monotonic)
        self._mem_token: Dict[str, Tuple[str, float]] = {}

    # ── property ──────────────────────────────────────────────────────────
    @property
    def is_distributed(self) -> bool:
        """True when backed by Redis (data shared across instances)."""
        return self._use_redis

    # =====================================================================
    # Auth failure tracking
    # =====================================================================

    def record_auth_failure(self, ip: str) -> None:
        """Record an authentication failure for *ip*."""
        if self._use_redis:
            key = f"{self._PFX_AUTH_FAIL}{ip}"
            pipe = self._redis.pipeline()
            pipe.rpush(key, str(time.time()))
            pipe.expire(key, 120)  # auto-clean after 2 min
            pipe.execute()
        else:
            with self._lock:
                self._mem_failures.setdefault(ip, []).append(time.monotonic())

    def get_auth_failure_count(self, ip: str, window_seconds: int) -> int:
        """Return the number of auth failures for *ip* within the rolling window."""
        if self._use_redis:
            key = f"{self._PFX_AUTH_FAIL}{ip}"
            cutoff = str(time.time() - window_seconds)
            # Read all timestamps, count those within window
            entries = self._redis.lrange(key, 0, -1) or []
            return sum(1 for ts in entries if float(ts) >= float(cutoff))
        else:
            now = time.monotonic()
            with self._lock:
                timestamps = self._mem_failures.get(ip, [])
                valid = [t for t in timestamps if now - t < window_seconds]
                self._mem_failures[ip] = valid
                return len(valid)

    def block_ip(self, ip: str, block_seconds: int) -> None:
        """Block *ip* for *block_seconds*."""
        if self._use_redis:
            key = f"{self._PFX_AUTH_BLOCK}{ip}"
            self._redis.setex(key, block_seconds, "1")
            # Clear failure log
            self._redis.delete(f"{self._PFX_AUTH_FAIL}{ip}")
        else:
            with self._lock:
                self._mem_blocked[ip] = time.monotonic() + block_seconds
                self._mem_failures.pop(ip, None)

    def is_ip_blocked(self, ip: str) -> Tuple[bool, int]:
        """Check if *ip* is currently blocked.

        Returns ``(is_blocked, retry_after_seconds)``.
        """
        if self._use_redis:
            key = f"{self._PFX_AUTH_BLOCK}{ip}"
            ttl = self._redis.ttl(key)
            if ttl and ttl > 0:
                return True, ttl
            return False, 0
        else:
            with self._lock:
                blocked_until = self._mem_blocked.get(ip)
                if blocked_until is None:
                    return False, 0
                remaining = blocked_until - time.monotonic()
                if remaining > 0:
                    return True, int(remaining)
                del self._mem_blocked[ip]
                return False, 0

    def clear_auth_state(self, ip: str) -> None:
        """Clear all auth failure and block state for *ip*."""
        if self._use_redis:
            self._redis.delete(
                f"{self._PFX_AUTH_FAIL}{ip}",
                f"{self._PFX_AUTH_BLOCK}{ip}",
            )
        else:
            with self._lock:
                self._mem_failures.pop(ip, None)
                self._mem_blocked.pop(ip, None)

    # =====================================================================
    # OBO token cache
    # =====================================================================

    def get_obo_token(self, assertion_hash: str) -> Optional[str]:
        """Return cached OBO token or ``None``."""
        if self._use_redis:
            return self._redis.get(f"{self._PFX_OBO}{assertion_hash}")
        else:
            with self._lock:
                entry = self._mem_obo.get(assertion_hash)
                if entry and time.monotonic() < entry[1]:
                    return entry[0]
                if entry:
                    del self._mem_obo[assertion_hash]
                return None

    def set_obo_token(self, assertion_hash: str, token: str, ttl_seconds: int) -> None:
        """Cache an OBO token with TTL."""
        if self._use_redis:
            self._redis.setex(f"{self._PFX_OBO}{assertion_hash}", ttl_seconds, token)
        else:
            with self._lock:
                self._mem_obo[assertion_hash] = (token, time.monotonic() + ttl_seconds)
                # Bound memory
                if len(self._mem_obo) > 10_000:
                    oldest = sorted(self._mem_obo.items(), key=lambda kv: kv[1][1])[:1000]
                    for k, _ in oldest:
                        del self._mem_obo[k]

    def invalidate_obo_token(self, assertion_hash: str) -> None:
        """Force-evict a cached OBO token (e.g. after permission change)."""
        if self._use_redis:
            self._redis.delete(f"{self._PFX_OBO}{assertion_hash}")
        else:
            with self._lock:
                self._mem_obo.pop(assertion_hash, None)

    # =====================================================================
    # Token validation payload cache
    # =====================================================================

    def get_token_payload(self, token_hash: str) -> Optional[Dict[str, Any]]:
        """Return cached token payload or ``None``."""
        if self._use_redis:
            raw = self._redis.get(f"{self._PFX_TOKEN}{token_hash}")
            if raw:
                try:
                    return json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    return None
            return None
        else:
            with self._lock:
                entry = self._mem_token.get(token_hash)
                if entry and time.monotonic() < entry[1]:
                    return json.loads(entry[0])
                if entry:
                    del self._mem_token[token_hash]
                return None

    def set_token_payload(
        self, token_hash: str, payload: Dict[str, Any], ttl_seconds: int = 300
    ) -> None:
        """Cache a validated token payload with TTL (default 5 min)."""
        raw = json.dumps(payload)
        if self._use_redis:
            self._redis.setex(f"{self._PFX_TOKEN}{token_hash}", ttl_seconds, raw)
        else:
            with self._lock:
                self._mem_token[token_hash] = (raw, time.monotonic() + ttl_seconds)
                if len(self._mem_token) > 10_000:
                    oldest = sorted(self._mem_token.items(), key=lambda kv: kv[1][1])[:1000]
                    for k, _ in oldest:
                        del self._mem_token[k]


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
security_store = SecurityStore()
