import logging
from typing import Dict, Any, List
from src.domain.entities import DocumentLibrary
from src.domain.exceptions import SharePointProvisioningException
from src.infrastructure.services.graph_api_client import GraphAPIClient
from src.infrastructure.repositories.utils.payload_builders import PayloadBuilders
from src.infrastructure.repositories.utils.constants import SharePointConstants
from src.infrastructure.repositories.utils.error_handlers import handle_sharepoint_errors

logger = logging.getLogger(__name__)

class LibraryService:
    """Handles all Document Library operations."""

    def __init__(self, graph_client: GraphAPIClient):
        """Initialize library service.
        
        Args:
            graph_client: Graph API client for making requests
        """
        self.graph_client = graph_client

    @handle_sharepoint_errors("create document library")
    async def create_document_library(self, library: DocumentLibrary, site_id: str = None) -> Dict[str, Any]:
        """Create a document library in SharePoint via Graph API.
        
        Args:
            library: DocumentLibrary entity to create
            site_id: Optional site ID override.
            
        Returns:
            Created library data including resource_link
        """
        payload = PayloadBuilders.build_library_payload(library)
        target_site = site_id or self.graph_client.site_id
        endpoint = f"/sites/{target_site}/lists"
        
        original_title = library.title
        attempt = 0
        
        while True:
            try:
                data = await self.graph_client.post(endpoint, payload)
                logger.info("SUCCESS with Graph API for library '%s'", library.title)
                break
            except Exception as e:
                err_msg = str(e).lower()
                if "status 409" in err_msg or "namealreadyexists" in err_msg or "already exists" in err_msg:
                    attempt += 1
                    new_title = f"{original_title} ({attempt})"
                    logger.info(f"Library '{library.title}' already exists. Retrying with name '{new_title}'.")
                    library.title = new_title
                    payload["displayName"] = new_title
                    continue
                    
                logger.warning("Graph API library creation failed for '%s'. Error: %s", library.title, str(e))
                
                logger.info("Attempting fallback to SharePoint REST API (via OBO)...")
                try:
                    data = await self._create_library_rest_fallback(library, target_site)
                    logger.info("SUCCESS with REST API fallback for library '%s'", library.title)
                    break
                except Exception as e_rest:
                    rest_err_msg = str(e_rest).lower()
                    if "status 409" in rest_err_msg or "namealreadyexists" in rest_err_msg or "already exists" in rest_err_msg or "already in use" in rest_err_msg or "status_code: 409" in rest_err_msg:
                        attempt += 1
                        new_title = f"{original_title} ({attempt})"
                        logger.info(f"Library '{library.title}' already exists (REST fallback). Retrying with name '{new_title}'.")
                        library.title = new_title
                        payload["displayName"] = new_title
                        continue

                    logger.error("FINAL FAILURE: REST API fallback for library also failed: %s", e_rest)
                    raise SharePointProvisioningException(
                        f"Failed to create library '{library.title}' via Graph API and REST API. "
                        f"Graph Error: {str(e)}. REST Error: {str(e_rest)}"
                    ) from e_rest
        data["resource_link"] = data.get("webUrl", "")
        return data

    @handle_sharepoint_errors("get all document libraries")
    async def get_all_document_libraries(self, site_id: str = None) -> List[Dict[str, Any]]:
        """Get all document libraries on the SharePoint site.

        Args:
            site_id: Optional site ID. If None, uses the client's default site.

        Returns:
            List of all document libraries
        """
        target_site = site_id or self.graph_client.site_id
        endpoint = f"/sites/{target_site}/lists"
        data = await self.graph_client.get(endpoint)
        all_lists = data.get("value", [])
        
        # Filter for document libraries (template = documentLibrary or 1)
        return [
            lst for lst in all_lists
            if (lst.get("list", {}) or {}).get("template") == SharePointConstants.DOCUMENT_LIBRARY_TEMPLATE
            or (lst.get("list", {}) or {}).get("template") == SharePointConstants.DOCUMENT_LIBRARY_TEMPLATE_ID
        ]

    @handle_sharepoint_errors("get document library")
    async def get_document_library(self, library_id: str) -> Dict[str, Any]:
        """Get a specific document library by ID.
        
        Args:
            library_id: Library ID
            
        Returns:
            Library data
        """
        endpoint = f"/sites/{self.graph_client.site_id}/lists/{library_id}"
        data = await self.graph_client.get(endpoint)
        return data

    @handle_sharepoint_errors("update document library")
    async def update_library_metadata(
        self, library_id: str, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update document library metadata.
        
        Args:
            library_id: Library ID
            metadata: Metadata to update (description, settings, etc.)
            
        Returns:
            Updated library data
        """
        endpoint = f"/sites/{self.graph_client.site_id}/lists/{library_id}"
        
        # Build payload for metadata update
        payload = {}
        if "name" in metadata or "title" in metadata:
            payload["displayName"] = metadata.get("name") or metadata.get("title")
        if "description" in metadata:
            payload["description"] = metadata["description"]
        
        # Remove None values
        payload = {k: v for k, v in payload.items() if v is not None}
        
        data = await self.graph_client.patch(endpoint, payload)
        return data

    @handle_sharepoint_errors("delete document library")
    async def delete_document_library(self, library_id: str, site_id: str = None) -> bool:
        """Delete a document library from SharePoint.
        
        Args:
            library_id: Library ID
            site_id: Optional site ID override.
            
        Returns:
            True if deletion was successful
        """
        target_site = site_id or self.graph_client.site_id
        endpoint = f"/sites/{target_site}/lists/{library_id}"
        return await self.graph_client.delete(endpoint)

    @handle_sharepoint_errors("search libraries")
    async def search_libraries(self, query: str, site_id: str = None) -> List[Dict[str, Any]]:
        """Search for document libraries by display name.

        Args:
            query: Search query string
            site_id: Optional site ID.

        Returns:
            List of matching libraries
        """
        all_libraries = await self.get_all_document_libraries(site_id=site_id)
        query_lower = query.lower()
        
        return [
            lib for lib in all_libraries
            if query_lower in lib.get("displayName", "").lower()
            or query_lower in lib.get("description", "").lower()
        ]

    @handle_sharepoint_errors("add library column")
    async def add_library_column(
        self, library_id: str, column_name: str, column_type: str, required: bool = False
    ) -> Dict[str, Any]:
        """Add a column to a document library.
        
        Args:
            library_id: Library ID
            column_name: Column name
            column_type: Column type
            required: Is required
            
        Returns:
            Created column metadata
        """
        endpoint = f"/sites/{self.graph_client.site_id}/lists/{library_id}/columns"
        
        # Map column types to SharePoint types
        type_mapping = {
            "text": {"text": {}},
            "number": {"number": {}},
            "boolean": {"boolean": {}},
            "dateTime": {"dateTime": {}},
            "choice": {"choice": {"choices": []}},
            "lookup": {"lookup": {}},
            "person": {"personOrGroup": {}},
            "url": {"hyperlinkOrPicture": {}},
        }
        
        payload = {
            "name": column_name,
            "displayName": column_name,
            "required": required,
            **type_mapping.get(column_type, {"text": {}})
        }
        
        data = await self.graph_client.post(endpoint, payload)
        return data

    @handle_sharepoint_errors("get library schema")
    async def get_library_schema(self, library_id: str, site_id: str = None) -> Dict[str, Any]:
        """Get library schema including columns.

        Args:
            library_id: Library ID
            site_id: Optional site ID. If None, uses the client's default site.

        Returns:
            Library schema
        """
        target_site = site_id or self.graph_client.site_id
        # Get library info
        library_endpoint = f"/sites/{target_site}/lists/{library_id}"
        library_data = await self.graph_client.get(library_endpoint)
        
        # Get columns
        columns_endpoint = f"/sites/{target_site}/lists/{library_id}/columns"
        columns_data = await self.graph_client.get(columns_endpoint)
        
        return {
            "library": library_data,
            "columns": columns_data.get("value", [])
        }

    async def _create_library_rest_fallback(self, library: DocumentLibrary, site_id: str) -> Dict[str, Any]:
        """Fall back to SharePoint REST API for library creation if Graph fails.
        
        Uses OBO flow to maintain user identity.
        """
        # Get the user token from the graph client (if available)
        user_token = self.graph_client._user_token if self.graph_client else None
        if not user_token:
            raise SharePointProvisioningException("User token not available for REST fallback")

        # Determine site URL and rest_client (assumes availability or can be passed)
        # For simplicity, we try to get headers via auth_service
        from src.infrastructure.services.authentication_service import AuthenticationService
        auth_service = self.graph_client.auth_service
        headers = await auth_service.get_rest_headers_obo(user_token, site_id)
        
        # Use nometadata for consistency with page fallback
        headers["Accept"] = "application/json;odata=nometadata"
        headers["Content-Type"] = "application/json;odata=nometadata"
        
        # Determine site URL via Graph API
        site_info = await self.graph_client.get(f"/sites/{site_id}")
        site_url = site_info.get("webUrl", "")
        if not site_url:
            raise SharePointProvisioningException(f"Could not resolve webUrl for site {site_id}")
        
        endpoint = f"{site_url}/_api/web/lists"
        
        # REST API payload for document library (BaseTemplate: 101)
        payload = {
            "Title": library.title,
            "Description": library.description,
            "BaseTemplate": 101, # documentLibrary
            "AllowContentTypes": True
        }
        
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            if not response.is_success:
                logger.error("REST Library Fallback failed: %s. Response: %s", response.status_code, response.text)
                raise SharePointProvisioningException(f"REST library fallback failed: {response.text}")
            
            data = response.json()
            return {
                "id": str(data.get("Id", "")),
                "displayName": library.title,
                "webUrl": data.get("AbsoluteUrl", "") or f"{site_url}/{library.title.replace(' ', '')}"
            }
