"""Async Redis-backed (or in-memory fallback) conversation state service.

Replaces the global in-memory dictionaries that were scattered across chat.py
and handler modules. Provides session-scoped, TTL-controlled storage for:

- High-risk pending confirmations
- Last-created resource context (pronoun resolution)
- Pending clarification candidates (disambiguation)
- Pending search hints (location follow-ups)
- Pending file uploads (temporary file storage)

All methods are async-safe. When Redis is available, state is shared across
multiple instances. When Redis is unavailable, falls back to thread-safe
in-memory storage (suitable for single-instance / dev).
"""

import base64
import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from src.infrastructure.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Attempt to import async redis; fall back silently
# ---------------------------------------------------------------------------
try:
    import redis.asyncio as aioredis
    ASYNC_REDIS_AVAILABLE = True
except ImportError:
    ASYNC_REDIS_AVAILABLE = False
    logger.info("redis.asyncio not available — ConversationState will use in-memory backend")


class ConversationStateService:
    """Async conversation state store with Redis or in-memory backend.

    Mirrors the dual-backend pattern of ``SecurityStore`` but uses
    ``redis.asyncio`` for non-blocking operations in async handlers.
    """

    # Key prefixes for Redis namespacing
    _PFX_HIGH_RISK = "conv:hr:"
    _PFX_LAST_CREATED = "conv:lc:"
    _PFX_CLARIFICATION = "conv:clar:"
    _PFX_SEARCH_HINT = "conv:hint:"
    _PFX_UPLOAD = "conv:upload:"

    # TTL defaults (seconds)
    TTL_HIGH_RISK = 300        # 5 minutes
    TTL_LAST_CREATED = 3600    # 1 hour
    TTL_CLARIFICATION = 300    # 5 minutes
    TTL_SEARCH_HINT = 300      # 5 minutes
    TTL_UPLOAD = 900           # 15 minutes

    def __init__(self) -> None:
        self._redis: Optional["aioredis.Redis"] = None
        self._use_redis = False
        self._connected = False

        # --- In-memory fallback structures ---
        self._lock = threading.Lock()
        # High-risk pending: session_id -> (prompt, expiry_monotonic)
        self._mem_high_risk: Dict[str, Tuple[str, float]] = {}
        # Last created: session_id -> (json_str, expiry_monotonic)
        self._mem_last_created: Dict[str, Tuple[str, float]] = {}
        # Clarification: session_id -> (json_str, expiry_monotonic)
        self._mem_clarification: Dict[str, Tuple[str, float]] = {}
        # Search hint: session_id -> (json_str, expiry_monotonic)
        self._mem_search_hint: Dict[str, Tuple[str, float]] = {}
        # Upload store: file_id -> (json_str, expiry_monotonic)
        self._mem_upload: Dict[str, Tuple[str, float]] = {}

    async def _ensure_connected(self) -> None:
        """Lazy-connect to Redis on first use."""
        if self._connected:
            return
        self._connected = True

        if ASYNC_REDIS_AVAILABLE:
            try:
                self._redis = aioredis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=3,
                )
                await self._redis.ping()
                self._use_redis = True
                logger.info("ConversationState: connected to Redis at %s", settings.REDIS_URL)
            except Exception as exc:
                logger.warning(
                    "ConversationState: Redis connection failed (%s) — falling back to in-memory",
                    exc,
                )
                self._redis = None
        else:
            logger.warning(
                "ConversationState: redis.asyncio not available — using in-memory storage"
            )

    @property
    def is_distributed(self) -> bool:
        """True when backed by Redis."""
        return self._use_redis

    # =====================================================================
    # Generic get/set/pop helpers
    # =====================================================================

    async def _set(self, prefix: str, key: str, value: str, ttl: int) -> None:
        await self._ensure_connected()
        if self._use_redis:
            try:
                await self._redis.setex(f"{prefix}{key}", ttl, value)
                return
            except Exception as exc:
                logger.warning("Redis SET failed: %s", exc)
        # In-memory fallback
        store = self._get_mem_store(prefix)
        with self._lock:
            store[key] = (value, time.monotonic() + ttl)
            self._bound_store(store)

    async def _get(self, prefix: str, key: str) -> Optional[str]:
        await self._ensure_connected()
        if self._use_redis:
            try:
                return await self._redis.get(f"{prefix}{key}")
            except Exception as exc:
                logger.warning("Redis GET failed: %s", exc)
        # In-memory fallback
        store = self._get_mem_store(prefix)
        with self._lock:
            entry = store.get(key)
            if entry and time.monotonic() < entry[1]:
                return entry[0]
            if entry:
                del store[key]
            return None

    async def _pop(self, prefix: str, key: str) -> Optional[str]:
        await self._ensure_connected()
        if self._use_redis:
            try:
                pipe = self._redis.pipeline()
                pipe.get(f"{prefix}{key}")
                pipe.delete(f"{prefix}{key}")
                results = await pipe.execute()
                return results[0]
            except Exception as exc:
                logger.warning("Redis POP failed: %s", exc)
        # In-memory fallback
        store = self._get_mem_store(prefix)
        with self._lock:
            entry = store.pop(key, None)
            if entry and time.monotonic() < entry[1]:
                return entry[0]
            return None

    async def _delete(self, prefix: str, key: str) -> None:
        await self._ensure_connected()
        if self._use_redis:
            try:
                await self._redis.delete(f"{prefix}{key}")
                return
            except Exception as exc:
                logger.warning("Redis DELETE failed: %s", exc)
        store = self._get_mem_store(prefix)
        with self._lock:
            store.pop(key, None)

    def _get_mem_store(self, prefix: str) -> Dict:
        """Return the in-memory dict for the given prefix."""
        mapping = {
            self._PFX_HIGH_RISK: self._mem_high_risk,
            self._PFX_LAST_CREATED: self._mem_last_created,
            self._PFX_CLARIFICATION: self._mem_clarification,
            self._PFX_SEARCH_HINT: self._mem_search_hint,
            self._PFX_UPLOAD: self._mem_upload,
        }
        return mapping.get(prefix, self._mem_high_risk)

    def _bound_store(self, store: Dict, max_size: int = 10_000) -> None:
        """Prevent unbounded in-memory growth."""
        if len(store) > max_size:
            now = time.monotonic()
            expired = [k for k, (_, exp) in store.items() if now > exp]
            for k in expired:
                del store[k]
            if len(store) > max_size:
                oldest = sorted(store.items(), key=lambda kv: kv[1][1])[:1000]
                for k, _ in oldest:
                    del store[k]

    # =====================================================================
    # High-Risk Pending Confirmations
    # =====================================================================

    async def set_high_risk_pending(self, session_id: str, prompt: str) -> None:
        """Store a prompt after a high-risk warning for confirmation."""
        logger.info("[state] Session %s: stored high-risk pending (TTL=%ds)", session_id, self.TTL_HIGH_RISK)
        await self._set(self._PFX_HIGH_RISK, session_id, prompt, self.TTL_HIGH_RISK)

    async def get_high_risk_pending(self, session_id: str) -> Optional[str]:
        """Retrieve the pending high-risk prompt."""
        return await self._get(self._PFX_HIGH_RISK, session_id)

    async def pop_high_risk_pending(self, session_id: str) -> Optional[str]:
        """Retrieve and remove the pending high-risk prompt."""
        result = await self._pop(self._PFX_HIGH_RISK, session_id)
        if result:
            logger.info("[state] Session %s: consumed high-risk pending", session_id)
        return result

    # =====================================================================
    # Last-Created Resource Context
    # =====================================================================

    async def set_last_created(
        self, session_id: str, name: str, resource_type: str, site_id: str = ""
    ) -> None:
        """Track the most recently created/referenced resource for pronoun resolution."""
        data = json.dumps({"name": name, "type": resource_type, "site_id": site_id})
        await self._set(self._PFX_LAST_CREATED, session_id, data, self.TTL_LAST_CREATED)
        logger.debug("[state] Session %s: last_created=%s (%s)", session_id, name, resource_type)

    async def get_last_created(self, session_id: str) -> Optional[Tuple[str, str, str]]:
        """Return (name, type, site_id) or None."""
        raw = await self._get(self._PFX_LAST_CREATED, session_id)
        if raw:
            try:
                d = json.loads(raw)
                return (d["name"], d["type"], d.get("site_id", ""))
            except (json.JSONDecodeError, KeyError):
                return None
        return None

    # =====================================================================
    # Pending Clarification
    # =====================================================================

    async def set_pending_clarification(
        self, session_id: str, original_question: str, candidates: list, reason: str = ""
    ) -> None:
        """Store disambiguation candidates for user's next reply."""
        # Candidates are ResourceCandidate objects; serialize their attrs
        serialized_candidates = []
        for c in candidates:
            serialized_candidates.append({
                "site_id": getattr(c, "site_id", None),
                "site_name": getattr(c, "site_name", None),
                "title": getattr(c, "title", None),
                "resource_type": getattr(c, "resource_type", None),
                "relevance_score": getattr(c, "relevance_score", 0),
            })
        data = json.dumps({
            "original_question": original_question,
            "candidates": serialized_candidates,
            "clarification_reason": reason,
        })
        await self._set(self._PFX_CLARIFICATION, session_id, data, self.TTL_CLARIFICATION)
        # Also clear any stale search hint
        await self._delete(self._PFX_SEARCH_HINT, session_id)

    async def get_pending_clarification(self, session_id: str) -> Optional[Dict]:
        """Return the pending clarification data or None."""
        raw = await self._get(self._PFX_CLARIFICATION, session_id)
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return None
        return None

    async def pop_pending_clarification(self, session_id: str) -> Optional[Dict]:
        """Retrieve and remove pending clarification."""
        raw = await self._pop(self._PFX_CLARIFICATION, session_id)
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return None
        return None

    async def clear_pending_clarification(self, session_id: str) -> None:
        """Clear pending clarification state."""
        await self._delete(self._PFX_CLARIFICATION, session_id)

    # =====================================================================
    # Pending Search Hint
    # =====================================================================

    async def set_pending_search_hint(
        self, session_id: str, original_question: str, topic: str
    ) -> None:
        """Store a 'not found' context for location hint follow-up."""
        data = json.dumps({"original_question": original_question, "topic": topic})
        await self._set(self._PFX_SEARCH_HINT, session_id, data, self.TTL_SEARCH_HINT)
        # Also clear any stale clarification
        await self._delete(self._PFX_CLARIFICATION, session_id)

    async def get_pending_search_hint(self, session_id: str) -> Optional[Dict]:
        """Return pending search hint data or None."""
        raw = await self._get(self._PFX_SEARCH_HINT, session_id)
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return None
        return None

    async def pop_pending_search_hint(self, session_id: str) -> Optional[Dict]:
        """Retrieve and remove pending search hint."""
        raw = await self._pop(self._PFX_SEARCH_HINT, session_id)
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return None
        return None

    async def clear_pending_search_hint(self, session_id: str) -> None:
        """Clear pending search hint state."""
        await self._delete(self._PFX_SEARCH_HINT, session_id)

    # =====================================================================
    # Pending File Upload Store
    # =====================================================================

    async def store_pending_files(self, file_list: List[Dict[str, Any]]) -> str:
        """Save uploaded files temporarily and return a UUID key.

        Each item in *file_list* must have keys: ``bytes``, ``filename``, ``content_type``.
        File bytes are base64-encoded for Redis storage.
        """
        import uuid
        file_id = str(uuid.uuid4())

        serialized = []
        for f in file_list:
            serialized.append({
                "bytes_b64": base64.b64encode(f["bytes"]).decode("ascii"),
                "filename": f["filename"],
                "content_type": f["content_type"],
            })
        data = json.dumps(serialized)
        await self._set(self._PFX_UPLOAD, file_id, data, self.TTL_UPLOAD)
        logger.info("[state] Stored %d pending file(s), id=%s (TTL=%ds)", len(file_list), file_id, self.TTL_UPLOAD)
        return file_id

    async def store_pending_file(self, file_bytes: bytes, filename: str, content_type: str) -> str:
        """Convenience wrapper for a single file."""
        return await self.store_pending_files([{
            "bytes": file_bytes, "filename": filename, "content_type": content_type,
        }])

    async def get_pending_files(self, file_id: str) -> Optional[List[Dict[str, Any]]]:
        """Return the list of temporarily stored files, or None if expired/missing."""
        raw = await self._get(self._PFX_UPLOAD, file_id)
        if not raw:
            return None
        try:
            serialized = json.loads(raw)
            result = []
            for f in serialized:
                result.append({
                    "bytes": base64.b64decode(f["bytes_b64"]),
                    "filename": f["filename"],
                    "content_type": f["content_type"],
                })
            return result
        except (json.JSONDecodeError, KeyError):
            return None

    async def get_pending_file(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Return the first stored file entry (legacy single-file callers)."""
        files = await self.get_pending_files(file_id)
        return files[0] if files else None

    async def remove_pending_files(self, file_id: str) -> None:
        """Remove a pending upload entry."""
        await self._delete(self._PFX_UPLOAD, file_id)

    # =====================================================================
    # Utility: update last context from response
    # =====================================================================

    async def update_last_context_from_response(
        self, session_id: str, response: Any, default_site_id: str = ""
    ) -> None:
        """Update last_created from a handler response's data_summary.

        Works for item_operation responses (create/update/delete/query) and any
        response that carries a ``list_name``, ``library_name``, ``page_name``, or
        ``site_name`` key in its data_summary.
        """
        ds = getattr(response, "data_summary", None)
        if not ds or not isinstance(ds, dict):
            return
        for key, rtype in (
            ("list_name", "list"),
            ("library_name", "library"),
            ("page_name", "page"),
            ("site_name", "site"),
        ):
            name = ds.get(key)
            if name:
                await self.set_last_created(
                    session_id, name, rtype, ds.get("site_id") or default_site_id
                )
                return

    async def update_last_context_from_provision(
        self, session_id: str, result_dto: Any, site_id: str = ""
    ) -> None:
        """Update last_created from a provisioning result DTO."""
        if result_dto.created_lists:
            await self.set_last_created(
                session_id,
                result_dto.created_lists[0].get("displayName", ""),
                "list", site_id,
            )
        elif result_dto.created_pages:
            name = result_dto.created_pages[0].get(
                "displayName", result_dto.created_pages[0].get("name", "")
            )
            await self.set_last_created(session_id, name, "page", site_id)
        elif result_dto.created_document_libraries:
            await self.set_last_created(
                session_id,
                result_dto.created_document_libraries[0].get("displayName", ""),
                "library", site_id,
            )
        elif getattr(result_dto, "created_sites", []):
            name = result_dto.created_sites[0].get(
                "displayName", result_dto.created_sites[0].get("name", "")
            )
            await self.set_last_created(session_id, name, "site", site_id)

    # =====================================================================
    # Clear all session state
    # =====================================================================

    async def clear_session(self, session_id: str) -> None:
        """Clear all state for a session."""
        for prefix in (
            self._PFX_HIGH_RISK,
            self._PFX_LAST_CREATED,
            self._PFX_CLARIFICATION,
            self._PFX_SEARCH_HINT,
        ):
            await self._delete(prefix, session_id)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
conversation_state = ConversationStateService()
