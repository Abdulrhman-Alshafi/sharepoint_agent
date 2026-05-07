"""Graph service for deploying packages to the SharePoint tenant app catalog."""

from pathlib import Path
from typing import Any, Dict

import httpx
import msal

from src.domain.exceptions import SharePointProvisioningException
from src.infrastructure.config import settings


class GraphService:
    """Wrapper around Graph API app catalog deployment operations."""

    def __init__(self):
        self.authority = f"https://login.microsoftonline.com/{settings.TENANT_ID}"
        self.client_id = settings.CLIENT_ID
        self.client_secret = settings.CLIENT_SECRET
        self.scopes = ["https://graph.microsoft.com/.default"]
        self.app_catalog_site_id = settings.APP_CATALOG_SITE_ID or settings.SITE_ID

        if not self.app_catalog_site_id:
            raise SharePointProvisioningException(
                "APP_CATALOG_SITE_ID or SITE_ID must be configured for app catalog deployment"
            )

        self.app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=self.authority,
            client_credential=self.client_secret,
        )

    def _get_access_token(self) -> str:
        result = self.app.acquire_token_silent(self.scopes, account=None)
        if not result:
            result = self.app.acquire_token_for_client(scopes=self.scopes)

        if "access_token" in result:
            return result["access_token"]

        raise SharePointProvisioningException(
            f"Could not acquire access token: {result.get('error_description', 'Unknown error')}"
        )

    def _get_headers(self, content_type: str = "application/octet-stream") -> Dict[str, str]:
        token = self._get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type,
        }

    async def deploy_to_app_catalog(self, package_path: str) -> Dict[str, Any]:
        """Upload a .sppkg binary file to the SharePoint tenant app catalog."""
        import asyncio
        package_file = Path(package_path)

        if not package_file.exists() or not package_file.is_file():
            raise SharePointProvisioningException(f"Package file not found: {package_path}")

        upload_endpoint = (
            f"https://graph.microsoft.com/v1.0/sites/{self.app_catalog_site_id}"
            f"/drive/root:/{package_file.name}:/content"
        )

        token = await asyncio.to_thread(self._get_access_token)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
        }
        file_content = await asyncio.to_thread(lambda: package_file.read_bytes())
        async with httpx.AsyncClient() as client:
            response = await client.put(upload_endpoint, headers=headers, content=file_content)

        if not response.is_success:
            raise SharePointProvisioningException(
                f"Failed to deploy package to app catalog. "
                f"Status: {response.status_code}. Response: {response.text}"
            )

        return response.json()
