"""Async client for SharePoint REST API operations."""

import json
import logging
from typing import Any, Dict, Optional

from src.domain.exceptions import SharePointProvisioningException
from src.infrastructure.services.authentication_service import AuthenticationService
from src.infrastructure.services.base_api_client import BaseAPIClient


logger = logging.getLogger(__name__)


class RESTAPIClient(BaseAPIClient):
    """Async client for SharePoint REST API with retry logic and error handling."""

    def __init__(self, auth_service: AuthenticationService, site_id: str, user_token: Optional[str] = None):
        super().__init__(auth_service, site_id)
        # Replace the synchronous session with an async httpx client
        self.http = self._build_client()
        self._site_web_url: Optional[str] = None
        self._user_token = user_token

    async def _get_headers(self, site_id: Optional[str] = None) -> Dict[str, str]:
        """Return auth headers using OBO (preferred) or App-Only authentication."""
        target_site_id = site_id or self.site_id
        if self._user_token:
            return await self.auth_service.get_rest_headers_obo(self._user_token, target_site_id)
        return await self.auth_service.get_rest_headers(target_site_id)

    async def get_site_url(self, site_id: Optional[str] = None) -> str:
        """Return the SharePoint site web URL (cached after first fetch)."""
        target_site_id = site_id or self.site_id
        
        # Only cache if using the default site_id
        if not site_id and self._site_web_url:
            return self._site_web_url

        endpoint = f"https://graph.microsoft.com/v1.0/sites/{target_site_id}"
        
        # For site URL resolution, we still use Graph headers
        if self._user_token:
            token = await self.auth_service.get_obo_graph_token(self._user_token)
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        else:
            headers = await self.auth_service.get_graph_headers()
            
        response = await self.http.get(endpoint, headers=headers)
        if response.is_success:
            web_url = response.json().get("webUrl", "")
            if not site_id:
                self._site_web_url = web_url
            return web_url

        raise SharePointProvisioningException(f"Could not determine SharePoint site URL for {target_site_id}")

    async def get(self, endpoint: str, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Async GET against the SharePoint REST API."""
        target_site_id = site_id or self.site_id
        url = endpoint if endpoint.startswith("https://") else f"{await self.get_site_url(target_site_id)}{endpoint}"
        headers = await self._get_headers(target_site_id)
        response = await self.http.get(url, headers=headers)
        if not response.is_success:
            raise SharePointProvisioningException(
                f"REST API GET failed: {response.status_code}. Response: {response.text}"
            )
        return response.json()

    async def post(self, endpoint: str, payload: Dict[str, Any], site_id: Optional[str] = None) -> Dict[str, Any]:
        """Async POST against the SharePoint REST API."""
        target_site_id = site_id or self.site_id
        url = endpoint if endpoint.startswith("https://") else f"{await self.get_site_url(target_site_id)}{endpoint}"
        headers = await self._get_headers(target_site_id)
        logger.debug("[RESTAPIClient] POST %s, Payload: %s", url, json.dumps(payload))
        response = await self.http.post(url, headers=headers, json=payload)
        logger.debug("[RESTAPIClient] POST %s Status: %s, Body: %s", url, response.status_code, response.text)
        if not response.is_success:
            raise SharePointProvisioningException(
                f"REST API POST failed: {response.status_code}. Response: {response.text}"
            )
        return response.json()
