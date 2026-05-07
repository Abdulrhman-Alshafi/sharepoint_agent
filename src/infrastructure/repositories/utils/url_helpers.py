"""URL helper utilities for SharePoint operations."""

import re
from typing import Optional
from src.domain.exceptions import SharePointProvisioningException


class URLHelpers:
    """Helper utilities for SharePoint URL operations."""

    @staticmethod
    def generate_page_name(title: str) -> str:
        """Generate a URL-safe page name from a title.
        
        SharePoint page names must:
        - Be URL-safe
        - End with .aspx
        - Not contain special characters
        
        Args:
            title: Page title
            
        Returns:
            URL-safe page name ending with .aspx
        """
        # Remove or replace special characters
        safe_name = re.sub(r'[^a-zA-Z0-9\s-]', '', title)
        # Replace spaces with hyphens and convert to lowercase
        safe_name = re.sub(r'\s+', '-', safe_name.strip()).lower()
        # Ensure it ends with .aspx
        if not safe_name.endswith('.aspx'):
            safe_name = f"{safe_name}.aspx"
        return safe_name

    @staticmethod
    def get_site_base_url(
        site_id: str,
        cached_url: Optional[str] = None,
        http_session=None,
        headers: Optional[dict] = None,
        **_kwargs,
    ) -> str:
        """Derive the SharePoint site base URL.

        Returns ``cached_url`` immediately if provided.  Otherwise queries the
        Microsoft Graph API synchronously using *http_session*.

        Args:
            site_id: SharePoint site ID used to build the Graph API URL.
            cached_url: Return this directly when supplied (no network call).
            http_session: A :class:`requests.Session`-compatible object used
                to make the HTTP GET request.
            headers: HTTP headers (e.g. ``Authorization``) for the request.

        Returns:
            The SharePoint site ``webUrl``.

        Raises:
            SharePointProvisioningException: When the API call fails.
        """
        if cached_url:
            return cached_url

        url = f"https://graph.microsoft.com/v1.0/sites/{site_id}"
        response = http_session.get(url, headers=headers or {})
        if not response.ok:
            raise SharePointProvisioningException(
                f"Failed to retrieve site base URL for site_id={site_id!r}"
            )
        return response.json()["webUrl"]
