"""Service for SharePoint site operations."""

import logging
import json
from typing import Dict, Any, Optional, List
from src.domain.entities.core import SPSite
from src.domain.exceptions import SharePointProvisioningException
from src.infrastructure.services.graph_api_client import GraphAPIClient
from src.infrastructure.services.rest_api_client import RESTAPIClient

logger = logging.getLogger(__name__)


class SiteService:
    """Service for managing SharePoint Sites."""

    def __init__(self, graph_client: GraphAPIClient, rest_client: RESTAPIClient = None):
        self.graph_client = graph_client
        self.rest_client = rest_client

    async def create_site(self, sp_site: SPSite) -> Dict[str, Any]:
        """Create a new SharePoint site.
        
        Uses the beta /sites endpoint.
        """
        # Determine a safe URL name if none provided
        safe_name = sp_site.name
        if not safe_name:
            # simple slugification
            safe_name = sp_site.title.lower().replace(" ", "-")
            import re
            safe_name = re.sub(r'[^a-z0-9\-]', '', safe_name)


        
        # Map templates to teamSite or communicationSite as recommended by actual Graph API behavior
        template_map = {
            "sts": "teamSite",
            "teamsite": "teamSite",
            "team": "teamSite",
            "group": "teamSite",
            "sitepagepublishing": "communicationSite",
            "communicationsite": "communicationSite",
            "sitepage": "communicationSite",
        }
        site_template = template_map.get(sp_site.template.lower(), "teamSite")

        # Get hostname for siteCollection
        from src.infrastructure.config import settings
        from urllib.parse import urlparse
        hostname = ""
        site_url_raw = getattr(settings, "SHAREPOINT_SITE_URL", "")
        if site_url_raw:
            hostname = urlparse(site_url_raw).netloc
        if not hostname:
            tenants = getattr(settings, "ALLOWED_SHAREPOINT_TENANTS", "").split(",")
            if tenants and tenants[0]:
                hostname = f"{tenants[0].strip()}.sharepoint.com"
                
        safe_name = sp_site.name
        if not safe_name:
            import re
            safe_name = sp_site.title.lower().replace(" ", "")
            safe_name = re.sub(r'[^a-z0-9]', '', safe_name)
                
        payload = {
            "displayName": sp_site.title,
            "description": sp_site.description or f"Site created by SharePoint AI Agent: {sp_site.title}",
            "name": safe_name,
            "template": site_template,
        }
        
        if hostname:
            payload["siteCollection"] = {
                "hostname": hostname
            }

        # Log actual payload being sent to Graph
        logger.info("[SiteService] Request Body sent to Graph POST /beta/sites: %s", json.dumps(payload))

        creation_method = "graph"
        fallback_reason = None
        
        try:
            # We enforce Graph API exclusively as recommended.
            response = await self.graph_client.post_beta("/sites", payload)
            logger.info("SUCCESS with Graph API for site '%s'", sp_site.title)
        except Exception as e:
            logger.error("Graph API site creation failed for '%s'. Error: %s", sp_site.title, str(e))
            if hasattr(e, 'response') and e.response:
                logger.error("[SiteService] Graph Error Status: %s, Body: %s", e.response.status_code, e.response.text)
            
            # Re-raise instead of falling back to REST to prevent inconsistent states
            raise SharePointProvisioningException(
                f"Failed to create site '{sp_site.title}' via Graph API. "
                f"Graph Error: {str(e)}"
            ) from e

        # Log structured creation info
        logger.info(
            "Site creation details: title='%s', method='%s', fallback_reason='%s'",
            sp_site.title, creation_method, fallback_reason or "N/A"
        )

        # The API returns 202 Accepted usually with a Location header, 
        # but the GraphAPIClient currently just returns response.json().
        # For our purposes, returning the response JSON provides the status details.
        response["resource_link"] = response.get("webUrl", "")

        # If the API returned 202 Accepted, poll until provisioning completes
        if response.get("_provisioning"):
            poll_url = response.get("_poll_url", "")
            site_title = sp_site.title
            poll_data = await self._poll_site_provisioning(poll_url, site_title)
            if poll_data:
                response.update(poll_data)
                
            # If polling didn't give us the ID or webUrl, search for the site by title
            if not response.get("id") and not response.get("webUrl"):
                logger.info("Polling finished but no ID/webUrl returned. Searching for site by title: %s", site_title)
                import asyncio
                await asyncio.sleep(5)  # Allow time for index
                search_results = await self.search_sites(site_title)
                if search_results:
                    site_match = search_results[0]
                    response["id"] = site_match.get("id")
                    response["webUrl"] = site_match.get("webUrl")
                    response["resource_link"] = site_match.get("webUrl", "")
            
        # If ID is missing but webUrl is present, try to resolve ID with retries
        if not response.get("id") and response.get("webUrl"):
            logger.debug("Attempting to resolve site ID from webUrl: %s", response.get("webUrl"))
            max_resolve_attempts = 5
            for attempt in range(max_resolve_attempts):
                try:
                    resolved = await self.get_site_by_url(response["webUrl"])
                    if resolved and resolved.get("id"):
                        response["id"] = resolved["id"]
                        logger.info("Resolved site ID '%s' from webUrl (attempt %d).", response["id"], attempt + 1)
                        break
                    else:
                        logger.debug("Site lookup returned no ID (attempt %d). Response keys: %s", attempt + 1, list(resolved.keys()) if resolved else "None")
                except Exception as resolve_err:
                    logger.debug("Could not resolve site ID from webUrl (attempt %d): %s", attempt + 1, resolve_err)
                    if attempt < max_resolve_attempts - 1:
                        import asyncio
                        await asyncio.sleep(1)  # Brief delay before retry

        # Wait for site to be fully ready before returning
        if response.get("id"):
            await self.wait_until_ready(response["id"])
        elif response.get("webUrl"):
            logger.warning("Site created but ID could not be resolved. Using webUrl as site reference: %s", response.get("webUrl"))

        return response

    async def wait_until_ready(self, site_id: str, max_attempts: int = 10, delay: int = 5) -> bool:
        """Poll the site until it's ready for content (e.g., lists can be fetched)."""
        import asyncio
        logger.info("Waiting for site '%s' to be ready for content...", site_id)
        
        # We try to fetch the default 'Documents' library as a readiness check
        # Actually, any call to /sites/{site_id}/lists that succeeds is good.
        for attempt in range(max_attempts):
            try:
                # Try a lightweight call
                await self.graph_client.get(f"/sites/{site_id}/lists")
                logger.info("Site '%s' is ready after %d attempts.", site_id, attempt + 1)
                return True
            except Exception as e:
                logger.debug("Site '%s' not ready yet (attempt %d): %s", site_id, attempt + 1, e)
                await asyncio.sleep(delay)
        
        logger.warning("Site '%s' did not become ready in time, proceeding anyway.", site_id)
        return False

    async def _poll_site_provisioning(self, poll_url: str, site_title: str, max_attempts: int = 20) -> Dict[str, Any]:
        """Background task: poll until the async site creation resolves."""
        import asyncio
        from src.infrastructure.logging import get_logger
        _poll_logger = get_logger(__name__)
        if not poll_url:
            return {}
        for attempt in range(max_attempts):
            await asyncio.sleep(15)
            try:
                data = await self.graph_client.get(poll_url)
                status = data.get("status", "").lower()
                _poll_logger.info(f"[poll] site '{site_title}' status={status} (attempt {attempt + 1})")
                if status in ("succeeded", "failed", ""):
                    return data
            except Exception as exc:
                _poll_logger.warning(f"[poll] site '{site_title}' poll error: {exc}")
                break
        return {}

    async def get_site(self, site_id: str) -> Dict[str, Any]:
        """Get a site by ID."""
        endpoint = f"/sites/{site_id}"
        return await self.graph_client.get(endpoint)

    async def get_site_by_url(self, site_url: str) -> Dict[str, Any]:
        """Get a site by URL."""
        from urllib.parse import urlparse
        parsed = urlparse(site_url)
        hostname = parsed.netloc
        path = parsed.path.lstrip("/")
        endpoint = f"/sites/{hostname}:/{path}"
        return await self.graph_client.get(endpoint)

    async def get_all_sites(self) -> List[Dict[str, Any]]:
        """Get all sites user has access to."""
        endpoint = "/sites?search=*&$select=id,name,displayName,webUrl,description,siteCollection"
        data = await self.graph_client.get(endpoint)
        return data.get("value", [])

    async def search_sites(self, query: str) -> List[Dict[str, Any]]:
        """Search sites by name or description."""
        endpoint = f"/sites?search={query}"
        data = await self.graph_client.get(endpoint)
        return data.get("value", [])

    async def update_site(self, site_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update site properties."""
        endpoint = f"/sites/{site_id}"
        return await self.graph_client.patch(endpoint, updates)

    async def delete_site(self, site_id: str) -> bool:
        """Delete a site."""
        endpoint = f"/sites/{site_id}"
        return await self.graph_client.delete(endpoint)

    async def get_site_owners(self, site_id: str) -> List[Dict[str, Any]]:
        """Get site owners."""
        endpoint = f"/sites/{site_id}/owners"
        try:
            data = await self.graph_client.get(endpoint)
            return data.get("value", [])
        except Exception as e:
            # Fallback: get from site groups
            logger.warning(f"Failed to get site owners directly, using fallback: {e}")
            groups_endpoint = f"/sites/{site_id}/groups"
            groups_data = await self.graph_client.get(groups_endpoint)
            owners = [g for g in groups_data.get("value", []) if "owner" in g.get("displayName", "").lower()]
            return owners

    async def get_site_members(self, site_id: str) -> List[Dict[str, Any]]:
        """Get site members."""
        endpoint = f"/sites/{site_id}/members"
        try:
            data = await self.graph_client.get(endpoint)
            return data.get("value", [])
        except Exception as e:
            # Fallback
            logger.warning(f"Failed to get site members directly, using fallback: {e}")
            groups_endpoint = f"/sites/{site_id}/groups"
            groups_data = await self.graph_client.get(groups_endpoint)
            members = [g for g in groups_data.get("value", []) if "member" in g.get("displayName", "").lower()]
            return members

    async def add_site_owner(self, site_id: str, user_email: str) -> bool:
        """Add a site owner."""
        # Get user ID first
        user_endpoint = f"/users/{user_email}"
        user = await self.graph_client.get(user_endpoint)
        user_id = user.get("id")
        
        # Add to owners group
        endpoint = f"/sites/{site_id}/owners/$ref"
        payload = {"@odata.id": f"https://graph.microsoft.com/v1.0/users/{user_id}"}
        await self.graph_client.post(endpoint, payload)
        return True

    async def add_site_member(self, site_id: str, user_email: str) -> bool:
        """Add a site member."""
        user_endpoint = f"/users/{user_email}"
        user = await self.graph_client.get(user_endpoint)
        user_id = user.get("id")
        
        endpoint = f"/sites/{site_id}/members/$ref"
        payload = {"@odata.id": f"https://graph.microsoft.com/v1.0/users/{user_id}"}
        await self.graph_client.post(endpoint, payload)
        return True

    async def remove_site_user(self, site_id: str, user_id: str) -> bool:
        """Remove user from site."""
        # Try removing from members first
        try:
            endpoint = f"/sites/{site_id}/members/{user_id}/$ref"
            await self.graph_client.delete(endpoint)
            return True
        except Exception as e:
            # Try removing from owners
            logger.debug(f"User not in members, trying owners: {e}")
            endpoint = f"/sites/{site_id}/owners/{user_id}/$ref"
            return await self.graph_client.delete(endpoint)

    async def get_site_permissions(self, site_id: str) -> Dict[str, Any]:
        """Get site permissions."""
        endpoint = f"/sites/{site_id}/permissions"
        data = await self.graph_client.get(endpoint)
        return {"permissions": data.get("value", [])}

    async def update_site_theme(self, site_id: str, theme_settings: Dict[str, Any]) -> bool:
        """Update site theme/logo."""
        endpoint = f"/sites/{site_id}"
        await self.graph_client.patch(endpoint, theme_settings)
        return True


    async def get_site_navigation(self, site_id: str, nav_type: str = "top") -> List[Dict[str, Any]]:
        """Get site navigation (top or quick launch) using SharePoint REST API."""
        if not self.rest_client:
            logger.warning("get_site_navigation: rest_client not available, returning empty list")
            return []
        try:
            nav_path = "TopNavigationBar" if nav_type == "top" else "QuickLaunch"
            site_url = await self.rest_client.get_site_url()
            url = f"{site_url}/_api/web/Navigation/{nav_path}"
            headers = await self.rest_client.auth_service.get_rest_headers(self.rest_client.site_id)
            response = await self.rest_client.http.get(url, headers=headers)
            response.raise_for_status()
            return response.json().get('d', {}).get('results', [])
        except Exception as e:
            logger.error("Error fetching site navigation: %s", e)
            return []

    async def update_site_navigation(self, site_id: str, nav_type: str, nav_items: List[Dict[str, Any]]) -> bool:
        """Update site navigation (top or quick launch) using SharePoint REST API."""
        if not self.rest_client:
            logger.warning("update_site_navigation: rest_client not available")
            return False
        try:
            nav_path = "TopNavigationBar" if nav_type == "top" else "QuickLaunch"
            site_url = await self.rest_client.get_site_url()
            url = f"{site_url}/_api/web/Navigation/{nav_path}"
            headers = await self.rest_client.auth_service.get_rest_headers(self.rest_client.site_id)
            # Fetch and delete all existing nodes
            response = await self.rest_client.http.get(url, headers=headers)
            existing = response.json().get('d', {}).get('results', [])
            for node in existing:
                del_url = f"{url}({node['Id']})"
                await self.rest_client.http.delete(del_url, headers=headers)
            # Add new nodes
            for item in nav_items:
                payload = {
                    '__metadata': {'type': 'SP.NavigationNode'},
                    'Title': item['Title'],
                    'Url': item['Url'],
                    'IsExternal': item.get('IsExternal', True)
                }
                post_headers = {**headers, 'Content-Type': 'application/json;odata=verbose'}
                await self.rest_client.http.post(url, headers=post_headers, json=payload)
            return True
        except Exception as e:
            logger.error("Error updating site navigation: %s", e)
            return False

    async def get_site_storage_info(self, site_id: str) -> Dict[str, Any]:
        """Get site storage info."""
        site = await self.get_site(site_id)
        quota = site.get("quota", {})
        return {
            "used": quota.get("used", 0),
            "remaining": quota.get("remaining", 0),
            "total": quota.get("total", 0),
            "state": quota.get("state", "normal")
        }

    async def get_site_analytics(self, site_id: str, period: str = "last7days") -> Dict[str, Any]:
        """Get site analytics."""
        endpoint = f"/sites/{site_id}/analytics/{period}"
        try:
            data = await self.graph_client.get(endpoint)
            return data
        except Exception as e:
            logger.warning(f"Failed to get site analytics: {e}")
            return {"period": period, "views": 0, "visitors": 0}

    async def get_site_recycle_bin(self, site_id: str) -> List[Dict[str, Any]]:
        """Get recycle bin items."""
        endpoint = f"/sites/{site_id}/recycleBin/items"
        try:
            data = await self.graph_client.get(endpoint)
            return data.get("value", [])
        except Exception as e:
            logger.warning(f"Failed to get recycle bin items: {e}")
            return []

    async def restore_from_recycle_bin(self, site_id: str, item_id: str) -> bool:
        """Restore item from recycle bin."""
        endpoint = f"/sites/{site_id}/recycleBin/items/{item_id}/restore"
        await self.graph_client.post(endpoint, {})
        return True

    async def empty_recycle_bin(self, site_id: str) -> bool:
        """Empty recycle bin."""
        # Get all items first
        items = await self.get_site_recycle_bin(site_id)
        for item in items:
            item_id = item.get("id")
            if item_id:
                endpoint = f"/sites/{site_id}/recycleBin/items/{item_id}"
                try:
                    await self.graph_client.delete(endpoint)
                except Exception as e:
                    logger.warning(f"Failed to delete recycle bin item {item_id}: {e}")
        return True

    async def _create_site_rest_fallback(self, sp_site: SPSite) -> Dict[str, Any]:
        """Fall back to SharePoint REST API for site creation if Graph fails.
        
        Uses OBO flow to maintain user identity.
        """
        user_token = self.graph_client._user_token if self.graph_client else None
        if not user_token:
            raise SharePointProvisioningException("User token not available for REST fallback")

        # Determine if it's a team site or communication site
        is_comm_site = sp_site.template in ["communicationSite", "sitepagepublishing"]
        
        from src.infrastructure.config import settings
        auth_service = self.graph_client.auth_service
        # For site creation, we use the root site or tenant URL for the REST endpoint
        # site_id here can be empty as we're creating a new one
        headers = await auth_service.get_rest_headers_obo(user_token, "")
        headers["Accept"] = "application/json;odata=nometadata"
        headers["Content-Type"] = "application/json;odata=nometadata"
        
        site_url_raw = getattr(settings, "SHAREPOINT_SITE_URL", "")
        if not site_url_raw:
            # Fallback to tenant name if URL not set
            tenants = getattr(settings, "ALLOWED_SHAREPOINT_TENANTS", "").split(",")
            if tenants and tenants[0]:
                site_url_base = f"https://{tenants[0].strip()}.sharepoint.com"
            else:
                raise SharePointProvisioningException("SHAREPOINT_SITE_URL is not set and tenant domain cannot be determined.")
        else:
            site_url_base = site_url_raw.split("/sites/")[0]
        
        import httpx
        async with httpx.AsyncClient(timeout=60.0) as client:
            if is_comm_site:
                # Communication site creation via REST
                endpoint = f"{site_url_base}/_api/SPSiteManager/create"
                payload = {
                    "request": {
                        "Title": sp_site.title,
                        "Url": f"{site_url_base}/sites/{sp_site.name or sp_site.title.replace(' ', '')}",
                        "Lcid": 1033,
                        "ShareByEmailEnabled": False,
                        "WebTemplate": "SITEPAGEPUBLISHING#0",
                        "Description": sp_site.description
                    }
                }
                response = await client.post(endpoint, headers=headers, json=payload)
            else:
                # Team site creation via REST (Group-connected)
                endpoint = f"{site_url_base}/_api/GroupSiteManager/CreateGroupEx"
                payload = {
                    "displayName": sp_site.title,
                    "alias": sp_site.name or sp_site.title.replace(' ', ''),
                    "isPublic": False,
                    "optionalParams": {
                        "Description": sp_site.description,
                        "CreationOptions": ["Exchange", "SharePoint"]
                    }
                }
                response = await client.post(endpoint, headers=headers, json=payload)

            # Verbose logging of the REST fallback response
            logger.info("[SiteService] REST Site Fallback Status: %s", response.status_code)
            logger.debug("[SiteService] REST Site Fallback Headers: %s", response.headers)
            logger.info("[SiteService] REST Site Fallback Response Body: %s", response.text)

            if not response.is_success:
                logger.error("[SiteService] REST Site Fallback HTTP Error: %s", response.status_code)
                raise SharePointProvisioningException(f"REST site fallback failed: {response.text}")
            
            try:
                data = response.json()
            except Exception as json_err:
                logger.error("[SiteService] Failed to parse REST fallback response as JSON: %s", json_err)
                raise SharePointProvisioningException(f"Invalid JSON in REST fallback response: {response.text}")
            
            # SharePoint REST API often wraps results in a 'd' property
            d_data = data.get("d", data)
            
            # SPSiteManager.create returns { d: { Create: { SiteUrl: "..." } } }
            # GroupSiteManager.CreateGroupEx returns { d: { CreateGroupEx: "..." } } (sometimes just a string)
            
            site_url = ""
            site_id_guid = None
            if isinstance(d_data, dict):
                # Try common keys
                site_url = (
                    d_data.get("SiteUrl") or 
                    d_data.get("SiteFullUrl") or 
                    d_data.get("Create", {}).get("SiteUrl")
                )
                if not site_url and "CreateGroupEx" in d_data:
                    cge = d_data["CreateGroupEx"]
                    if isinstance(cge, dict):
                        site_url = cge.get("SiteUrl", "")
                        if not site_id_guid:
                            site_id_guid = cge.get("SiteId")
                    elif isinstance(cge, str):
                        try:
                            import json
                            cge_dict = json.loads(cge)
                            site_url = cge_dict.get("SiteUrl", "")
                            if not site_id_guid:
                                site_id_guid = cge_dict.get("SiteId")
                        except Exception:
                            site_url = cge
                
                # If we have a SiteId (GUID), we can return it as resource_id
                if not site_id_guid:
                    site_id_guid = d_data.get("SiteId")
            elif isinstance(d_data, str):
                site_url = d_data

            if not site_url:
                error_msg = f"[SiteService] REST site fallback returned success status but empty SiteUrl. Response: {response.text}"
                logger.error(error_msg)
                raise SharePointProvisioningException(error_msg)
            
            if not site_id_guid:
                logger.warning("[SiteService] REST site fallback returned empty SiteId. Subsequent operations might fail if they require a GUID.")
            return {
                "id": site_id_guid or "", # Return GUID if available
                "resource_id": site_id_guid or "",
                "displayName": sp_site.title,
                "webUrl": site_url,
                "resource_link": site_url
            }
