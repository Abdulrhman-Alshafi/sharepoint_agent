"""Service for SharePoint Enterprise Architecture features."""

from typing import Dict, Any
from src.domain.entities import TermSet, ContentType, SPView
from src.domain.exceptions import SharePointProvisioningException
from src.infrastructure.services.graph_api_client import GraphAPIClient
from src.infrastructure.services.rest_api_client import RESTAPIClient
from src.infrastructure.repositories.utils.constants import SharePointConstants
from src.infrastructure.repositories.utils.error_handlers import handle_sharepoint_errors
from src.infrastructure.repositories.utils.payload_builders import PayloadBuilders


class EnterpriseService:
    """Handles SharePoint Enterprise features: Content Types, Term Sets, Views."""

    def __init__(self, graph_client: GraphAPIClient, rest_client: RESTAPIClient):
        """Initialize enterprise service.
        
        Args:
            graph_client: Graph API client for content types and term sets
            rest_client: REST API client for views
        """
        self.graph_client = graph_client
        self.rest_client = rest_client

    @handle_sharepoint_errors("create content type")
    async def create_content_type(self, content_type: ContentType) -> Dict[str, Any]:
        """Create a SharePoint Content Type via Graph API.
        
        Args:
            content_type: ContentType entity to create
            
        Returns:
            Created content type data
        """
        endpoint = f"/sites/{self.graph_client.site_id}/contentTypes"
        payload = PayloadBuilders.build_content_type_payload(content_type)
        data = await self.graph_client.post(endpoint, payload)
        data["content_type_id"] = data.get("id", "")
        return data

    @handle_sharepoint_errors("create term set")
    async def create_term_set(self, term_set: TermSet) -> Dict[str, Any]:
        """Create a Managed Metadata Term Set via Taxonomy API.
        
        Args:
            term_set: TermSet entity to create
            
        Returns:
            Created term set data
        """
        # Use Graph API v1.0 TermStore API
        payload = PayloadBuilders.build_term_set_payload(term_set)

        data = await self.graph_client.post(
            f"/sites/{self.graph_client.site_id}/termStore/sets",
            payload,
        )

        set_id = data.get("id", "")

        # Now add terms
        for term in term_set.terms:
            term_payload = PayloadBuilders.build_term_payload(term)
            await self.graph_client.post(
                f"/sites/{self.graph_client.site_id}/termStore/sets/{set_id}/children",
                term_payload,
            )
        
        data["term_set_id"] = set_id
        return data

    @handle_sharepoint_errors("create view")
    async def create_view(self, view: SPView) -> Dict[str, Any]:
        """Create a List View via REST API.
        
        Args:
            view: SPView entity to create
            
        Returns:
            Created view data
        """
        endpoint = f"/_api/web/lists/getByTitle('{view.target_list_title}')/views"
        payload = PayloadBuilders.build_view_payload(view)
        data = await self.rest_client.post(endpoint, payload)
        result = data.get("d", data)
        result["view_id"] = result.get("Id", "")
        return result

    # ── CONTENT TYPES ───────────────────────────────────────────────────────

    @handle_sharepoint_errors("get content types")
    async def get_content_types(self, site_id: str = None) -> list:
        """List all content types for the site."""
        target = site_id or self.graph_client.site_id
        data = await self.graph_client.get(f"/sites/{target}/contentTypes")
        return data.get("value", [])

    @handle_sharepoint_errors("get content type")
    async def get_content_type(self, content_type_id: str, site_id: str = None) -> Dict[str, Any]:
        """Get a specific content type by ID."""
        target = site_id or self.graph_client.site_id
        return await self.graph_client.get(f"/sites/{target}/contentTypes/{content_type_id}")

    @handle_sharepoint_errors("update content type")
    async def update_content_type(
        self, content_type_id: str, updates: Dict[str, Any], site_id: str = None
    ) -> Dict[str, Any]:
        """Update content type properties."""
        target = site_id or self.graph_client.site_id
        return await self.graph_client.patch(
            f"/sites/{target}/contentTypes/{content_type_id}", updates
        )

    @handle_sharepoint_errors("delete content type")
    async def delete_content_type(self, content_type_id: str, site_id: str = None) -> bool:
        """Delete a content type."""
        target = site_id or self.graph_client.site_id
        await self.graph_client.delete(f"/sites/{target}/contentTypes/{content_type_id}")
        return True

    # ── TERM SETS ────────────────────────────────────────────────────────────

    @handle_sharepoint_errors("get term sets")
    async def get_term_sets(self, site_id: str = None) -> list:
        """List all term sets in the site term store."""
        target = site_id or self.graph_client.site_id
        data = await self.graph_client.get(f"/sites/{target}/termStore/sets")
        return data.get("value", [])

    @handle_sharepoint_errors("get term set")
    async def get_term_set(self, term_set_id: str, site_id: str = None) -> Dict[str, Any]:
        """Get a specific term set by ID."""
        target = site_id or self.graph_client.site_id
        return await self.graph_client.get(f"/sites/{target}/termStore/sets/{term_set_id}")

    @handle_sharepoint_errors("add term to set")
    async def add_term_to_set(
        self, term_set_id: str, term_label: str, parent_term_id: str = None, site_id: str = None
    ) -> Dict[str, Any]:
        """Add a term to an existing term set."""
        target = site_id or self.graph_client.site_id
        if parent_term_id:
            endpoint = f"/sites/{target}/termStore/sets/{term_set_id}/terms/{parent_term_id}/children"
        else:
            endpoint = f"/sites/{target}/termStore/sets/{term_set_id}/children"
        payload = PayloadBuilders.build_term_payload(term_label)
        return await self.graph_client.post(endpoint, payload)

    @handle_sharepoint_errors("delete term set")
    async def delete_term_set(self, term_set_id: str, site_id: str = None) -> bool:
        """Delete a term set."""
        target = site_id or self.graph_client.site_id
        await self.graph_client.delete(f"/sites/{target}/termStore/sets/{term_set_id}")
        return True

    # ── VIEWS (UPDATE) ───────────────────────────────────────────────────────

    @handle_sharepoint_errors("update view")
    async def update_view(
        self, list_id: str, view_id: str, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update view properties using REST MERGE."""
        site_url = await self.rest_client.get_site_url()
        url = f"{site_url}/_api/web/lists(guid'{list_id}')/views('{view_id}')"
        headers = await self.rest_client.auth_service.get_rest_headers(self.rest_client.site_id)
        merge_headers = {**headers, "X-HTTP-Method": "MERGE", "IF-MATCH": "*"}
        payload = {"__metadata": {"type": "SP.View"}, **updates}
        response = await self.rest_client.http.post(url, headers=merge_headers, json=payload)
        if not response.is_success and response.status_code not in (200, 204):
            raise SharePointProvisioningException(
                f"update_view failed: {response.status_code} {response.text}"
            )
        return {"list_id": list_id, "view_id": view_id, **updates}
