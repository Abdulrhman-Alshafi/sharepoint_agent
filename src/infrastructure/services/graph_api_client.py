"""Async client for Microsoft Graph API operations."""

from typing import Any, Dict, Optional

import httpx
import json

from src.domain.exceptions import (
    SharePointProvisioningException,
    SharePointAPIError,
    PermissionDeniedException,
    AuthenticationException,
    RateLimitError,
    ExternalServiceUnavailableError,
    ExternalTimeoutError,
)
from src.infrastructure.services.authentication_service import AuthenticationService
from src.infrastructure.services.base_api_client import BaseAPIClient
from src.infrastructure.resilience import graph_breaker
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class GraphAPIClient(BaseAPIClient):
    """Async client for Microsoft Graph API with retry logic and error handling."""

    def __init__(self, auth_service: AuthenticationService, site_id: str, user_token: Optional[str] = None):
        super().__init__(auth_service, site_id)
        # Replace the synchronous session with an async httpx client
        self.http = self._build_client()
        self.base_url = "https://graph.microsoft.com/v1.0"
        self.beta_base_url = "https://graph.microsoft.com/beta"
        self._user_token = user_token

    async def _get_headers(self) -> dict:
        """Return auth headers using OBO (preferred) or App-Only authentication.
        
        If a user token is present, exchanges it for a Graph token via OBO flow.
        Otherwise, falls back to App-Only (Client Credentials) flow for system contexts.
        """
        if not self._user_token:
            # Fall back to App-Only auth for non-user contexts (e.g. health check)
            logger.debug("[_get_headers] No user token; falling back to App-Only authentication.")
            token = await self.auth_service.get_graph_access_token()
            return {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            
        # OBO: Exchange user token for Graph API access
        logger.debug(f"[_get_headers] User token present: {self._user_token is not None}, token length: {len(self._user_token) if self._user_token else 0}")
        obo_token = await self.auth_service.get_obo_graph_token(self._user_token)
        return {
            "Authorization": f"Bearer {obo_token}",
            "Content-Type": "application/json",
        }

    # ── Shared error handling ────────────────────────────────────────────────

    def _raise_for_status(self, response: httpx.Response, operation: str) -> None:
        """Raise a typed domain exception based on the HTTP status code."""
        if response.is_success:
            graph_breaker.record_success()
            return
        if response.status_code == 401:
            raise AuthenticationException(
                message="Your session has expired or the token is invalid. Please sign in again.",
                details={"status": 401, "endpoint": operation},
            )
        if response.status_code == 403:
            raise PermissionDeniedException(
                message="You don't have permission to perform this action on the requested resource.",
                details={"status": 403, "endpoint": operation},
            )
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", "10"))
            graph_breaker.record_failure()
            raise RateLimitError(
                service="Microsoft Graph API",
                retry_after=retry_after,
                details={"endpoint": operation},
            )
        if response.status_code in (503, 504):
            graph_breaker.record_failure()
            raise ExternalServiceUnavailableError(
                service="Microsoft Graph API",
                details={"status": response.status_code, "endpoint": operation},
            )
        if response.status_code >= 500:
            graph_breaker.record_failure()
        
        raise SharePointProvisioningException(
            f"{operation} failed with status {response.status_code}. Response: {response.text[:500]}"
        )

    def _handle_request_error(self, exc: Exception, operation: str) -> None:
        """Convert httpx transport errors to typed domain exceptions."""
        graph_breaker.record_failure()
        if isinstance(exc, httpx.TimeoutException):
            raise ExternalTimeoutError(
                service="Microsoft Graph API",
                details={"endpoint": operation, "error": str(exc)},
            ) from exc
        if isinstance(exc, httpx.ConnectError):
            raise ExternalServiceUnavailableError(
                service="Microsoft Graph API",
                details={"endpoint": operation, "error": str(exc)},
            ) from exc
        raise SharePointAPIError(
            message=f"{operation} error: {exc}",
            endpoint=operation,
        ) from exc

    # ── v1.0 methods ─────────────────────────────────────────────────────────

    async def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None, extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        url = endpoint if endpoint.startswith("https://") else f"{self.base_url}{endpoint}"
        headers = await self._get_headers()
        if extra_headers:
            headers.update(extra_headers)
        graph_breaker.check()
        try:
            response = await self.http.get(url, headers=headers, params=params)
            self._raise_for_status(response, f"Graph API GET {endpoint}")
            return response.json()
        except (AuthenticationException, PermissionDeniedException, RateLimitError,
                ExternalServiceUnavailableError, ExternalTimeoutError,
                SharePointProvisioningException, SharePointAPIError):
            raise
        except httpx.RequestError as exc:
            self._handle_request_error(exc, f"Graph API GET {endpoint}")
            return {}  # unreachable, satisfies type checker

    async def post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = endpoint if endpoint.startswith("https://") else f"{self.base_url}{endpoint}"
        headers = await self._get_headers()
        logger.debug("[GraphAPIClient] POST %s, Payload: %s", url, json.dumps(payload))
        graph_breaker.check()
        try:
            response = await self.http.post(url, headers=headers, json=payload)
            logger.debug("[GraphAPIClient] POST %s Status: %s, Body: %s", url, response.status_code, response.text)
            self._raise_for_status(response, f"Graph API POST {endpoint}")
            
            # Handle 202 Accepted for async operations (common in site/page creation)
            body = response.json() if response.content else {}
            if response.status_code == 202:
                body["_provisioning"] = True
                location = response.headers.get("Location") or response.headers.get("location", "")
                if location:
                    body["_poll_url"] = location
            return body
        except (AuthenticationException, PermissionDeniedException, RateLimitError,
                ExternalServiceUnavailableError, ExternalTimeoutError,
                SharePointProvisioningException, SharePointAPIError):
            raise
        except httpx.RequestError as exc:
            self._handle_request_error(exc, f"Graph API POST {endpoint}")
            return {}

    async def patch(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = endpoint if endpoint.startswith("https://") else f"{self.base_url}{endpoint}"
        headers = await self._get_headers()
        logger.debug("[GraphAPIClient] PATCH %s, Payload: %s", url, json.dumps(payload))
        graph_breaker.check()
        try:
            response = await self.http.patch(url, headers=headers, json=payload)
            logger.debug("[GraphAPIClient] PATCH %s Status: %s, Body: %s", url, response.status_code, response.text)
            self._raise_for_status(response, f"Graph API PATCH {endpoint}")
            return response.json()
        except (AuthenticationException, PermissionDeniedException, RateLimitError,
                ExternalServiceUnavailableError, ExternalTimeoutError,
                SharePointProvisioningException, SharePointAPIError):
            raise
        except httpx.RequestError as exc:
            self._handle_request_error(exc, f"Graph API PATCH {endpoint}")
            return {}

    async def delete(self, endpoint: str) -> bool:
        url = endpoint if endpoint.startswith("https://") else f"{self.base_url}{endpoint}"
        headers = await self._get_headers()
        graph_breaker.check()
        try:
            response = await self.http.delete(url, headers=headers)
            self._raise_for_status(response, f"Graph API DELETE {endpoint}")
            return True
        except (AuthenticationException, PermissionDeniedException, RateLimitError,
                ExternalServiceUnavailableError, ExternalTimeoutError,
                SharePointProvisioningException, SharePointAPIError):
            raise
        except httpx.RequestError as exc:
            self._handle_request_error(exc, f"Graph API DELETE {endpoint}")
            return False

    # Beta methods aliased to v1.0 for backward compatibility
    async def get_beta(self, endpoint, params=None, extra_headers=None):
        return await self.get(endpoint, params, extra_headers)

    async def post_beta(self, endpoint, payload):
        return await self.post(endpoint, payload)

    async def patch_beta(self, endpoint, payload):
        return await self.patch(endpoint, payload)
