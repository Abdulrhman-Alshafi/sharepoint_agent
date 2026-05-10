"""Service for SharePoint Page operations."""

import logging
import json
from typing import Dict, Any, Optional, List
from src.domain.entities import SPPage
from src.domain.exceptions import SharePointProvisioningException
from src.infrastructure.services.rest_api_client import RESTAPIClient
from src.infrastructure.services.graph_api_client import GraphAPIClient
from src.infrastructure.repositories.utils.canvas_builder import CanvasContentBuilder
from src.infrastructure.repositories.utils.url_helpers import URLHelpers
from src.infrastructure.repositories.utils.constants import SharePointConstants
from src.infrastructure.repositories.utils.error_handlers import handle_sharepoint_errors

logger = logging.getLogger(__name__)


class PageService:
    """Handles all SharePoint Page operations."""

    def __init__(self, rest_client: RESTAPIClient, graph_client: Optional[GraphAPIClient] = None):
        """Initialize page service.
        
        Args:
            rest_client: REST API client for making requests
            graph_client: Optional Graph API client for v1.0 endpoints
        """
        self.rest_client = rest_client
        self.graph_client = graph_client

    @handle_sharepoint_errors("create page")
    async def create_page(self, sp_page: SPPage, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a page in SharePoint via Microsoft Graph API.
        
        Args:
            sp_page: SPPage entity to create
            
        Returns:
            Created page data including resource_link
        """
        # Use Graph API (modern approach) instead of REST API
        if not self.graph_client:
            raise SharePointProvisioningException(
                "Graph API client required for page creation. REST API not supported with OAuth."
            )
        
        # Generate a URL-safe page name (must end with .aspx)
        page_name_base = URLHelpers.generate_page_name(sp_page.title)
        if not page_name_base.endswith('.aspx'):
            page_name_base += '.aspx'
        
        logger.debug("Creating page with name: %s", page_name_base)
        logger.debug("Page title: %s", sp_page.title)
        target_site_id = site_id or self.graph_client.site_id
        logger.debug("Site ID: %s", target_site_id)
        
        # Define endpoint and layouts
        endpoint_v1 = f"/sites/{target_site_id}/pages"
        _valid_layouts = {"article", "home", "singleWebPartApp"}
        page_layout = getattr(sp_page, "layout", "article")
        if page_layout not in _valid_layouts:
            page_layout = "article"

        payload = {
            "@odata.type": "#microsoft.graph.sitePage",
            "name": page_name_base,
            "title": sp_page.title,
            "pageLayout": page_layout,
            "publishingState": {
                "level": "draft"
            },
        }
        
        logger.info("[PageService] Attempting page creation on site '%s'. Payload: %s", target_site_id, json.dumps(payload))
        
        try:
            data = await self.graph_client.post(endpoint_v1, payload)
            logger.info("SUCCESS with v1.0 endpoint for page '%s'", sp_page.title)
        except Exception as e_v1:
            logger.warning("[PageService] Graph API v1.0 page creation failed for '%s'. Error: %s", sp_page.title, str(e_v1))
            if hasattr(e_v1, 'response'):
                logger.error("[PageService] v1.0 Status: %s, Body: %s", e_v1.response.status_code, e_v1.response.text)
            
            logger.info("Attempting fallback to SharePoint REST API (via OBO)...")
            try:
                data = await self._create_page_rest_fallback(sp_page, target_site_id)
                logger.info("SUCCESS with REST API fallback for page '%s'", sp_page.title)
                is_rest_created = True
            except Exception as e_rest:
                logger.error("FINAL FAILURE: REST API fallback also failed: %s", e_rest)
                raise SharePointProvisioningException(
                    f"Failed to create page '{sp_page.title}' via Graph API v1.0 and REST API. "
                    f"Graph Error: {str(e_v1)}. REST Error: {str(e_rest)}"
                ) from e_rest
        else:
            is_rest_created = False
        
        logger.debug("Page creation source: %s", "REST" if is_rest_created else "Graph")
        logger.debug("Response data: %s", data)
        
        # Extract page information from Graph API response
        page_id = data.get("id", "")
        page_url = data.get("webUrl", "")
        
        logger.debug("Page ID: %s", page_id)
        logger.debug("Page URL from response: %s", page_url)
        
        # Try to get the actual page URL from various response fields
        if not page_url:
            # Sometimes it's in a different field
            page_url = data.get("url", "") or data.get("serverRelativeUrl", "")
            logger.debug("Alternative URL found: %s", page_url)
        
        # Step 2: PATCH the page with canvas content (always, not just when webparts exist).
        # Sending canvasLayout in a separate PATCH avoids 400s on initial creation.
        if page_id and not is_rest_created:
            logger.debug("Adding %d webparts to page via PATCH...", len(sp_page.webparts))
            try:
                canvas_layout = self._build_canvas_layout(sp_page.webparts)
                update_payload = {
                    "canvasLayout": canvas_layout
                }
                # Use /pages/{id} endpoint for PATCH (not /microsoft.graph.sitePage cast)
                update_endpoint = f"/sites/{target_site_id}/pages/{page_id}"
                update_result = await self.graph_client.patch(update_endpoint, update_payload)
                logger.debug("Webparts update result: %s", update_result)
            except Exception as e:
                # Page created but content failed - log but don't fail
                logger.warning("Page created but content update failed: %s", e)
        
        # Try to publish the page so it's visible
        if page_id:
            logger.debug("Publishing page...")
            try:
                if is_rest_created:
                    await self._publish_page_rest_fallback(page_id, target_site_id)
                    logger.info("Page published via REST fallback.")
                else:
                    publish_endpoint = f"/sites/{target_site_id}/pages/{page_id}/microsoft.graph.sitePage/publish"
                    publish_result = await self.graph_client.post(publish_endpoint, {})
                    logger.debug("Page publish result: %s", publish_result)
                
                # After publishing, get the updated page info if not REST
                if not is_rest_created:
                    get_endpoint = f"/sites/{target_site_id}/pages/{page_id}"
                    updated_data = await self.graph_client.get(get_endpoint)
                    if updated_data and updated_data.get("webUrl"):
                        page_url = updated_data.get("webUrl")
                        logger.debug("Published page URL: %s", page_url)
            except Exception as e:
                logger.warning("Could not publish page: %s", e)
        
        # If webUrl not in response, construct it manually
        if not page_url:
            site_url = await self.rest_client.get_site_url()
            page_url = f"{site_url}/SitePages/{page_name_base}"
            logger.debug("Constructed URL: %s", page_url)
        
        logger.debug("Final page URL: %s", page_url)
        
        return {
            "id": page_id,
            "name": sp_page.title,
            "resource_link": page_url,
            "webUrl": page_url
        }

    async def _create_page_rest_fallback(self, sp_page: SPPage, site_id: str) -> Dict[str, Any]:
        """Fall back to SharePoint REST API for page creation if Graph fails.
        
        Uses OBO flow to maintain user identity.
        """
        # Get the user token from the graph client (if available)
        user_token = self.graph_client._user_token if self.graph_client else None
        if not user_token:
            raise SharePointProvisioningException("User token not available for REST fallback")

        # Get REST headers with OBO token
        headers = await self.graph_client.auth_service.get_rest_headers_obo(user_token, site_id)
        
        # Override to nometadata to avoid OData type errors
        headers["Accept"] = "application/json;odata=nometadata"
        headers["Content-Type"] = "application/json;odata=nometadata"
        
        # Determine site URL
        site_url = await self.rest_client.get_site_url(site_id)
        endpoint = f"{site_url}/_api/sitepages/pages"
        
        # Payload for REST API
        canvas_content_str = CanvasContentBuilder.build(sp_page.webparts)
        payload = {
            "Title": sp_page.title,
            "PageLayoutType": getattr(sp_page, "layout", "Article").capitalize(),
        }
        
        # Include canvas content if we have a valid JSON string from the builder
        if canvas_content_str and canvas_content_str != "[]":
            payload["CanvasContent1"] = canvas_content_str
        
        logger.debug("REST Fallback Payload (keys): %s", list(payload.keys()))
        
        # Use httpx from rest_client
        response = await self.rest_client.http.post(endpoint, headers=headers, json=payload)
        if not response.is_success:
            logger.error("REST Fallback failed with status %s: %s", response.status_code, response.text)
            raise SharePointProvisioningException(
                f"REST fallback failed: {response.status_code}. Response: {response.text}"
            )
            
        data = response.json()
        
        page_id = str(data.get("Id", ""))
        web_url = data.get("AbsoluteUrl", "")
        
        if not page_id or not web_url:
            error_msg = f"[PageService] REST page fallback returned success but empty ID or URL. Response: {response.text}"
            logger.error(error_msg)
            raise SharePointProvisioningException(error_msg)

        # With nometadata, there is no 'd' wrapper
        return {
            "id": page_id,
            "name": sp_page.title,
            "resource_link": web_url,
            "webUrl": web_url
        }

    async def _publish_page_rest_fallback(self, page_id: str, site_id: str) -> None:
        """Publish a page via SharePoint REST API (OBO)."""
        user_token = self.graph_client._user_token if self.graph_client else None
        if not user_token:
            return

        headers = await self.graph_client.auth_service.get_rest_headers_obo(user_token, site_id)
        headers["Accept"] = "application/json;odata=nometadata"
        
        site_url = await self.rest_client.get_site_url(site_id)
        # Endpoint for publishing via REST
        endpoint = f"{site_url}/_api/sitepages/pages({page_id})/publish"
        
        response = await self.rest_client.http.post(endpoint, headers=headers, json={})
        if not response.is_success:
            logger.warning("REST Publish failed: %s. Response: %s", response.status_code, response.text)
    
    def _build_canvas_layout(self, webparts: list) -> Dict[str, Any]:
        """Build canvas layout structure for Graph API v1.0.
        
        Uses CanvasContentBuilder for modern Graph API webpart mapping.
        
        Args:
            webparts: List of WebPart objects
            
        Returns:
            Canvas layout dictionary for Graph API v1.0
        """
        # Use the specialized builder to get the webparts in Graph v1.0 format
        webparts_list = CanvasContentBuilder.build_graph_webparts(webparts)
        
        # Return the horizontalSections structure expected by modern Pages API
        # Note: Do NOT include "id" fields - Graph API will handle those
        return {
            "horizontalSections": [
                {
                    "layout": "oneColumn",
                    "columns": [
                        {
                            "width": 12,
                            "webparts": webparts_list
                        }
                    ]
                }
            ]
        }

    @handle_sharepoint_errors("get page")
    async def get_page_by_id(self, site_id: str, page_id: str) -> Optional[Dict[str, Any]]:
        """Get a page by ID from SharePoint using Graph API v1.0.
        
        Args:
            site_id: SharePoint site ID
            page_id: SharePoint page ID
            
        Returns:
            Page data dictionary or None if failed
        """
        if not self.graph_client:
            raise SharePointProvisioningException(
                "Graph API client not available for page retrieval"
            )
        
        # Use Graph API v1.0 to get page - will raise SharePointAPIError if fails
        endpoint = f"/sites/{site_id}/pages/{page_id}"
        page_data = await self.graph_client.get(endpoint)
        
        return page_data

    @handle_sharepoint_errors("update page")
    async def update_page_content(self, site_id: str, page_id: str, modifications: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update the content/webparts of an existing page using Graph API v1.0.
        
        Args:
            site_id: SharePoint site ID
            page_id: SharePoint page ID
            modifications: Dictionary with fields to update (e.g., title, canvasContent1, etc.)
            
        Returns:
            Updated page data or None if failed
        """
        if not self.graph_client:
            raise SharePointProvisioningException(
                "Graph API client not available for page update"
            )
        
        # Use Graph API v1.0 to update page - will raise SharePointAPIError if fails
        endpoint = f"/sites/{site_id}/pages/{page_id}"
        updated_page = await self.graph_client.patch(endpoint, modifications)
        
        return updated_page

    @handle_sharepoint_errors("delete page")
    async def delete_page(self, site_id: str, page_id: str) -> bool:
        """Delete a page from SharePoint using Graph API v1.0.
        
        Args:
            site_id: SharePoint site ID
            page_id: SharePoint page ID
            
        Returns:
            True if successful, False otherwise
        """
        if not self.graph_client:
            raise SharePointProvisioningException(
                "Graph API client not available for page deletion"
            )
        
        # Use Graph API v1.0 to delete page - will raise SharePointAPIError if fails
        endpoint = f"/sites/{site_id}/pages/{page_id}"
        success = await self.graph_client.delete(endpoint)
        
        return success

    @handle_sharepoint_errors("get all pages")
    async def get_all_pages(self, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all pages from a site."""
        target_site_id = site_id or self.graph_client.site_id
        endpoint = f"/sites/{target_site_id}/pages"
        all_pages: List[Dict[str, Any]] = []
        while endpoint:
            data = await self.graph_client.get(endpoint)
            all_pages.extend(data.get("value", []))
            endpoint = data.get("@odata.nextLink")
        return all_pages

    @handle_sharepoint_errors("search pages")
    async def search_pages(self, query: str, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search pages by title or content."""
        all_pages = await self.get_all_pages(site_id)
        query_lower = query.lower()
        return [
            page for page in all_pages
            if query_lower in page.get("title", "").lower()
            or query_lower in page.get("name", "").lower()
        ]

    @handle_sharepoint_errors("get page by name")
    async def get_page_by_name(self, page_name: str, site_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get a page by its name."""
        target_site_id = site_id or self.graph_client.site_id
        if not page_name.endswith('.aspx'):
            page_name += '.aspx'
        endpoint = f"/sites/{target_site_id}/pages/{page_name}"
        try:
            return await self.graph_client.get(endpoint)
        except Exception as e:
            logger.debug(f"Page {page_name} not found: {e}")
            return None

    @handle_sharepoint_errors("publish page")
    async def publish_page(self, page_id: str, site_id: Optional[str] = None) -> bool:
        """Publish a page."""
        target_site_id = site_id or self.graph_client.site_id
        # Graph v1.0 requires the type-cast segment: microsoft.graph.sitePage/publish
        endpoint = f"/sites/{target_site_id}/pages/{page_id}/microsoft.graph.sitePage/publish"
        await self.graph_client.post(endpoint, {})
        return True

    @handle_sharepoint_errors("unpublish page")
    async def unpublish_page(self, page_id: str, site_id: Optional[str] = None) -> bool:
        """Unpublish a page."""
        target_site_id = site_id or self.graph_client.site_id
        endpoint = f"/sites/{target_site_id}/pages/{page_id}"
        await self.graph_client.patch(endpoint, {"promotionKind": "draft"})
        return True

    @handle_sharepoint_errors("checkout page")
    async def checkout_page(self, page_id: str, site_id: Optional[str] = None) -> bool:
        """Check out a page."""
        target_site_id = site_id or self.graph_client.site_id
        endpoint = f"/sites/{target_site_id}/pages/{page_id}/checkout"
        await self.graph_client.post(endpoint, {})
        return True

    @handle_sharepoint_errors("checkin page")
    async def checkin_page(self, page_id: str, comment: Optional[str] = None, site_id: Optional[str] = None) -> bool:
        """Check in a page."""
        target_site_id = site_id or self.graph_client.site_id
        endpoint = f"/sites/{target_site_id}/pages/{page_id}/checkin"
        payload = {"comment": comment or ""}
        await self.graph_client.post(endpoint, payload)
        return True

    @handle_sharepoint_errors("discard page checkout")
    async def discard_page_checkout(self, page_id: str, site_id: Optional[str] = None) -> bool:
        """Discard page checkout."""
        target_site_id = site_id or self.graph_client.site_id
        endpoint = f"/sites/{target_site_id}/pages/{page_id}/discardCheckout"
        await self.graph_client.post(endpoint, {})
        return True

    @handle_sharepoint_errors("copy page")
    async def copy_page(self, source_page_id: str, new_title: str, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Copy a page."""
        # Get source page first
        source_page = await self.get_page_by_id(site_id or self.graph_client.site_id, source_page_id)
        if not source_page:
            raise SharePointProvisioningException(f"Source page {source_page_id} not found")
        
        # Create new page with same content
        target_site_id = site_id or self.graph_client.site_id
        page_name = URLHelpers.generate_page_name(new_title) + '.aspx'
        
        payload = {
            "name": page_name,
            "title": new_title,
            "pageLayout": source_page.get("pageLayout", "article"),
            "canvasLayout": source_page.get("canvasLayout")
        }
        
        endpoint = f"/sites/{target_site_id}/pages"
        return await self.graph_client.post(endpoint, payload)

    @handle_sharepoint_errors("get page versions")
    async def get_page_versions(self, page_id: str, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get page versions."""
        target_site_id = site_id or self.graph_client.site_id
        endpoint = f"/sites/{target_site_id}/pages/{page_id}/versions"
        data = await self.graph_client.get(endpoint)
        return data.get("value", [])

    @handle_sharepoint_errors("restore page version")
    async def restore_page_version(self, page_id: str, version_id: str, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Restore a page version."""
        target_site_id = site_id or self.graph_client.site_id
        endpoint = f"/sites/{target_site_id}/pages/{page_id}/versions/{version_id}/restoreVersion"
        return await self.graph_client.post(endpoint, {})

    @handle_sharepoint_errors("promote page as news")
    async def promote_page_as_news(self, page_id: str, site_id: Optional[str] = None) -> bool:
        """Promote page as news."""
        target_site_id = site_id or self.graph_client.site_id
        endpoint = f"/sites/{target_site_id}/pages/{page_id}"
        await self.graph_client.patch(endpoint, {"promotionKind": "newsPost"})
        return True

    @handle_sharepoint_errors("create page share link")
    async def create_page_share_link(self, page_id: str, link_type: str = "view", site_id: Optional[str] = None) -> Dict[str, Any]:
        """Create sharing link for page."""
        target_site_id = site_id or self.graph_client.site_id
        # Get page info to get its web URL
        page = await self.get_page_by_id(target_site_id, page_id)
        if page and page.get("webUrl"):
            return {"link": page["webUrl"], "type": link_type}
        return {}

    async def get_page_analytics(self, page_id: str, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Get view analytics for a page via Graph /analytics endpoint."""
        target_site_id = site_id or self.graph_client.site_id
        try:
            data = await self.graph_client.get(
                f"/sites/{target_site_id}/pages/{page_id}/analytics"
            )
            return data
        except Exception:
            # analytics endpoint may not be available for all tenants; return empty dict
            return {}

    async def schedule_page_publish(
        self,
        page_id: str,
        scheduled_datetime: str,
        site_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Schedule a page to be published at a future datetime (ISO 8601 string)."""
        target_site_id = site_id or self.graph_client.site_id
        payload = {"scheduledDateTime": scheduled_datetime, "scheduledPublishingEnabled": True}
        try:
            return await self.graph_client.patch(
                f"/sites/{target_site_id}/pages/{page_id}",
                payload,
            )
        except Exception as exc:
            return {"error": str(exc)}
