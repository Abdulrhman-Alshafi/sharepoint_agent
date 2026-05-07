"""User status revalidation service for token revocation mitigation.

Azure AD JWTs remain valid until expiry even after a user is disabled.
This service performs a lightweight Graph /me check (via OBO exchange)
to verify the account is still active, with a short-lived cache (2 min)
to avoid throttling.

Usage::

    from src.infrastructure.services.user_status_service import require_active_user

    @router.post("/sensitive")
    async def sensitive_op(
        request: Request,
        current_user: str = Depends(get_current_user),
        _active: bool = Depends(require_active_user),
    ):
        ...
"""

import hashlib
import logging
import time
import threading

import httpx
from fastapi import HTTPException, Request, status

from src.domain.exceptions import AuthenticationException

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lightweight cache: hash(token) -> (is_active, expiry_monotonic)
# Short TTL (2 min) balances security vs. Graph API throttling.
# ---------------------------------------------------------------------------
_STATUS_CACHE_TTL = 120  # seconds
_status_cache: dict = {}
_status_lock = threading.Lock()


async def check_user_active(user_token: str) -> bool:
    """Verify the user's Azure AD account is still active via Graph /me.

    Handles both direct Graph tokens and backend API tokens (via OBO).
    Results are cached for 2 minutes to avoid excessive Graph calls.
    """
    token_hash = hashlib.sha256(user_token.encode()).hexdigest()

    # 1. Check local cache first
    with _status_lock:
        entry = _status_cache.get(token_hash)
        if entry and time.monotonic() < entry[1]:
            if not entry[0]:
                raise AuthenticationException(
                    "Your account has been disabled or the session has been revoked. "
                    "Please sign in again."
                )
            return True

    # 2. Determine if we need OBO or if this is already a Graph token
    is_graph_token = False
    try:
        import jwt as _jwt
        unverified = _jwt.decode(user_token, options={"verify_signature": False})
        aud = unverified.get("aud", "")
        # Graph App ID (00000003-0000-0000-c000-000000000000) or Graph audience string
        if aud == "00000003-0000-0000-c000-000000000000" or "graph.microsoft.com" in str(aud):
            is_graph_token = True
            logger.debug("User status check: token is already Graph-scoped.")
    except Exception:
        pass

    # 3. Get a Graph-scoped token
    auth_service = None
    if is_graph_token:
        graph_token = user_token
    else:
        try:
            from src.infrastructure.services.authentication_service import AuthenticationService
            auth_service = AuthenticationService()
            graph_token = await auth_service.get_obo_graph_token(user_token)
        except Exception as exc:
            # OBO exchange failed — fail open (don't block if MSAL is having issues)
            logger.warning("User status check: OBO exchange failed (fail-open): %s", exc)
            return True

    # 4. Call Graph /me
    async def _call_me(t: str):
        async with httpx.AsyncClient() as client:
            return await client.get(
                "https://graph.microsoft.com/v1.0/me"
                "?$select=id,accountEnabled,userPrincipalName",
                headers={"Authorization": f"Bearer {t}"},
                timeout=8,
            )

    try:
        response = await _call_me(graph_token)
        
        # If 401 and we used a cached OBO token, try one more time with a fresh one
        if response.status_code == 401 and not is_graph_token and auth_service:
            logger.info("User status check: Graph returned 401. Retrying with fresh OBO...")
            auth_service.invalidate_obo_cache(user_token)
            graph_token = await auth_service.get_obo_graph_token(user_token)
            response = await _call_me(graph_token)

    except (httpx.TimeoutException, httpx.RequestError) as exc:
        # Network error — fail open with a warning (don't block legitimate users)
        logger.warning("User status check failed (network): %s — allowing request", exc)
        return True

    # 5. Handle Response
    if response.status_code == 401:
        # Capture WWW-Authenticate header for debugging (e.g. "expired_token", "invalid_token")
        www_auth = response.headers.get("WWW-Authenticate", "")
        logger.warning("User status check: Graph rejected token with 401. WWW-Auth: %s", www_auth)
        
        _cache_status(token_hash, False)
        raise AuthenticationException(
            "Your session has expired or been revoked. Please sign in again."
        )

    if not response.is_success:
        # Non-auth failure — fail open to avoid blocking on Graph outages
        logger.warning("User status check: Graph returned HTTP %d — allowing request", response.status_code)
        return True

    me = response.json()
    account_enabled = me.get("accountEnabled", True)

    if not account_enabled:
        logger.warning("User status check: Account DISABLED for user %s", me.get("userPrincipalName"))
        _cache_status(token_hash, False)
        raise AuthenticationException(
            "Your account has been disabled. Please contact your administrator."
        )

    _cache_status(token_hash, True)
    return True


def _cache_status(token_hash: str, is_active: bool) -> None:
    with _status_lock:
        _status_cache[token_hash] = (is_active, time.monotonic() + _STATUS_CACHE_TTL)
        # Bound memory
        if len(_status_cache) > 10_000:
            oldest = sorted(_status_cache.items(), key=lambda kv: kv[1][1])[:1000]
            for k, _ in oldest:
                del _status_cache[k]


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

async def require_active_user(request: Request) -> bool:
    """FastAPI dependency that verifies the user's account is still active.

    Should be added to all write/destructive endpoints.  Extracts the
    Bearer token from the Authorization header, exchanges it for a
    Graph token via OBO, and calls Graph /me.

    Raises HTTPException(401) if the user's account is disabled or the
    token is revoked.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required for this operation.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header[7:]
    try:
        await check_user_active(token)
        return True
    except AuthenticationException as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )
