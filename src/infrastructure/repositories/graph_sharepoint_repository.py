"""Concrete SharePoint repository implementation.

Delegates every operation to one of the specialized services wired in __init__:
    SiteService, ListService, PageService, LibraryService, DriveService,
    PermissionService, EnterpriseService, DataService.

This file contains the single class GraphAPISharePointRepository.
Import it via:
    from src.infrastructure.repositories import GraphAPISharePointRepository
or directly:
    from src.infrastructure.repositories.graph_sharepoint_repository import GraphAPISharePointRepository
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)
from src.infrastructure.services.cache_service import cache_with_ttl
from src.domain.entities import (
    SPList, SPPage, DocumentLibrary, SharePointGroup,
    ContentType, TermSet, SPView, LibraryItem
)
from src.domain.entities.core import SPPermissionMask
from src.domain.repositories import SharePointRepository
from src.infrastructure.config import settings
from src.infrastructure.services.authentication_service import AuthenticationService
from src.infrastructure.services.graph_api_client import GraphAPIClient
from src.infrastructure.services.rest_api_client import RESTAPIClient
from src.infrastructure.services.batch_operations_service import BatchOperationsService
from src.infrastructure.services.sharepoint.list_service import ListService
from src.infrastructure.services.sharepoint.page_service import PageService
from src.infrastructure.services.sharepoint.library_service import LibraryService
from src.infrastructure.services.sharepoint.permission_service import PermissionService
from src.infrastructure.services.sharepoint.enterprise_service import EnterpriseService
from src.infrastructure.services.sharepoint.data_service import DataService
from src.infrastructure.services.sharepoint.site_service import SiteService
from src.infrastructure.services.sharepoint.drive_service import DriveService


class GraphAPISharePointRepository(SharePointRepository):
    """Implementation of SharePointRepository delegating to specialized services."""

    def __init__(self, user_token: Optional[str] = None, site_id: Optional[str] = None):
        """Initialize repository with all required services.

        Args:
            user_token: Optional raw Bearer token from the user's request.
                        When provided, all Graph API calls are made on behalf
                        of that user via the OBO flow (enforces SharePoint
                        permissions). When None, falls back to the service
                        account client-credentials token.
            site_id: Optional site ID to use as the default for all operations.
                     When provided, overrides settings.SITE_ID so operations
                     target the site from the request context rather than the
                     environment configuration.
        """
        self.site_id = site_id or settings.SITE_ID
        
        # Initialize base services
        self.auth_service = AuthenticationService()
        self.graph_client = GraphAPIClient(self.auth_service, self.site_id, user_token=user_token)
        self.rest_client = RESTAPIClient(self.auth_service, self.site_id, user_token=user_token)
        self.batch_service = BatchOperationsService(self.graph_client)
        
        # Initialize specialized SharePoint services
        self.lists = ListService(self.graph_client)
        self.pages = PageService(self.rest_client, self.graph_client)
        self.libraries = LibraryService(self.graph_client)
        self.drives = DriveService(self.graph_client)
        self.permissions = PermissionService(self.rest_client)
        self.enterprise = EnterpriseService(self.graph_client, self.rest_client)
        self.data = DataService(self.batch_service)
        self.sites = SiteService(self.graph_client, self.rest_client)

    def _get_site_id(self, site_id: str = None) -> str:
        """Get the site ID to use for operations.
        
        Args:
            site_id: Optional site ID. If None, returns default configured site.
            
        Returns:
            Site ID to use
        """
        return site_id if site_id else self.site_id

    # ── SITE OPERATIONS ─────────────────────────────────────

    async def create_site(self, sp_site) -> Dict[str, Any]:
        """Create a site in SharePoint."""
        return await self.sites.create_site(sp_site)

    # ── LIST OPERATIONS ─────────────────────────────────────

    async def create_list(self, sp_list: SPList, site_id: str = None) -> Dict[str, Any]:
        """Create a list in SharePoint.
        
        Args:
            sp_list: SPList entity to create
            site_id: Optional site ID. If None, uses default configured site.
        """
        target_site_id = self._get_site_id(site_id)
        endpoint = f"/sites/{target_site_id}/lists"
        from src.infrastructure.repositories.utils.payload_builders import PayloadBuilders
        payload = PayloadBuilders.build_list_payload(sp_list)
        data = await self.graph_client.post(endpoint, payload)
        data["resource_link"] = data.get("webUrl", "")
        return data

    async def get_list(self, list_id: str, site_id: Optional[str] = None) -> SPList:
        """Get a list by ID from SharePoint."""
        target_site_id = self._get_site_id(site_id)
        endpoint = f"/sites/{target_site_id}/lists/{list_id}?$expand=columns"
        data = await self.graph_client.get(endpoint)
        from src.domain.value_objects import SPColumn
        
        # Handle columns - can be a dict with 'value' key or a list directly
        columns_data = data.get("columns", {})
        if isinstance(columns_data, dict):
            columns_list = columns_data.get("value", [])
        elif isinstance(columns_data, list):
            columns_list = columns_data
        else:
            columns_list = []
            
        columns = [
            SPColumn(
                name=col["name"],
                type=col.get("columnGroup", "text"),
                required=col.get("required", False),
            )
            for col in columns_list
        ] or [SPColumn(name="Title", type="text", required=True)]
        
        # Handle list_details - can be a dict or other types
        list_details = data.get("list", {})
        if not isinstance(list_details, dict):
            list_details = {}
            
        return SPList(
            title=data.get("displayName", ""),
            description=data.get("description", ""),
            columns=columns,
            list_id=data.get("id", ""),
            item_count=list_details.get("itemCount", 0),
        )

    @cache_with_ttl(ttl=300, key_prefix="lists:")
    async def get_all_lists(self, site_id: str = None) -> List[Dict[str, Any]]:
        """Get all lists on the SharePoint site with full pagination support.
        
        Args:
            site_id: Optional site ID. If None, uses default configured site.
        """
        target_site_id = self._get_site_id(site_id)
        endpoint = f"/sites/{target_site_id}/lists"
        all_lists = []
        next_link = endpoint
        while next_link:
            data = await self.graph_client.get(next_link)
            all_lists.extend(data.get("value", []))
            next_link = data.get("@odata.nextLink")
        return all_lists

    async def get_list_items(self, list_id: str, site_id: str = None) -> List[Dict[str, Any]]:
        """Get all items from a SharePoint list.
        
        Args:
            list_id: ID of the list
            site_id: Optional site ID. If None, uses default configured site.
        """
        target_site_id = self._get_site_id(site_id)
        endpoint = f"/sites/{target_site_id}/lists/{list_id}/items?expand=fields"
        
        all_items = []
        next_link = endpoint
        
        while next_link:
            data = await self.graph_client.get(next_link)
            all_items.extend(data.get("value", []))
            next_link = data.get("@odata.nextLink")
        
        return all_items

    async def search_lists(self, query: str) -> List[Dict[str, Any]]:
        """Search for lists by display name."""
        return await self.lists.search_lists(query)

    async def get_all_sites(self) -> List[Dict[str, Any]]:
        """Get all SharePoint sites in the organization."""
        try:
            # Use Graph API to search for all sites the user has access to
            endpoint = "/sites?search=*&$select=id,name,displayName,webUrl,description"
            response = await self.graph_client.get(endpoint)
            return response.get("value", [])
        except Exception as exc:
            logger.error("get_all_sites failed: %s", exc, exc_info=True)
            from src.domain.exceptions import SharePointAPIError
            raise SharePointAPIError("Unable to retrieve sites", status_code=500) from exc

    async def update_list(self, list_id: str, sp_list: SPList, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Update an existing list in SharePoint (metadata + columns)."""
        target_site_id = self._get_site_id(site_id)
        return await self.lists.update_list(list_id, sp_list, site_id=target_site_id)

    async def delete_list(self, list_id: str, site_id: Optional[str] = None) -> bool:
        """Delete a list from SharePoint."""
        return await self.lists.delete_list(list_id, site_id=self._get_site_id(site_id))

    async def enable_list_versioning(
        self, list_id: str, site_id: Optional[str] = None, major_version_limit: int = 500
    ) -> Dict[str, Any]:
        """Enable major versioning on a SharePoint list or document library.

        Args:
            list_id: The SharePoint list/library GUID.
            site_id: Optional site to target. Defaults to the configured site.
            major_version_limit: Maximum number of major versions to retain.

        Returns:
            The Graph API response dict.
        """
        target_site_id = self._get_site_id(site_id)
        endpoint = f"/sites/{target_site_id}/lists/{list_id}"
        payload = {
            "list": {
                "enableVersioning": True,
                "majorVersionLimit": major_version_limit,
            }
        }
        return await self.graph_client.patch(endpoint, payload)

    # ── PAGE OPERATIONS ─────────────────────────────────────

    async def create_page(self, sp_page: SPPage, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a page in SharePoint."""
        return await self.pages.create_page(sp_page, site_id=site_id)

    async def get_page(self, page_id: str) -> SPPage:
        """Get a page by ID from SharePoint."""
        return await self.pages.get_page(page_id)

    async def update_page_content(self, page_id: str, sp_page: SPPage) -> Dict[str, Any]:
        """Update the content/webparts of an existing page."""
        return await self.pages.update_page_content(page_id, sp_page)

    async def delete_page(self, page_id: str) -> bool:
        """Delete a page from SharePoint."""
        return await self.pages.delete_page(page_id)

    # ── DOCUMENT LIBRARY OPERATIONS ─────────────────────────

    async def create_document_library(self, library: DocumentLibrary, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a document library in SharePoint."""
        return await self.libraries.create_document_library(library, site_id=self._get_site_id(site_id))

    async def get_all_document_libraries(self, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all document libraries on the SharePoint site.

        Args:
            site_id: Optional site ID. If None, uses the default configured site.
        """
        return await self.libraries.get_all_document_libraries(site_id=self._get_site_id(site_id))

    async def search_libraries(self, query: str, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search for document libraries by display name."""
        return await self.libraries.search_libraries(query, site_id=self._get_site_id(site_id))

    async def update_document_library(
        self,
        library_id: str,
        metadata: Dict[str, Any],
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update document library settings and metadata."""
        return await self.libraries.update_library_metadata(library_id, metadata)

    async def delete_document_library(
        self,
        library_id: str,
        site_id: Optional[str] = None
    ) -> bool:
        """Delete a document library."""
        return await self.libraries.delete_document_library(
            library_id,
            site_id=self._get_site_id(site_id),
        )

    async def add_library_column(
        self,
        library_id: str,
        column_name: str,
        column_type: str,
        required: bool = False,
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Add a column to a document library."""
        return await self.libraries.add_library_column(
            library_id, column_name, column_type, required
        )

    async def get_library_schema(
        self,
        library_id: str,
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get library schema including all columns."""
        return await self.libraries.get_library_schema(library_id, site_id=self._get_site_id(site_id))

    # ── FILE OPERATIONS ─────────────────────────────────────

    async def get_library_items(
        self, library_id: str, site_id: Optional[str] = None
    ) -> List[LibraryItem]:
        """Get all files from a document library.
        
        Args:
            library_id: ID of the document library
            site_id: Optional site ID (currently unused, kept for interface compatibility)
        """
        return await self.drives.get_library_items(library_id)

    async def upload_file(
        self,
        library_id: str,
        file_name: str,
        file_content: bytes,
        metadata: Optional[Dict[str, Any]] = None,
        site_id: Optional[str] = None
    ) -> LibraryItem:
        """Upload a file to a document library.
        
        Args:
            library_id: ID of the target document library
            file_name: Name of the file to upload
            file_content: Binary content of the file
            metadata: Optional custom metadata
            site_id: Optional site ID (currently unused, kept for interface compatibility)
        """
        return await self.drives.upload_file(library_id, file_name, file_content, metadata)

    async def download_file(
        self, library_id: str, file_id: str, site_id: Optional[str] = None
    ) -> bytes:
        """Download file content from a document library.

        Resolves the drive_id from the library_id so the caller only needs to
        supply the domain-level library identifier.

        Args:
            library_id: ID of the document library (SharePoint list GUID).
            file_id: ID of the file to download.
            site_id: Optional site ID override (reserved for future use).
        """
        drive_id = await self.drives.get_library_drive_id(library_id)
        return await self.drives.download_file(file_id, drive_id)

    async def delete_file(
        self, file_id: str, drive_id: str, site_id: Optional[str] = None
    ) -> bool:
        """Delete a file from a document library.

        Args:
            file_id: Drive item ID of the file to delete.
            drive_id: Drive ID that contains the file (from LibraryItem.drive_id).
            site_id: Optional site ID override (reserved for future use).
        """
        return await self.drives.delete_file(file_id, drive_id)

    async def update_file_metadata(
        self, file_id: str, drive_id: str, metadata: Dict[str, Any]
    ) -> LibraryItem:
        """Update metadata of a file.
        
        Args:
            file_id: ID of the file to update
            drive_id: ID of the drive containing the file
            metadata: Metadata fields to update
        """
        return await self.drives.update_file_metadata(file_id, drive_id, metadata)

    async def get_library_drive_id(
        self, library_id: str, site_id: Optional[str] = None
    ) -> str:
        """Get the drive ID for a document library.
        
        Args:
            library_id: ID of the document library
            site_id: Optional site ID (currently unused, kept for interface compatibility)
        """
        return await self.drives.get_library_drive_id(library_id)

    async def query_library_files(
        self,
        library_id: str,
        filter_query: Optional[str] = None,
        select_fields: Optional[List[str]] = None,
        order_by: Optional[str] = None,
        top: Optional[int] = None,
        skip: Optional[int] = None,
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Query files in a library with advanced filtering and sorting."""
        return await self.drives.query_library_files(
            library_id, filter_query, select_fields, order_by, top, skip
        )

    async def get_file_by_path(
        self,
        library_id: str,
        file_path: str,
        site_id: Optional[str] = None
    ) -> Optional[LibraryItem]:
        """Get a file by its path in the library."""
        return await self.drives.get_file_by_path(library_id, file_path)

    async def copy_file(
        self,
        source_drive_id: str,
        source_file_id: str,
        destination_drive_id: str,
        destination_folder_path: Optional[str] = None,
        new_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Copy a file to another location."""
        return await self.drives.copy_file(
            source_drive_id, source_file_id, destination_drive_id,
            destination_folder_path, new_name
        )

    async def move_file(
        self,
        drive_id: str,
        file_id: str,
        destination_folder_id: Optional[str] = None,
        new_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Move a file to another location or rename it."""
        return await self.drives.move_file(
            drive_id, file_id, destination_folder_id, new_name
        )

    async def get_file_versions(
        self,
        drive_id: str,
        file_id: str
    ) -> List[Dict[str, Any]]:
        """Get all versions of a file."""
        return await self.drives.get_file_versions(drive_id, file_id)

    async def restore_file_version(
        self,
        drive_id: str,
        file_id: str,
        version_id: str
    ) -> Dict[str, Any]:
        """Restore a specific version of a file."""
        return await self.drives.restore_file_version(drive_id, file_id, version_id)

    async def checkout_file(
        self,
        drive_id: str,
        file_id: str
    ) -> bool:
        """Check out a file for editing."""
        return await self.drives.checkout_file(drive_id, file_id)

    async def checkin_file(
        self,
        drive_id: str,
        file_id: str,
        comment: Optional[str] = None
    ) -> bool:
        """Check in a file after editing."""
        return await self.drives.checkin_file(drive_id, file_id, comment)

    async def create_file_share_link(
        self,
        drive_id: str,
        file_id: str,
        link_type: str = "view",
        scope: str = "organization"
    ) -> Dict[str, Any]:
        """Create a sharing link for a file."""
        return await self.drives.create_file_share_link(
            drive_id, file_id, link_type, scope
        )

    async def create_folder(
        self,
        library_id: str,
        folder_name: str,
        parent_folder_path: Optional[str] = None,
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a folder in a document library."""
        return await self.drives.create_folder(
            library_id, folder_name, parent_folder_path
        )

    async def delete_folder(
        self,
        drive_id: str,
        folder_id: str
    ) -> bool:
        """Delete a folder and its contents."""
        return await self.drives.delete_folder(drive_id, folder_id)

    async def get_folder_contents(
        self,
        drive_id: str,
        folder_id: Optional[str] = None,
        folder_path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get contents of a folder."""
        return await self.drives.get_folder_contents(drive_id, folder_id, folder_path)

    async def batch_upload_files(
        self,
        library_id: str,
        files: List[Dict[str, Any]],
        site_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Upload multiple files in batch."""
        return await self.drives.batch_upload_files(library_id, files)

    async def batch_delete_files(
        self,
        drive_id: str,
        file_ids: List[str]
    ) -> Dict[str, Any]:
        """Delete multiple files in batch."""
        return await self.drives.batch_delete_files(drive_id, file_ids)

    # ── GROUPS & PERMISSIONS ────────────────────────────────

    async def get_site_groups(self) -> List[Dict[str, Any]]:
        """Get all SharePoint site groups."""
        return await self.permissions.get_site_groups()

    async def create_site_group(self, group: SharePointGroup, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a new SharePoint site group."""
        return await self.permissions.create_site_group(group)

    async def assign_library_permission(
        self, library_id: str, group_id: str, permission_level: str
    ) -> bool:
        """Assign permissions to a group on a document library."""
        return await self.permissions.assign_library_permission(
            library_id, group_id, permission_level
        )

    # ── ENTERPRISE ARCHITECTURE ─────────────────────────────

    async def create_content_type(self, content_type: ContentType) -> Dict[str, Any]:
        """Create a SharePoint Content Type."""
        return await self.enterprise.create_content_type(content_type)

    async def create_term_set(self, term_set: TermSet) -> Dict[str, Any]:
        """Create a Managed Metadata Term Set."""
        return await self.enterprise.create_term_set(term_set)

    async def create_view(self, view: SPView) -> Dict[str, Any]:
        """Create a List View."""
        return await self.enterprise.create_view(view)

    # ── DATA OPERATIONS ─────────────────────────────────────

    async def seed_list_data(
        self, list_id: str, seed_data: List[Dict[str, Any]], site_id: str = None
    ) -> bool:
        """Seed a list with data items."""
        return await self.data.seed_list_data(list_id, seed_data, site_id=site_id)

    # ── LIST ITEM OPERATIONS ────────────────────────────────

    async def create_list_item(self, list_id: str, item_data: Dict[str, Any], site_id: str = None) -> Dict[str, Any]:
        """Create a single item in a SharePoint list."""
        return await self.lists.create_list_item(list_id, item_data, site_id=site_id)

    async def update_list_item(self, list_id: str, item_id: str, item_data: Dict[str, Any], site_id: str = None) -> Dict[str, Any]:
        """Update a single item in a SharePoint list."""
        return await self.lists.update_list_item(list_id, item_id, item_data, site_id=site_id)

    async def delete_list_item(self, list_id: str, item_id: str, site_id: str = None) -> bool:
        """Delete a single item from a SharePoint list."""
        return await self.lists.delete_list_item(list_id, item_id, site_id=site_id)

    async def query_list_items(self, list_id: str, filter_query: str = None, site_id: str = None) -> List[Dict[str, Any]]:
        """Query list items with optional OData filter."""
        return await self.lists.query_list_items(list_id, filter_query, site_id=site_id)

    async def query_list_items_advanced(
        self, list_id: str, filter_query: Optional[str] = None,
        select_fields: Optional[List[str]] = None, order_by: Optional[str] = None,
        top: Optional[int] = None, skip: Optional[int] = None,
        expand: Optional[List[str]] = None, site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Query list items with advanced OData parameters."""
        return await self.lists.query_list_items_advanced(
            list_id, filter_query, select_fields, order_by, top, skip, expand, site_id=site_id
        )

    async def add_item_attachment(self, list_id: str, item_id: str, file_name: str,
                                   file_content: bytes, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Add an attachment to a list item."""
        return await self.lists.add_item_attachment(list_id, item_id, file_name, file_content)

    async def get_item_attachments(self, list_id: str, item_id: str,
                                    site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all attachments for a list item."""
        return await self.lists.get_item_attachments(list_id, item_id)

    async def delete_item_attachment(self, list_id: str, item_id: str, attachment_id: str,
                                      site_id: Optional[str] = None) -> bool:
        """Delete an attachment from a list item."""
        return await self.lists.delete_item_attachment(list_id, item_id, attachment_id)

    async def get_list_schema(self, list_id: str, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Get the schema/column definitions for a list."""
        return await self.lists.get_list_schema(list_id, site_id=site_id)

    async def create_list_view(self, list_id: str, view_name: str, view_fields: List[str],
                                view_query: Optional[str] = None, is_default: bool = False,
                                site_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a custom view for a list."""
        return await self.lists.create_list_view(list_id, view_name, view_fields, view_query, is_default)

    async def get_list_views(self, list_id: str, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all views for a list."""
        return await self.lists.get_list_views(list_id)

    async def delete_list_view(self, list_id: str, view_id: str,
                                site_id: Optional[str] = None) -> bool:
        """Delete a custom view from a list."""
        return await self.lists.delete_list_view(list_id, view_id)

    # ── PAGE OPERATIONS (EXTENDED) ──────────────────────────
    @cache_with_ttl(ttl=300, key_prefix="pages:")
    async def get_all_pages(self, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all pages from a site."""
        return await self.pages.get_all_pages(site_id)

    async def search_pages(self, query: str, site_id: Optional[str] = None) ->List[Dict[str, Any]]:
        """Search pages by title or content."""
        return await self.pages.search_pages(query, site_id)

    async def get_page_by_name(self, page_name: str, site_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get a page by its name/path."""
        return await self.pages.get_page_by_name(page_name, site_id)

    async def publish_page(self, page_id: str, site_id: Optional[str] = None) -> bool:
        """Publish a page."""
        return await self.pages.publish_page(page_id, site_id)

    async def unpublish_page(self, page_id: str, site_id: Optional[str] = None) -> bool:
        """Unpublish a page."""
        return await self.pages.unpublish_page(page_id, site_id)

    async def checkout_page(self, page_id: str, site_id: Optional[str] = None) -> bool:
        """Check out a page."""
        return await self.pages.checkout_page(page_id, site_id)

    async def checkin_page(self, page_id: str, comment: Optional[str] = None, site_id: Optional[str] = None) -> bool:
        """Check in a page."""
        return await self.pages.checkin_page(page_id, comment, site_id)

    async def discard_page_checkout(self, page_id: str, site_id: Optional[str] = None) -> bool:
        """Discard page checkout."""
        return await self.pages.discard_page_checkout(page_id, site_id)

    async def copy_page(self, source_page_id: str, new_title: str, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Copy a page."""
        return await self.pages.copy_page(source_page_id, new_title, site_id)

    async def get_page_versions(self, page_id: str, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get page versions."""
        return await self.pages.get_page_versions(page_id, site_id)

    async def restore_page_version(self, page_id: str, version_id: str, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Restore a page version."""
        return await self.pages.restore_page_version(page_id, version_id, site_id)

    async def promote_page_as_news(self, page_id: str, site_id: Optional[str] =None) -> bool:
        """Promote page as news."""
        return await self.pages.promote_page_as_news(page_id, site_id)

    async def create_page_share_link(self, page_id: str, link_type: str = "view", site_id: Optional[str] = None) -> Dict[str, Any]:
        """Create sharing link for page."""
        return await self.pages.create_page_share_link(page_id, link_type, site_id)

    async def get_page_analytics(self, page_id: str, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Get page analytics."""
        return await self.pages.get_page_analytics(page_id, site_id)

    async def schedule_page_publish(self, page_id: str, scheduled_datetime: str, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Schedule page publish."""
        return await self.pages.schedule_page_publish(page_id, scheduled_datetime, site_id)

    # ── SITE OPERATIONS (EXTENDED) ──────────────────────────
    async def get_site(self, site_id: str) -> Dict[str, Any]:
        """Get a site by ID."""
        return await self.sites.get_site(site_id)

    async def get_site_by_url(self, site_url: str) -> Dict[str, Any]:
        """Get a site by URL."""
        return await self.sites.get_site_by_url(site_url)

    async def search_sites(self, query: str) -> List[Dict[str, Any]]:
        """Search sites."""
        return await self.sites.search_sites(query)

    async def update_site(self, site_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update site properties."""
        return await self.sites.update_site(site_id, updates)

    async def delete_site(self, site_id: str) -> bool:
        """Delete a site."""
        return await self.sites.delete_site(site_id)

    async def get_site_owners(self, site_id: str) -> List[Dict[str, Any]]:
        """Get site owners."""
        return await self.sites.get_site_owners(site_id)

    async def get_site_members(self, site_id: str) -> List[Dict[str, Any]]:
        """Get site members."""
        return await self.sites.get_site_members(site_id)

    async def add_site_owner(self, site_id: str, user_email: str) -> bool:
        """Add site owner."""
        return await self.sites.add_site_owner(site_id, user_email)

    async def add_site_member(self, site_id: str, user_email: str) -> bool:
        """Add site member."""
        return await self.sites.add_site_member(site_id, user_email)

    async def remove_site_user(self, site_id: str, user_id: str) -> bool:
        """Remove user from site."""
        return await self.sites.remove_site_user(site_id, user_id)

    async def get_site_permissions(self, site_id: str) -> Dict[str, Any]:
        """Get site permissions."""
        return await self.sites.get_site_permissions(site_id)

    async def update_site_theme(self, site_id: str, theme_settings: Dict[str, Any]) -> bool:
        """Update site theme."""
        return await self.sites.update_site_theme(site_id, theme_settings)

    async def get_site_navigation(self, site_id: str, nav_type: str = "top") -> List[Dict[str, Any]]:
        """Get site navigation."""
        return await self.sites.get_site_navigation(site_id, nav_type)

    async def update_site_navigation(self, site_id: str, nav_type: str, nav_items: List[Dict[str, Any]]) -> bool:
        """Update site navigation."""
        return await self.sites.update_site_navigation(site_id, nav_type, nav_items)

    async def get_site_storage_info(self, site_id: str) -> Dict[str, Any]:
        """Get site storage info."""
        return await self.sites.get_site_storage_info(site_id)

    async def get_site_analytics(self, site_id: str, period: str = "last7days") -> Dict[str, Any]:
        """Get site analytics."""
        return await self.sites.get_site_analytics(site_id, period)

    async def get_site_recycle_bin(self, site_id: str) -> List[Dict[str, Any]]:
        """Get recycle bin items."""
        return await self.sites.get_site_recycle_bin(site_id)

    async def restore_from_recycle_bin(self, site_id: str, item_id: str) -> bool:
        """Restore from recycle bin."""
        return await self.sites.restore_from_recycle_bin(site_id, item_id)

    async def empty_recycle_bin(self, site_id: str) -> bool:
        """Empty recycle bin."""
        return await self.sites.empty_recycle_bin(site_id)

    # ── ILISTREPOSITORY ─────────────

    async def get_list_item(
        self,
        list_id: str,
        item_id: str,
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get a specific list item by ID."""
        target_site_id = self._get_site_id(site_id)
        endpoint = f"/sites/{target_site_id}/lists/{list_id}/items/{item_id}?expand=fields"
        return await self.graph_client.get(endpoint)

    async def get_list_columns(
        self,
        list_id: str,
        site_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all columns for a list."""
        target_site_id = self._get_site_id(site_id)
        endpoint = f"/sites/{target_site_id}/lists/{list_id}/columns"
        data = await self.graph_client.get(endpoint)
        return data.get("value", [])

    async def add_list_column(
        self,
        list_id: str,
        column_data: Dict[str, Any],
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Add a column to a list."""
        return await self.lists.add_list_column(list_id, column_data)

    # ── IPERMISSIONREPOSITORY: MISSING IMPLEMENTATIONS ───────

    async def create_group(
        self,
        group,
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a SharePoint group."""
        return await self.permissions.create_site_group(group)

    async def get_all_groups(
        self,
        site_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all groups in a site."""
        return await self.permissions.get_site_groups()

    async def get_group(
        self,
        group_id: str,
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        return await self.permissions.get_group(group_id)

    async def update_group(
        self,
        group_id: str,
        updates: Dict[str, Any],
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        return await self.permissions.update_group(group_id, updates)

    async def delete_group(
        self,
        group_id: str,
        site_id: Optional[str] = None
    ) -> bool:
        return await self.permissions.delete_group(group_id)

    async def add_user_to_group(
        self,
        group_id: str,
        user_email: str,
        site_id: Optional[str] = None
    ) -> bool:
        return await self.permissions.add_user_to_group(group_id, user_email)

    async def remove_user_from_group(
        self,
        group_id: str,
        user_id: str,
        site_id: Optional[str] = None
    ) -> bool:
        return await self.permissions.remove_user_from_group(group_id, user_id)

    async def get_group_members(
        self,
        group_id: str,
        site_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return await self.permissions.get_group_members(group_id)

    async def get_list_permissions(
        self,
        list_id: str,
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        return await self.permissions.get_list_permissions(list_id)

    async def get_item_permissions(
        self,
        list_id: str,
        item_id: str,
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        return await self.permissions.get_item_permissions(list_id, item_id)

    async def grant_list_permissions(
        self,
        list_id: str,
        principal_id: str,
        permission_level,
        site_id: Optional[str] = None
    ) -> bool:
        return await self.permissions.grant_list_permissions(list_id, principal_id, permission_level)

    async def revoke_list_permissions(
        self,
        list_id: str,
        principal_id: str,
        site_id: Optional[str] = None
    ) -> bool:
        return await self.permissions.revoke_list_permissions(list_id, principal_id)

    async def ensure_user_principal_id(self, user_email: str, site_id: Optional[str] = None) -> int:
        """Resolve a user email to their numeric SharePoint principal ID."""
        return await self.permissions.ensure_user_principal_id(user_email)

    async def break_permission_inheritance(
        self,
        list_id: str,
        copy_role_assignments: bool = True,
        site_id: Optional[str] = None
    ) -> bool:
        return await self.permissions.break_permission_inheritance(list_id, copy_role_assignments)

    async def reset_permission_inheritance(
        self,
        list_id: str,
        site_id: Optional[str] = None
    ) -> bool:
        return await self.permissions.reset_permission_inheritance(list_id)

    async def get_permission_levels(self, site_id: str) -> List[Dict[str, Any]]:
        return await self.permissions.get_permission_levels()

    async def create_custom_permission_level(
        self,
        site_id: str,
        level_name: str,
        permissions: List[str]
    ) -> Dict[str, Any]:
        from src.domain.exceptions import DomainException
        raise DomainException(
            "create_custom_permission_level is not supported via API — "
            "use the SharePoint Admin Center to manage custom permission levels.",
            http_status=501,
        )

    async def check_user_permission(
        self,
        user_login: str,
        required_mask: SPPermissionMask,
        list_title: Optional[str] = None,
    ) -> bool:
        """Check whether a user has the required permission mask.

        Delegates to the injected PermissionService.
        """
        return await self.permissions.check_user_permission(
            user_login, required_mask, list_title
        )

    # ── IENTREPRISEREPOSITORY: MISSING IMPLEMENTATIONS ───────

    async def get_content_types(
        self,
        site_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return await self.enterprise.get_content_types(site_id)

    async def get_content_type(
        self,
        content_type_id: str,
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        return await self.enterprise.get_content_type(content_type_id, site_id)

    async def update_content_type(
        self,
        content_type_id: str,
        updates: Dict[str, Any],
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        return await self.enterprise.update_content_type(content_type_id, updates, site_id)

    async def delete_content_type(
        self,
        content_type_id: str,
        site_id: Optional[str] = None
    ) -> bool:
        return await self.enterprise.delete_content_type(content_type_id, site_id)

    async def add_content_type_to_list(
        self,
        list_id: str,
        content_type_id: str,
        site_id: Optional[str] = None
    ) -> bool:
        """Associate a content type with a list."""
        return await self.lists.associate_content_type(list_id, content_type_id)

    async def get_term_sets(
        self,
        site_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return await self.enterprise.get_term_sets(site_id)

    async def get_term_set(
        self,
        term_set_id: str,
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        return await self.enterprise.get_term_set(term_set_id, site_id)

    async def add_term_to_set(
        self,
        term_set_id: str,
        term_label: str,
        parent_term_id: Optional[str] = None,
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        return await self.enterprise.add_term_to_set(term_set_id, term_label, parent_term_id, site_id)

    async def delete_term_set(
        self,
        term_set_id: str,
        site_id: Optional[str] = None
    ) -> bool:
        return await self.enterprise.delete_term_set(term_set_id, site_id)

    async def get_views(
        self,
        list_id: str,
        site_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all views for a list."""
        return await self.lists.get_list_views(list_id)

    async def get_view(
        self,
        list_id: str,
        view_id: str,
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get a specific view by ID."""
        target_site_id = self._get_site_id(site_id)
        endpoint = f"/sites/{target_site_id}/lists/{list_id}/views/{view_id}"
        return await self.graph_client.get(endpoint)

    async def update_view(
        self,
        list_id: str,
        view_id: str,
        updates: Dict[str, Any],
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        return await self.enterprise.update_view(list_id, view_id, updates)

    async def delete_view(
        self,
        list_id: str,
        view_id: str,
        site_id: Optional[str] = None
    ) -> bool:
        """Delete a view."""
        return await self.lists.delete_list_view(list_id, view_id)

    # ── ILIBRARYREPOSITORY: MISSING IMPLEMENTATIONS ──────────

    async def discard_file_checkout(
        self,
        library_id: str,
        file_id: str,
        site_id: Optional[str] = None
    ) -> bool:
        drive_id = await self.drives.get_library_drive_id(library_id)
        return await self.drives.discard_file_checkout(drive_id, file_id)
