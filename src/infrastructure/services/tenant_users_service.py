"""Tenant user directory service — fetches real users from Microsoft Graph.

Used to inject actual user names and emails into AI prompts so that
generated seed data for ``personOrGroup`` columns references real people
instead of fabricated names.
"""

import time
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Module-level cache: (timestamp, data)
_user_cache: Dict[str, Any] = {"ts": 0.0, "users": []}
_CACHE_TTL = 600  # 10 minutes


class TenantUsersService:
    """Fetch and cache tenant users from Microsoft Graph."""

    @staticmethod
    async def get_tenant_users(
        repository: Any,
        site_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, str]]:
        """Return a list of ``{"displayName": ..., "email": ...}`` dicts.

        Strategy:
        1. Try ``GET /users`` (requires ``User.Read.All`` or ``User.ReadBasic.All``).
        2. Fall back to ``get_site_members(site_id)`` which only needs Sites scopes.
        3. If everything fails, return an empty list (non-fatal).

        Results are cached for ``_CACHE_TTL`` seconds.
        """
        now = time.time()
        if _user_cache["users"] and (now - _user_cache["ts"]) < _CACHE_TTL:
            return _user_cache["users"]

        users: List[Dict[str, str]] = []

        # ── Strategy 1: Graph /users endpoint ────────────────────────────
        try:
            graph_client = getattr(repository, "graph_client", None)
            if graph_client:
                data = await graph_client.get(
                    f"/users?$top={limit}&$select=displayName,mail,userPrincipalName"
                )
                for u in data.get("value", []):
                    display = u.get("displayName", "")
                    email = u.get("mail") or u.get("userPrincipalName", "")
                    if display and email:
                        users.append({"displayName": display, "email": email})
                if users:
                    logger.info("TenantUsersService: fetched %d users from /users", len(users))
                    _user_cache.update({"ts": now, "users": users})
                    return users
        except Exception as e:
            logger.debug("TenantUsersService: /users failed (%s), falling back to site members", e)

        # ── Strategy 2: Site members fallback ────────────────────────────
        try:
            if site_id and hasattr(repository, "get_site_members"):
                members = await repository.get_site_members(site_id)
                for m in members:
                    display = m.get("displayName", "")
                    email = m.get("email") or m.get("mail") or m.get("userPrincipalName", "")
                    if display and email:
                        users.append({"displayName": display, "email": email})
                if users:
                    logger.info("TenantUsersService: fetched %d users from site members", len(users))
                    _user_cache.update({"ts": now, "users": users})
                    return users
        except Exception as e:
            logger.debug("TenantUsersService: site members fallback failed: %s", e)

        # ── Strategy 3: Empty (non-fatal) ────────────────────────────────
        logger.warning("TenantUsersService: could not fetch any real users — seed data will use AI-generated names")
        return []

    @staticmethod
    def format_for_prompt(users: List[Dict[str, str]], max_users: int = 20) -> str:
        """Format user list into a string suitable for AI prompt injection.

        Returns something like:
        ``"Real tenant users: Ahmad Ali (ahmad@co.com), Sara Khalid (sara@co.com), ..."``
        """
        if not users:
            return ""
        subset = users[:max_users]
        entries = [f"{u['displayName']} ({u['email']})" for u in subset]
        return "Real tenant users available: " + ", ".join(entries)

    @staticmethod
    def clear_cache():
        """Clear the user cache (useful for testing)."""
        _user_cache.update({"ts": 0.0, "users": []})

    @staticmethod
    async def find_user_by_name(
        repository: Any,
        name_query: str,
        site_id: Optional[str] = None,
    ) -> Optional[Dict[str, str]]:
        """Search tenant users by display name (fuzzy match).

        Args:
            repository: Repository with graph_client/get_site_members
            name_query: Name or partial name to search for
            site_id: Optional site ID override

        Returns:
            First matching user dict {"displayName": ..., "email": ...} or None
        """
        if not name_query or not isinstance(name_query, str):
            return None

        query_lower = name_query.lower().strip()
        if not query_lower:
            return None

        users = await TenantUsersService.get_tenant_users(repository, site_id=site_id)
        if not users:
            logger.debug("No tenant users available for name search")
            return None

        # Exact match first
        for user in users:
            if user.get("displayName", "").lower() == query_lower:
                return user

        # Fuzzy match: first/last name or substring
        for user in users:
            display = user.get("displayName", "").lower()
            # Match if query is in display name
            if query_lower in display:
                return user
            # Match if any word in display name matches query
            for word in display.split():
                if query_lower == word or query_lower in word:
                    return user

        return None

    @staticmethod
    def is_email_like(value: str) -> bool:
        """Check if a string looks like an email address."""
        if not isinstance(value, str):
            return False
        return "@" in value and "." in value.split("@")[-1]
