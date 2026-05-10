"""Service for SharePoint Drive (Document Library) file operations."""

import logging
from typing import Dict, Any, List, Optional
import httpx
from src.domain.entities.document import LibraryItem
from src.domain.exceptions import SharePointProvisioningException
from src.infrastructure.services.graph_api_client import GraphAPIClient
from src.infrastructure.repositories.utils.error_handlers import handle_sharepoint_errors
from src.infrastructure.repositories.utils.payload_builders import PayloadBuilders

logger = logging.getLogger(__name__)


class DriveService:
    """Handles all SharePoint Drive and file operations."""
    
    # File size thresholds
    SMALL_FILE_THRESHOLD = 4 * 1024 * 1024  # 4MB - use simple upload
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB - maximum supported
    CHUNK_SIZE = 10 * 1024 * 1024  # 10MB chunks for resumable upload

    def __init__(self, graph_client: GraphAPIClient):
        """Initialize drive service.
        
        Args:
            graph_client: Graph API client for making requests
        """
        self.graph_client = graph_client

    @handle_sharepoint_errors("get library drive ID")
    async def get_library_drive_id(self, library_id: str, site_id: Optional[str] = None) -> str:
        """Get the drive ID for a document library.
        
        Args:
            library_id: SharePoint list ID of the document library
            site_id: Optional site ID override
            
        Returns:
            Drive ID corresponding to the library
        """
        target_site = site_id or self.graph_client.site_id
        endpoint = f"/sites/{target_site}/lists/{library_id}/drive"
        data = await self.graph_client.get(endpoint)
        return data.get("id", "")

    @handle_sharepoint_errors("get library items")
    async def get_library_items(self, library_id: str) -> List[LibraryItem]:
        """Get all files from a document library with pagination.
        
        Args:
            library_id: SharePoint list ID of the document library
            
        Returns:
            List of LibraryItem entities
        """
        # First get the drive ID
        drive_id = await self.get_library_drive_id(library_id)
        
        # Get items from the drive root
        endpoint = f"/drives/{drive_id}/root/children"
        items = []
        page_count = 0
        max_pages = 20  # Limit pagination to avoid excessive requests
        
        while endpoint and page_count < max_pages:
            data = await self.graph_client.get(endpoint)
            
            # Filter for files only (exclude folders)
            file_items = [
                item for item in data.get("value", [])
                if "file" in item  # Only include files, not folders
            ]
            
            # Convert to LibraryItem entities
            for item in file_items:
                try:
                    library_item = PayloadBuilders.library_item_from_graph_response(
                        item, library_id, drive_id
                    )
                    items.append(library_item)
                except Exception as e:
                    # Log and skip malformed items
                    logger.warning("Could not parse library item: %s", e)
            
            # Check for pagination
            endpoint = data.get("@odata.nextLink")
            page_count += 1
        
        return items

    @handle_sharepoint_errors("upload file")
    async def upload_file(
        self,
        library_id: str,
        file_name: str,
        file_content: bytes,
        metadata: Optional[Dict[str, Any]] = None
    ) -> LibraryItem:
        """Upload a file to a document library.
        
        Args:
            library_id: SharePoint list ID of the document library
            file_name: Name of the file to upload
            file_content: Binary content of the file
            metadata: Optional custom metadata
            
        Returns:
            LibraryItem entity representing the uploaded file
            
        Raises:
            SharePointProvisioningException: If file is too large or upload fails
        """
        file_size = len(file_content)
        
        # Validate file size
        if file_size > self.MAX_FILE_SIZE:
            raise SharePointProvisioningException(
                f"File size {file_size / (1024*1024):.2f}MB exceeds maximum "
                f"allowed size of {self.MAX_FILE_SIZE / (1024*1024)}MB"
            )
        
        # Get drive ID
        drive_id = await self.get_library_drive_id(library_id)
        
        # Choose upload method based on file size
        if file_size < self.SMALL_FILE_THRESHOLD:
            response = await self._upload_small_file(drive_id, file_name, file_content)
        else:
            response = await self._upload_large_file(drive_id, file_name, file_content)
        
        # Update metadata if provided
        if metadata:
            item_id = response.get("id")
            response = await self._update_file_metadata(drive_id, item_id, metadata)
        
        # Convert response to LibraryItem
        return PayloadBuilders.library_item_from_graph_response(response, library_id, drive_id)

    async def _upload_small_file(
        self, drive_id: str, file_name: str, file_content: bytes
    ) -> Dict[str, Any]:
        """Upload small file (<4MB) using simple PUT request.
        
        Args:
            drive_id: Drive ID
            file_name: File name
            file_content: File content
            
        Returns:
            Graph API response
        """
        endpoint = f"/drives/{drive_id}/root:/{file_name}:/content"
        url = f"{self.graph_client.base_url}{endpoint}"
        headers = await self.graph_client.auth_service.get_graph_headers()
        headers["Content-Type"] = "application/octet-stream"
        
        response = await self.graph_client.http.put(url, headers=headers, content=file_content)
        
        if not response.is_success:
            raise SharePointProvisioningException(
                f"File upload failed: {response.status_code}. Response: {response.text}"
            )
        
        return response.json()

    async def _upload_large_file(
        self, drive_id: str, file_name: str, file_content: bytes
    ) -> Dict[str, Any]:
        """Upload large file (4MB-100MB) using resumable upload session.
        
        Args:
            drive_id: Drive ID
            file_name: File name
            file_content: File content
            
        Returns:
            Graph API response
        """
        # Create upload session
        session_endpoint = f"/drives/{drive_id}/root:/{file_name}:/createUploadSession"
        session_data = await self.graph_client.post(session_endpoint, {
            "item": {
                "@microsoft.graph.conflictBehavior": "rename"
            }
        })
        
        upload_url = session_data.get("uploadUrl")
        if not upload_url:
            raise SharePointProvisioningException("Failed to create upload session")
        
        # Upload file in chunks
        file_size = len(file_content)
        offset = 0
        
        while offset < file_size:
            chunk_end = min(offset + self.CHUNK_SIZE, file_size)
            chunk = file_content[offset:chunk_end]
            
            headers = {
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {offset}-{chunk_end-1}/{file_size}"
            }
            
            response = await self.graph_client.http.put(upload_url, headers=headers, content=chunk)
            
            if response.status_code not in [200, 201, 202]:
                raise SharePointProvisioningException(
                    f"Chunk upload failed: {response.status_code}. Response: {response.text}"
                )
            
            offset = chunk_end
        
        # Final response contains the file metadata
        return response.json()

    @handle_sharepoint_errors("download file")
    async def download_file(self, file_id: str, drive_id: str) -> bytes:
        """Download file content.
        
        Args:
            file_id: File ID
            drive_id: Drive ID
            
        Returns:
            Binary file content
        """
        endpoint = f"/drives/{drive_id}/items/{file_id}/content"
        url = f"{self.graph_client.base_url}{endpoint}"
        headers = await self.graph_client.auth_service.get_graph_headers()
        
        response = await self.graph_client.http.get(url, headers=headers)
        
        if not response.is_success:
            raise SharePointProvisioningException(
                f"File download failed: {response.status_code}. Response: {response.text}"
            )
        
        return response.content

    @handle_sharepoint_errors("delete file")
    async def delete_file(self, file_id: str, drive_id: str) -> bool:
        """Delete a file from a document library.
        
        Args:
            file_id: File ID
            drive_id: Drive ID
            
        Returns:
            True if deletion was successful
        """
        endpoint = f"/drives/{drive_id}/items/{file_id}"
        return await self.graph_client.delete(endpoint)

    @handle_sharepoint_errors("update file metadata")
    async def update_file_metadata(
        self, file_id: str, drive_id: str, metadata: Dict[str, Any]
    ) -> LibraryItem:
        """Update metadata of a file.
        
        Args:
            file_id: File ID
            drive_id: Drive ID
            metadata: Metadata to update
            
        Returns:
            Updated LibraryItem
        """
        response = await self._update_file_metadata(drive_id, file_id, metadata)
        
        # We need library_id - try to get it from the response or metadata
        library_id = metadata.get("library_id", "")
        
        # Convert to LibraryItem
        return PayloadBuilders.library_item_from_graph_response(response, library_id, drive_id)

    async def _update_file_metadata(
        self, drive_id: str, file_id: str, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Internal method to update file metadata via PATCH.
        
        Args:
            drive_id: Drive ID
            file_id: File ID
            metadata: Metadata fields to update
            
        Returns:
            Updated file data
        """
        endpoint = f"/drives/{drive_id}/items/{file_id}"
        
        # Build payload for metadata update
        # Custom metadata goes in listItem.fields
        payload = {
            "name": metadata.get("name"),  # Can rename file
            "description": metadata.get("description", "")
        }
        
        # Remove None values
        payload = {k: v for k, v in payload.items() if v is not None}
        
        return await self.graph_client.patch(endpoint, payload)

    @handle_sharepoint_errors("query library files")
    async def query_library_files(
        self,
        library_id: str,
        filter_query: Optional[str] = None,
        select_fields: Optional[List[str]] = None,
        order_by: Optional[str] = None,
        top: Optional[int] = None,
        skip: Optional[int] = None
    ) -> Dict[str, Any]:
        """Query files in a library with advanced filtering.
        
        Args:
            library_id: Library ID
            filter_query: OData filter
            select_fields: Fields to select
            order_by: Order by field
            top: Max items
            skip: Skip items
            
        Returns:
            Query results with pagination
        """
        drive_id = await self.get_library_drive_id(library_id)
        
        # Build query parameters
        params = []
        if filter_query:
            params.append(f"$filter={filter_query}")
        if select_fields:
            params.append(f"$select={','.join(select_fields)}")
        if order_by:
            params.append(f"$orderby={order_by}")
        if top:
            params.append(f"$top={top}")
        if skip:
            params.append(f"$skip={skip}")
        
        query_string = "&".join(params) if params else ""
        endpoint = f"/drives/{drive_id}/root/children" + (f"?{query_string}" if query_string else "")
        
        data = await self.graph_client.get(endpoint)
        
        # Filter for files only
        items = [item for item in data.get("value", []) if "file" in item]
        
        return {
            "items": items,
            "next_link": data.get("@odata.nextLink"),
            "count": len(items)
        }

    @handle_sharepoint_errors("get file by path")
    async def get_file_by_path(
        self, library_id: str, file_path: str
    ) -> Optional[LibraryItem]:
        """Get a file by its path.
        
        Args:
            library_id: Library ID
            file_path: File path
            
        Returns:
            LibraryItem or None
        """
        drive_id = await self.get_library_drive_id(library_id)
        
        try:
            endpoint = f"/drives/{drive_id}/root:/{file_path}"
            data = await self.graph_client.get(endpoint)
            
            if "file" in data:
                return PayloadBuilders.library_item_from_graph_response(data, library_id, drive_id)
            return None
        except Exception as e:
            logger.debug(f"File not found at path {file_path}: {e}")
            return None

    @handle_sharepoint_errors("copy file")
    async def copy_file(
        self,
        source_drive_id: str,
        source_file_id: str,
        destination_drive_id: str,
        destination_folder_path: Optional[str] = None,
        new_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Copy a file to another location.
        
        Args:
            source_drive_id: Source drive ID
            source_file_id: Source file ID
            destination_drive_id: Destination drive ID
            destination_folder_path: Destination folder
            new_name: New file name
            
        Returns:
            Copied file metadata
        """
        endpoint = f"/drives/{source_drive_id}/items/{source_file_id}/copy"
        
        payload = {
            "parentReference": {
                "driveId": destination_drive_id
            }
        }
        
        if destination_folder_path:
            payload["parentReference"]["path"] = f"/drive/root:/{destination_folder_path}"
        
        if new_name:
            payload["name"] = new_name
        
        # Copy is async - returns 202 with monitor URL
        data = await self.graph_client.post(endpoint, payload)
        return data

    @handle_sharepoint_errors("move file")
    async def move_file(
        self,
        drive_id: str,
        file_id: str,
        destination_folder_id: Optional[str] = None,
        new_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Move or rename a file.
        
        Args:
            drive_id: Drive ID
            file_id: File ID
            destination_folder_id: Destination folder ID
            new_name: New name
            
        Returns:
            Updated file metadata
        """
        endpoint = f"/drives/{drive_id}/items/{file_id}"
        
        payload = {}
        
        if destination_folder_id:
            payload["parentReference"] = {"id": destination_folder_id}
        
        if new_name:
            payload["name"] = new_name
        
        return await self.graph_client.patch(endpoint, payload)

    @handle_sharepoint_errors("get file versions")
    async def get_file_versions(
        self, drive_id: str, file_id: str
    ) -> List[Dict[str, Any]]:
        """Get all versions of a file.
        
        Args:
            drive_id: Drive ID
            file_id: File ID
            
        Returns:
            List of file versions
        """
        endpoint = f"/drives/{drive_id}/items/{file_id}/versions"
        data = await self.graph_client.get(endpoint)
        return data.get("value", [])

    @handle_sharepoint_errors("restore file version")
    async def restore_file_version(
        self, drive_id: str, file_id: str, version_id: str
    ) -> Dict[str, Any]:
        """Restore a file version.
        
        Args:
            drive_id: Drive ID
            file_id: File ID
            version_id: Version ID
            
        Returns:
            Restored file metadata
        """
        endpoint = f"/drives/{drive_id}/items/{file_id}/versions/{version_id}/restoreVersion"
        return await self.graph_client.post(endpoint, {})

    @handle_sharepoint_errors("checkout file")
    async def checkout_file(self, drive_id: str, file_id: str) -> bool:
        """Check out a file.
        
        Args:
            drive_id: Drive ID
            file_id: File ID
            
        Returns:
            True if successful
        """
        endpoint = f"/drives/{drive_id}/items/{file_id}/checkout"
        await self.graph_client.post(endpoint, {})
        return True

    @handle_sharepoint_errors("checkin file")
    async def checkin_file(
        self, drive_id: str, file_id: str, comment: Optional[str] = None
    ) -> bool:
        """Check in a file.
        
        Args:
            drive_id: Drive ID
            file_id: File ID
            comment: Check-in comment
            
        Returns:
            True if successful
        """
        endpoint = f"/drives/{drive_id}/items/{file_id}/checkin"
        payload = {"comment": comment or ""}
        await self.graph_client.post(endpoint, payload)
        return True

    @handle_sharepoint_errors("discard file checkout")
    async def discard_file_checkout(self, drive_id: str, file_id: str) -> bool:
        """Discard a file checkout (undo checkout).

        Args:
            drive_id: Drive ID
            file_id: File ID

        Returns:
            True if successful
        """
        endpoint = f"/drives/{drive_id}/items/{file_id}/discardCheckout"
        await self.graph_client.post(endpoint, {})
        return True

    @handle_sharepoint_errors("create file share link")
    async def create_file_share_link(
        self,
        drive_id: str,
        file_id: str,
        link_type: str = "view",
        scope: str = "organization"
    ) -> Dict[str, Any]:
        """Create a sharing link for a file.
        
        Args:
            drive_id: Drive ID
            file_id: File ID
            link_type: Link type ('view', 'edit', 'embed')
            scope: Scope ('anonymous', 'organization')
            
        Returns:
            Share link info
        """
        endpoint = f"/drives/{drive_id}/items/{file_id}/createLink"
        payload = {
            "type": link_type,
            "scope": scope
        }
        return await self.graph_client.post(endpoint, payload)

    @handle_sharepoint_errors("create folder")
    async def create_folder(
        self,
        library_id: str,
        folder_name: str,
        parent_folder_path: Optional[str] = None,
        site_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a folder in a library.
        
        Args:
            library_id: Library ID
            folder_name: Folder name
            parent_folder_path: Parent folder path
            site_id: Optional site ID override
            
        Returns:
            Created folder metadata
        """
        drive_id = await self.get_library_drive_id(library_id, site_id=site_id)
        
        if parent_folder_path:
            endpoint = f"/drives/{drive_id}/root:/{parent_folder_path}:/children"
        else:
            endpoint = f"/drives/{drive_id}/root/children"
        
        payload = {
            "name": folder_name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "fail"
        }
        
        return await self.graph_client.post(endpoint, payload)

    @handle_sharepoint_errors("delete folder")
    async def delete_folder(self, drive_id: str = None, folder_id: str = None, library_id: str = None, folder_path: str = None, site_id: Optional[str] = None) -> bool:
        """Delete a folder.
        
        Args:
            drive_id: Drive ID (legacy)
            folder_id: Folder ID (legacy)
            library_id: Library ID (new)
            folder_path: Folder path (new)
            site_id: Optional site ID
            
        Returns:
            True if successful
        """
        # Handle new signature (library_id + folder_path)
        if library_id and folder_path:
            drive_id = await self.get_library_drive_id(library_id, site_id=site_id)
            endpoint = f"/drives/{drive_id}/root:/{folder_path}"
            return await self.graph_client.delete(endpoint)
        
        # Handle legacy signature (drive_id + folder_id)
        if drive_id and folder_id:
            endpoint = f"/drives/{drive_id}/items/{folder_id}"
            return await self.graph_client.delete(endpoint)
        
        return False

    @handle_sharepoint_errors("get folder contents")
    async def get_folder_contents(
        self,
        drive_id: str,
        folder_id: Optional[str] = None,
        folder_path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get folder contents.
        
        Args:
            drive_id: Drive ID
            folder_id: Folder ID
            folder_path: Folder path
            
        Returns:
            List of folder items
        """
        if folder_id:
            endpoint = f"/drives/{drive_id}/items/{folder_id}/children"
        elif folder_path:
            endpoint = f"/drives/{drive_id}/root:/{folder_path}:/children"
        else:
            endpoint = f"/drives/{drive_id}/root/children"
        
        data = await self.graph_client.get(endpoint)
        return data.get("value", [])

    @handle_sharepoint_errors("batch upload files")
    async def batch_upload_files(
        self, library_id: str, files: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Upload multiple files in batch.
        
        Args:
            library_id: Library ID
            files: List of files with 'name' and 'content'
            
        Returns:
            List of upload results
        """
        results = []
        
        for file_data in files:
            try:
                result = await self.upload_file(
                    library_id,
                    file_data["name"],
                    file_data["content"],
                    file_data.get("metadata")
                )
                results.append({
                    "success": True,
                    "file_name": file_data["name"],
                    "file_id": result.item_id
                })
            except Exception as e:
                results.append({
                    "success": False,
                    "file_name": file_data["name"],
                    "error": str(e)
                })
        
        return results

    @handle_sharepoint_errors("batch delete files")
    async def batch_delete_files(
        self, drive_id: str, file_ids: List[str]
    ) -> Dict[str, Any]:
        """Delete multiple files in batch.
        
        Args:
            drive_id: Drive ID
            file_ids: List of file IDs
            
        Returns:
            Batch results
        """
        results = {
            "deleted": [],
            "failed": []
        }
        
        for file_id in file_ids:
            try:
                success = await self.delete_file(file_id, drive_id)
                if success:
                    results["deleted"].append(file_id)
                else:
                    results["failed"].append({"file_id": file_id, "error": "Unknown error"})
            except Exception as e:
                results["failed"].append({"file_id": file_id, "error": str(e)})
        
        return results
