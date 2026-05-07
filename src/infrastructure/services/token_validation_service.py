"""Service for validating Azure AD JWT tokens.

Authentication strategy (two-tier, by design):

1. **Primary — JWKS signature verification** (cryptographic trust):
   JWT tokens issued for *this application's audience* (api://CLIENT_ID)
   are verified using Microsoft's published JWKS signing keys.  This is the
   preferred path — fast, offline-capable, and cryptographically sound.

2. **Fallback — Graph /me liveness check** (runtime trust):
   Microsoft Graph tokens have *intentionally unverifiable* signatures
   (Microsoft does not publish the signing keys for Graph-audience tokens).
   When JWKS verification returns ``InvalidSignatureError``, the token is
   instead validated by calling Graph /me: if Microsoft accepts it and
   returns a user profile, the token is genuine.

   This fallback is guarded by the Graph API circuit breaker to prevent
   cascading failures when Graph is throttled or unavailable.  If the
   circuit is open, the token is **rejected** (fail-closed).

Both paths cache validated payloads in the distributed SecurityStore
(Redis or in-memory) for 5 minutes to eliminate repeated network calls.
"""

import hashlib
import logging
import time
import httpx
import jwt
from typing import Dict, Any, Optional

from src.domain.exceptions import AuthenticationException
from src.infrastructure.config import settings
from src.infrastructure.resilience import graph_breaker
from src.infrastructure.services.redis_security_store import security_store

logger = logging.getLogger(__name__)

# Cache TTL for validated token payloads (seconds)
_CACHE_TTL_SECONDS = 300  # 5 minutes


class TokenValidationService:
    """Service to cryptographically validate Azure AD Bearer tokens."""
    
    def __init__(self):
        self.settings = settings
        
        # Use tenant-specific JWKS endpoint when TENANT_ID is configured.
        tenant = (
            getattr(self.settings, 'TENANT_ID', None)
            or getattr(self.settings, 'tenant_id', None)
            or "common"
        )
        self.jwks_url = f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys"
        self.jwks_client = jwt.PyJWKClient(self.jwks_url)

    async def validate_token(self, token: str) -> Dict[str, Any]:
        """Validate the JWT token and return its payload.

        Tries the distributed cache first (5-min TTL), then JWKS signature
        verification. For Graph-scoped tokens (unverifiable signature by
        design), falls back to a live Graph /me call to prove authenticity.
        The Graph fallback is protected by a circuit breaker.
        """
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        # 1. Cache hit — skip all network calls
        cached = security_store.get_token_payload(token_hash)
        if cached is not None:
            return cached

        token_prefix = token[:20] + "..." if len(token) > 20 else token
        parts = token.split(".")

        if len(parts) != 3:
            raise AuthenticationException("The token is malformed or invalid.")

        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            # Accept both bare CLIENT_ID and api://CLIENT_ID audiences so that
            # tokens acquired by the frontend via getToken('api://CLIENT_ID')
            # pass validation without a 401.
            if self.settings.CLIENT_ID:
                valid_audiences = [
                    self.settings.CLIENT_ID,
                    f"api://{self.settings.CLIENT_ID}",
                ]
                decode_options = {"verify_exp": True}
            else:
                valid_audiences = None
                decode_options = {"verify_aud": False, "verify_exp": True}

            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=valid_audiences,
                options=decode_options,
            )
            payload["_source"] = "jwks"
            security_store.set_token_payload(token_hash, payload, _CACHE_TTL_SECONDS)
            return payload

        except jwt.exceptions.ExpiredSignatureError:
            raise AuthenticationException("The provided token has expired.")
        except jwt.exceptions.InvalidSignatureError:
            # Graph tokens have intentionally unverifiable signatures.
            # Prove the token is genuine by calling Graph /me.
            logger.info(
                "JWT signature unverifiable (likely a Graph-audience token). "
                "Falling back to Graph /me validation."
            )
            return await self._validate_graph_token_via_me_endpoint(token, token_prefix)
        except jwt.exceptions.PyJWKClientError as e:
            logger.error(f"JWKS fetch failed: {type(e).__name__}: {e}")
            raise AuthenticationException(f"Failed to fetch Microsoft signing keys: {e}")
        except (jwt.exceptions.DecodeError, jwt.exceptions.InvalidAlgorithmError) as e:
            logger.error(f"JWT decode error: {type(e).__name__}: {e}")
            raise AuthenticationException("The token is malformed or invalid.")
        except Exception as e:
            logger.error(f"Unexpected token validation error: {type(e).__name__}: {e}", exc_info=True)
            raise AuthenticationException(f"Token validation failed: {type(e).__name__}")

    async def _validate_graph_token_via_me_endpoint(self, token: str, token_prefix: str) -> Dict[str, Any]:
        """Securely validate a Microsoft Graph token by calling Graph /me.

        Graph tokens have signatures that cannot be verified by third parties.
        The only secure way to validate them is to use them: if Microsoft's
        Graph API accepts the token and returns a user profile, the token is genuine.

        This method is protected by the Graph API circuit breaker.  If the
        breaker is open (Graph recently failed repeatedly), the token is
        **rejected** rather than silently accepted — fail-closed security.

        Args:
            token: Raw JWT string from the request.
            token_prefix: Safe log prefix (first 20 chars + '...').

        Returns:
            A payload dict containing at minimum 'preferred_username' and 'name',
            structured like a standard JWT payload so the rest of the auth flow
            works unchanged.

        Raises:
            AuthenticationException: If Graph rejects the token, returns an error,
            or the circuit breaker is open.
        """
        # ── Circuit breaker check ─────────────────────────────────────────
        from src.domain.exceptions import CircuitBreakerOpenError
        try:
            graph_breaker.check()
        except CircuitBreakerOpenError:
            logger.warning(
                "Graph /me circuit breaker is OPEN — rejecting token (fail-closed). "
                "Graph API may be down or throttled."
            )
            raise AuthenticationException(
                "Token validation is temporarily unavailable due to Microsoft Graph issues. "
                "Please try again in a few moments."
            )

        try:
            t0 = time.monotonic()
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://graph.microsoft.com/v1.0/me",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10,
                )
            elapsed_ms = int((time.monotonic() - t0) * 1000)
        except httpx.TimeoutException:
            graph_breaker.record_failure()
            logger.error("Graph /me validation timed out.")
            raise AuthenticationException("Token validation timed out — could not reach Microsoft Graph.")
        except httpx.RequestError as e:
            graph_breaker.record_failure()
            logger.error(f"Graph /me request failed: {type(e).__name__}: {str(e)}")
            raise AuthenticationException("Token validation failed — could not reach Microsoft Graph.")

        if response.status_code == 401:
            # Token is genuinely invalid — not a Graph failure
            raise AuthenticationException("The provided token is invalid or has expired.")

        if response.status_code == 429 or response.status_code >= 500:
            # Graph throttling or server error — record as circuit failure
            graph_breaker.record_failure()
            logger.warning(
                "Graph /me returned HTTP %d during token validation", response.status_code
            )
            raise AuthenticationException(
                f"Token validation failed — Graph returned HTTP {response.status_code}."
            )

        if not response.is_success:
            try:
                err_detail = response.json().get("error", {}).get("message", response.text[:300])
            except Exception:
                err_detail = response.text[:300]
            logger.error(f"Graph /me returned HTTP {response.status_code}: {err_detail}")
            raise AuthenticationException(f"Token validation failed — Graph returned HTTP {response.status_code}.")

        # Success — record for circuit breaker
        graph_breaker.record_success()

        me = response.json()
        upn = me.get("userPrincipalName") or me.get("mail") or me.get("displayName", "")
        logger.info(f"Graph /me auth OK ({elapsed_ms}ms) — user: {upn}")

        payload = {
            "preferred_username": upn,
            "name": me.get("displayName", ""),
            "oid": me.get("id", ""),
            "iss": "https://graph.microsoft.com/v1.0/me",
            "_source": "graph_me",
        }
        # Use a shorter TTL for Graph-validated tokens (no exp claim to rely on)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        security_store.set_token_payload(token_hash, payload, _CACHE_TTL_SECONDS)
        return payload

    def extract_user_identity(self, payload: Dict[str, Any]) -> str:
        """Extract the user's UPN/email from the token payload."""
        for claim in ["upn", "preferred_username", "unique_name", "email"]:
            identity = payload.get(claim)
            if identity:
                return identity

        logger.error(
            f"No identity claim found. Available: {list(payload.keys())}, "
            f"iss={payload.get('iss')}, aud={payload.get('aud')}"
        )
        raise AuthenticationException("Token does not contain a recognizable identity claim (upn/email).")
