"""Authentication service for Microsoft SharePoint APIs."""

import asyncio
import hashlib
import time
from typing import Dict, Optional, Tuple
import msal
from src.infrastructure.config import settings
from src.infrastructure.services.redis_security_store import security_store
from src.domain.exceptions import SharePointProvisioningException, PermissionDeniedException

import logging

logger = logging.getLogger(__name__)


class AuthenticationService:
    """Handles MSAL authentication and token management for SharePoint APIs."""

    def __init__(self):
        """Initialize MSAL confidential client application."""
        self.authority = f"https://login.microsoftonline.com/{settings.TENANT_ID}"
        self.client_id = settings.CLIENT_ID
        self.client_secret = settings.CLIENT_SECRET
        self.graph_scopes = ["https://graph.microsoft.com/.default"]
        self._obo_ttl = settings.OBO_CACHE_TTL_SECONDS
        
        self.app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=self.authority,
            client_credential=self.client_secret,
        )

    async def get_graph_access_token(self) -> str:
        """Get access token for Microsoft Graph API.
        
        Returns:
            Access token string
            
        Raises:
            SharePointProvisioningException: If token acquisition fails
        """
        import asyncio
        result = await asyncio.to_thread(self.app.acquire_token_silent, self.graph_scopes, None)
        if not result:
            result = await asyncio.to_thread(self.app.acquire_token_for_client, scopes=self.graph_scopes)
        
        if "access_token" in result:
            return result["access_token"]
        
        raise SharePointProvisioningException(
            f"Could not acquire Graph API access token: {result.get('error_description', 'Unknown error')}"
        )

    async def get_rest_access_token(self, site_id: str) -> str:
        """Get access token for SharePoint REST API.

        Args:
            site_id: SharePoint site ID (used as fallback for tenant hostname resolution)

        Returns:
            Access token string

        Raises:
            SharePointProvisioningException: If token acquisition fails
        """
        from urllib.parse import urlparse

        parsed = urlparse(getattr(settings, "SHAREPOINT_SITE_URL", "") or "")
        hostname = parsed.netloc
        if not hostname and site_id:
            # Fallback: extract from site_id which may contain domain
            parts = site_id.split(",")
            if len(parts) >= 1 and ".sharepoint.com" in parts[0]:
                hostname = parts[0]
        
        if not hostname:
            # Final fallback: check ALLOWED_SHAREPOINT_TENANTS
            tenants = getattr(settings, "ALLOWED_SHAREPOINT_TENANTS", "").split(",")
            if tenants and tenants[0]:
                hostname = f"{tenants[0].strip()}.sharepoint.com"

        if not hostname:
            raise SharePointProvisioningException(
                "Cannot determine SharePoint tenant domain for REST API. Please set SHAREPOINT_SITE_URL in .env."
            )
        rest_scopes = [f"https://{hostname}/.default"]

        result = await asyncio.to_thread(self.app.acquire_token_silent, rest_scopes, None)
        if not result:
            result = await asyncio.to_thread(
                self.app.acquire_token_for_client, scopes=rest_scopes
            )

        if "access_token" in result:
            return result["access_token"]

        raise SharePointProvisioningException(
            f"Could not acquire REST API access token: {result.get('error_description', 'Unknown error')}"
        )

    async def get_obo_graph_token(self, user_assertion: str) -> str:
        """Exchange a user's AAD token for a user-scoped Graph token via OBO flow.

        Uses the distributed SecurityStore for caching so that OBO tokens are
        shared across pods and survive restarts (when Redis is enabled).

        Args:
            user_assertion: The raw Bearer token from the user's request.

        Returns:
            A Graph access token scoped to the user's permissions.

        Raises:
            PermissionDeniedException: If the OBO exchange fails.
        """
        logger.debug(f"[get_obo_graph_token] Received assertion: {user_assertion is not None}, type: {type(user_assertion).__name__}")
        if user_assertion is None:
            logger.error("[get_obo_graph_token] user_assertion is None!")
            raise PermissionDeniedException(
                message="User assertion (token) is None. Cannot perform OBO exchange.",
                details={},
            )
        cache_key = hashlib.sha256(user_assertion.encode()).hexdigest()

        # Return cached token if still valid
        cached_token = security_store.get_obo_token(cache_key)
        if cached_token:
            return cached_token

        # requires the downstream audience's .default scope.
        obo_scopes = ["https://graph.microsoft.com/.default"]

        result = await asyncio.to_thread(
            self.app.acquire_token_on_behalf_of,
            user_assertion=user_assertion,
            scopes=obo_scopes,
        )

        if "access_token" in result:
            security_store.set_obo_token(cache_key, result["access_token"], self._obo_ttl)
            logger.debug("OBO token cached for %d seconds", self._obo_ttl)
            return result["access_token"]

        raise PermissionDeniedException(
            message=result.get("error_description", "OBO token exchange failed"),
            details={"error": result.get("error"), "suberror": result.get("suberror")},
        )

    async def get_obo_rest_token(self, user_assertion: str, site_id: str) -> str:
        """Exchange a user's AAD token for a user-scoped SharePoint REST token via OBO flow.

        Args:
            user_assertion: The raw Bearer token from the user's request.
            site_id: SharePoint site ID for tenant hostname resolution.

        Returns:
            A SharePoint REST access token scoped to the user's permissions.

        Raises:
            PermissionDeniedException: If the OBO exchange fails.
        """
        if user_assertion is None:
            raise PermissionDeniedException(
                message="User assertion (token) is None. Cannot perform OBO exchange.",
                details={},
            )

        from urllib.parse import urlparse
        parsed = urlparse(getattr(settings, "SHAREPOINT_SITE_URL", "") or "")
        hostname = parsed.netloc
        if not hostname and site_id:
            parts = site_id.split(",")
            if len(parts) >= 1 and ".sharepoint.com" in parts[0]:
                hostname = parts[0]
        
        if not hostname:
            # Final fallback: check ALLOWED_SHAREPOINT_TENANTS
            tenants = getattr(settings, "ALLOWED_SHAREPOINT_TENANTS", "").split(",")
            if tenants and tenants[0]:
                hostname = f"{tenants[0].strip()}.sharepoint.com"

        if not hostname:
            raise SharePointProvisioningException(
                "Cannot determine SharePoint tenant domain for REST API. Please set SHAREPOINT_SITE_URL in .env."
            )

        rest_scopes = [f"https://{hostname}/.default"]
        cache_key = hashlib.sha256(f"{user_assertion}:{hostname}".encode()).hexdigest()

        # Return cached token if still valid
        cached_token = security_store.get_obo_token(cache_key)
        if cached_token:
            return cached_token

        result = await asyncio.to_thread(
            self.app.acquire_token_on_behalf_of,
            user_assertion=user_assertion,
            scopes=rest_scopes,
        )

        if "access_token" in result:
            security_store.set_obo_token(cache_key, result["access_token"], self._obo_ttl)
            return result["access_token"]

        raise PermissionDeniedException(
            message=result.get("error_description", "OBO REST token exchange failed"),
            details={"error": result.get("error"), "suberror": result.get("suberror")},
        )

    def invalidate_obo_cache(self, user_assertion: str) -> None:
        """Force-evict a cached OBO token (e.g. after permission change)."""
        cache_key = hashlib.sha256(user_assertion.encode()).hexdigest()
        security_store.invalidate_obo_token(cache_key)
        logger.info("OBO cache invalidated for assertion hash %s…", cache_key[:12])

    async def get_graph_headers(self) -> Dict[str, str]:
        """Get HTTP headers for Graph API requests.

        Returns:
            Dictionary of HTTP headers with authorization
        """
        token = await self.get_graph_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def get_rest_headers(self, site_id: str) -> Dict[str, str]:
        """Get HTTP headers for SharePoint REST API requests.

        Args:
            site_id: SharePoint site ID for token scope

        Returns:
            Dictionary of HTTP headers with authorization and OData verbose format
        """
        token = await self.get_rest_access_token(site_id)
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json;odata=verbose",
            "Content-Type": "application/json;odata=verbose",
        }
    async def get_rest_headers_obo(self, user_assertion: str, site_id: str) -> Dict[str, str]:
        """Get HTTP headers for SharePoint REST API requests using OBO token.

        Args:
            user_assertion: User's AAD token
            site_id: SharePoint site ID for token scope

        Returns:
            Dictionary of HTTP headers with user-scoped authorization
        """
        token = await self.get_obo_rest_token(user_assertion, site_id)
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json;odata=verbose",
            "Content-Type": "application/json;odata=verbose",
        }
