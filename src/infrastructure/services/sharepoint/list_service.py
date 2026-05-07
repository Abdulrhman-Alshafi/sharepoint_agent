"""Service for SharePoint List operations."""

import logging
from typing import Dict, Any, List, Optional
from src.domain.entities import SPList
from src.domain.exceptions import SharePointProvisioningException
from src.infrastructure.services.graph_api_client import GraphAPIClient
from src.infrastructure.repositories.utils.payload_builders import PayloadBuilders
from src.infrastructure.repositories.utils.constants import SharePointConstants
from src.infrastructure.repositories.utils.error_handlers import handle_sharepoint_errors
from src.infrastructure.resilience import with_retry

logger = logging.getLogger(__name__)


class ListService:
    """Handles all SharePoint List CRUD operations."""

    @handle_sharepoint_errors("associate content type")
    async def associate_content_type(self, list_id: str, content_type_id: str) -> bool:
        """Associate a content type with a SharePoint list."""
        endpoint = f"/sites/{self.graph_client.site_id}/lists/{list_id}/contentTypes/$ref"
        payload = {
            "@odata.id": f"https://graph.microsoft.com/v1.0/contentTypes/{content_type_id}"
        }
        await self.graph_client.post(endpoint, payload)
        return True

    @handle_sharepoint_errors("remove content type")
    async def remove_content_type(self, list_id: str, content_type_id: str) -> bool:
        """Remove a content type from a SharePoint list."""
        endpoint = f"/sites/{self.graph_client.site_id}/lists/{list_id}/contentTypes/{content_type_id}/$ref"
        await self.graph_client.delete(endpoint)
        return True

    @handle_sharepoint_errors("batch create list items")
    async def batch_create_items(self, list_id: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Batch create items in a SharePoint list."""
        endpoint = f"/sites/{self.graph_client.site_id}/lists/{list_id}/items"
        created = []
        for item in items:
            payload = {"fields": item}
            data = await self.graph_client.post(endpoint, payload)
            created.append(data)
        return created

    @handle_sharepoint_errors("batch update list items")
    async def batch_update_items(self, list_id: str, updates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Batch update items in a SharePoint list. Each update dict must include 'id' and fields to update."""
        endpoint_base = f"/sites/{self.graph_client.site_id}/lists/{list_id}/items"
        updated = []
        for upd in updates:
            item_id = upd.get("id")
            if not item_id:
                continue
            fields = {k: v for k, v in upd.items() if k != "id"}
            endpoint = f"{endpoint_base}/{item_id}/fields"
            data = await self.graph_client.patch(endpoint, fields)
            updated.append(data)
        return updated

    @handle_sharepoint_errors("batch delete list items")
    async def batch_delete_items(self, list_id: str, item_ids: List[str]) -> int:
        """Batch delete items from a SharePoint list. Returns count deleted."""
        endpoint_base = f"/sites/{self.graph_client.site_id}/lists/{list_id}/items"
        deleted_count = 0
        for item_id in item_ids:
            endpoint = f"{endpoint_base}/{item_id}"
            try:
                await self.graph_client.delete(endpoint)
                deleted_count += 1
            except Exception as e:
                logger.warning(f"Failed to delete item {item_id}: {e}")
        return deleted_count

    @handle_sharepoint_errors("add list column")
    async def add_list_column(self, list_id: str, column) -> Dict[str, Any]:
        """Add a column to a SharePoint list."""
        columns_endpoint = f"/sites/{self.graph_client.site_id}/lists/{list_id}/columns"
        col_payload = PayloadBuilders.build_column_payload(column)
        return await self.graph_client.post(columns_endpoint, col_payload)

    @handle_sharepoint_errors("update list column")
    async def update_list_column(self, list_id: str, column_id: str, column_updates: dict) -> Dict[str, Any]:
        """Update a column in a SharePoint list."""
        endpoint = f"/sites/{self.graph_client.site_id}/lists/{list_id}/columns/{column_id}"
        return await self.graph_client.patch(endpoint, column_updates)

    @handle_sharepoint_errors("delete list column")
    async def delete_list_column(self, list_id: str, column_id: str) -> bool:
        """Delete a column from a SharePoint list."""
        endpoint = f"/sites/{self.graph_client.site_id}/lists/{list_id}/columns/{column_id}"
        return await self.graph_client.delete(endpoint)

    def __init__(self, graph_client: GraphAPIClient):
        """Initialize list service.
        
        Args:
            graph_client: Graph API client for making requests
        """
        self.graph_client = graph_client

    @handle_sharepoint_errors("create list")
    async def create_list(self, sp_list: SPList, site_id: str = None) -> Dict[str, Any]:
        """Create a list in SharePoint via Graph API.
        
        Args:
            sp_list: SPList entity to create
            site_id: Optional site ID override.
            
        Returns:
            Created list data including resource_link
        """
        payload = PayloadBuilders.build_list_payload(sp_list)
        target_site = site_id or self.graph_client.site_id
        endpoint = f"/sites/{target_site}/lists"
        
        original_title = sp_list.title
        attempt = 0
        
        while True:
            try:
                data = await self.graph_client.post(endpoint, payload)
                break
            except SharePointProvisioningException as e:
                err_msg = str(e).lower()
                if "status 409" in err_msg or "namealreadyexists" in err_msg or "already exists" in err_msg:
                    attempt += 1
                    new_title = f"{original_title} ({attempt})"
                    logger.info(f"List '{sp_list.title}' already exists. Retrying with name '{new_title}'.")
                    sp_list.title = new_title
                    payload["displayName"] = new_title
                    if "list" in payload and "displayName" in payload["list"]:
                        payload["list"]["displayName"] = new_title
                    continue
                raise
            
        data["resource_link"] = data.get("webUrl", "")
        return data

    @handle_sharepoint_errors("get list")
    async def get_list(self, list_id: str) -> SPList:
        """Get a list by ID from SharePoint.
        
        Args:
            list_id: SharePoint list ID
            
        Returns:
            SPList entity
        """
        endpoint = f"/sites/{self.graph_client.site_id}/lists/{list_id}"
        data = await self.graph_client.get(endpoint)
        
        from src.domain.value_objects import SPColumn
        return SPList(
            title=data.get("displayName", ""),
            description=data.get("description", ""),
            columns=[SPColumn(name="Title", type="text", required=True)],
            list_id=data.get("id", ""),
        )

    @handle_sharepoint_errors("get all lists")
    async def get_all_lists(self, site_id: str = None) -> List[Dict[str, Any]]:
        """Get all lists on the SharePoint site.
        
        Args:
            site_id: Optional site ID override (defaults to configured site)
            
        Returns:
            List of all lists data
        """
        resolved_site_id = site_id or self.graph_client.site_id
        endpoint = f"/sites/{resolved_site_id}/lists"
        
        logger.info(f"DEBUG: Calling Graph API to get all lists for site: {resolved_site_id}")
        data = await self.graph_client.get(endpoint)
        
        lists = data.get("value", [])
        logger.info(f"DEBUG: get_all_lists for site {resolved_site_id} returned {len(lists)} lists.")
        
        if not lists:
            logger.info(f"DEBUG: Raw Graph API response when no lists found: {data}")
            
        return lists

    @with_retry(max_attempts=3, service_name="SharePoint List")
    @handle_sharepoint_errors("get list items")
    async def get_list_items(self, list_id: str) -> List[Dict[str, Any]]:
        """Get all items from a SharePoint list with pagination.
        
        Args:
            list_id: SharePoint list ID
            
        Returns:
            List of all items
        """
        endpoint = (
            f"/sites/{self.graph_client.site_id}/lists/{list_id}/items"
            f"?expand=fields&$top={SharePointConstants.ITEMS_PER_PAGE}"
        )
        all_items = []
        page_count = 0
        
        while endpoint and page_count < SharePointConstants.MAX_PAGES_TO_FETCH:
            data = await self.graph_client.get(endpoint)
            all_items.extend(data.get("value", []))
            
            # Get next page URL if available
            endpoint = data.get("@odata.nextLink", "")
            page_count += 1
            
        return all_items

    @handle_sharepoint_errors("search lists")
    async def search_lists(self, query: str) -> List[Dict[str, Any]]:
        """Search for lists by display name (case-insensitive partial match).
        
        Args:
            query: Search query string
            
        Returns:
            List of matching lists
        """
        all_lists = await self.get_all_lists()
        query_lower = query.lower()
        return [
            lst for lst in all_lists
            if query_lower in lst.get("displayName", "").lower()
        ]

    @handle_sharepoint_errors("update list")
    async def update_list(self, list_id: str, sp_list: SPList, site_id: str = None) -> Dict[str, Any]:
        """Update an existing list in SharePoint (metadata + add/delete columns).
        
        Args:
            list_id: SharePoint list ID
            sp_list: SPList entity with updated data
            site_id: Optional site ID override.
            
        Returns:
            Updated list data
        """
        target_site = site_id or self.graph_client.site_id
        # Update list metadata
        endpoint = f"/sites/{target_site}/lists/{list_id}"
        patch_payload = {
            "displayName": sp_list.title,
            "description": sp_list.description,
        }
        data = await self.graph_client.patch(endpoint, patch_payload)

        # Manage columns (add new, delete removed)
        await self._sync_columns(list_id, sp_list.columns, site_id=target_site)

        data["resource_link"] = data.get("webUrl", "")
        return data

    async def _sync_columns(self, list_id: str, columns: List[Any], site_id: str = None) -> None:
        """Synchronize columns with the list (add new, delete removed).
        
        Args:
            list_id: SharePoint list ID
            columns: List of SPColumn value objects
            site_id: Optional site ID override.
        """
        target_site = site_id or self.graph_client.site_id
        columns_endpoint = f"/sites/{target_site}/lists/{list_id}/columns"
        
        # Fetch existing columns
        _cols_response = await self.graph_client.get(columns_endpoint)
        existing_cols_data = _cols_response.get("value", [])

        all_existing_names = set()
        for ex in existing_cols_data:
            all_existing_names.add(ex.get("name", "").lower())
            all_existing_names.add(ex.get("displayName", "").lower())

        blueprint_names = {col.name.lower() for col in columns}
        
        # Delete columns not in blueprint
        for ex in existing_cols_data:
            name_lower = ex.get("name", "").lower()
            display_name_lower = ex.get("displayName", "").lower()
            
            # Protect built-in and readOnly columns
            if ex.get("readOnly") or name_lower in SharePointConstants.PROTECTED_COLUMNS:
                continue
                
            if name_lower not in blueprint_names and display_name_lower not in blueprint_names:
                delete_endpoint = f"{columns_endpoint}/{ex['id']}"
                try:
                    await self.graph_client.delete(delete_endpoint)
                except Exception as e:
                    logger.warning(f"Failed to delete column {ex.get('name')}: {e}")

        # Add new columns
        for col in columns:
            if col.name.lower() in all_existing_names:
                continue  # Skip existing columns
                
            col_payload = PayloadBuilders.build_column_payload(col)
            try:
                await self.graph_client.post(columns_endpoint, col_payload)
            except Exception as e:
                logger.warning(f"Failed to add column {col.name}: {e}")

    @handle_sharepoint_errors("delete list")
    async def delete_list(self, list_id: str, site_id: str = None) -> bool:
        """Delete a list from SharePoint.
        
        Args:
            list_id: SharePoint list ID
            site_id: Optional site ID. If None, uses the client default.
            
        Returns:
            True if successful
        """
        target_site_id = site_id if site_id else self.graph_client.site_id
        endpoint = f"/sites/{target_site_id}/lists/{list_id}"
        return await self.graph_client.delete(endpoint)

    # ── LIST ITEM OPERATIONS ────────────────────────────────

    @handle_sharepoint_errors("create list item")
    async def create_list_item(self, list_id: str, item_data: Dict[str, Any], site_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a single item in a SharePoint list.
        
        Args:
            list_id: SharePoint list ID
            item_data: Dictionary of field values for the item
            site_id: Optional site ID override
            
        Returns:
            Created item data including ID
        """
        target_site = site_id or self.graph_client.site_id
        endpoint = f"/sites/{target_site}/lists/{list_id}/items"
        payload = {"fields": item_data}
        data = await self.graph_client.post(endpoint, payload)
        return data

    @handle_sharepoint_errors("update list item")
    async def update_list_item(self, list_id: str, item_id: str, item_data: Dict[str, Any], site_id: Optional[str] = None) -> Dict[str, Any]:
        """Update a single item in a SharePoint list.
        
        Args:
            list_id: SharePoint list ID
            item_id: SharePoint item ID
            item_data: Dictionary of field values to update
            site_id: Optional site ID override
            
        Returns:
            Updated item data
        """
        target_site = site_id or self.graph_client.site_id
        endpoint = f"/sites/{target_site}/lists/{list_id}/items/{item_id}/fields"
        data = await self.graph_client.patch(endpoint, item_data)
        return data

    @handle_sharepoint_errors("delete list item")
    async def delete_list_item(self, list_id: str, item_id: str, site_id: Optional[str] = None) -> bool:
        """Delete a single item from a SharePoint list.
        
        Args:
            list_id: SharePoint list ID
            item_id: SharePoint item ID
            site_id: Optional site ID override
            
        Returns:
            True if successful
        """
        target_site = site_id or self.graph_client.site_id
        endpoint = f"/sites/{target_site}/lists/{list_id}/items/{item_id}"
        return await self.graph_client.delete(endpoint)

    @handle_sharepoint_errors("query list items")
    async def query_list_items(self, list_id: str, filter_query: str = None, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Query list items with optional OData filter and pagination support.
        
        Args:
            list_id: SharePoint list ID
            filter_query: Optional OData $filter query string
            site_id: Optional site ID override
            
        Returns:
            List of matching items
        """
        target_site = site_id or self.graph_client.site_id
        base_endpoint = f"/sites/{target_site}/lists/{list_id}/items?expand=fields&$top={SharePointConstants.ITEMS_PER_PAGE}"

        # When filtering, Graph requires this header for non-indexed columns (e.g. Title)
        filter_headers = {"Prefer": "HonorNonIndexedQueriesWarningMayFailRandomly"} if filter_query else None

        if filter_query:
            endpoint = f"{base_endpoint}&$filter={filter_query}"
        else:
            endpoint = base_endpoint
            
        all_items = []
        page_count = 0
        
        while endpoint and page_count < SharePointConstants.MAX_PAGES_TO_FETCH:
            data = await self.graph_client.get(endpoint, extra_headers=filter_headers)
            all_items.extend(data.get("value", []))
            
            # Get next page URL if available
            endpoint = data.get("@odata.nextLink", "")
            page_count += 1
            
        return all_items

    @handle_sharepoint_errors("query list items advanced")
    async def query_list_items_advanced(
        self,
        list_id: str,
        filter_query: Optional[str] = None,
        select_fields: Optional[List[str]] = None,
        order_by: Optional[str] = None,
        top: Optional[int] = None,
        skip: Optional[int] = None,
        expand: Optional[List[str]] = None,
        site_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Query list items with advanced OData parameters."""
        target_site = site_id or self.graph_client.site_id
        params = ["expand=fields"]
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
        if expand and expand != ["fields"]:
            params.append(f"$expand={','.join(expand)}")
        query_string = "&".join(params)
        endpoint = f"/sites/{target_site}/lists/{list_id}/items?{query_string}"
        data = await self.graph_client.get(endpoint)
        return {"items": data.get("value", []), "next_link": data.get("@odata.nextLink"), "count": len(data.get("value", []))}

    @handle_sharepoint_errors("add item attachment")
    async def add_item_attachment(self, list_id: str, item_id: str, file_name: str, file_content: bytes) -> Dict[str, Any]:
        """Add an attachment to a list item."""
        import base64
        endpoint = f"/sites/{self.graph_client.site_id}/lists/{list_id}/items/{item_id}/attachments"
        payload = {"name": file_name, "contentBytes": base64.b64encode(file_content).decode('utf-8')}
        return await self.graph_client.post(endpoint, payload)

    @handle_sharepoint_errors("get item attachments")
    async def get_item_attachments(self, list_id: str, item_id: str) -> List[Dict[str, Any]]:
        """Get all attachments for a list item."""
        endpoint = f"/sites/{self.graph_client.site_id}/lists/{list_id}/items/{item_id}?$expand=fields,attachments"
        data = await self.graph_client.get(endpoint)
        return data.get("attachments", [])

    @handle_sharepoint_errors("delete item attachment")
    async def delete_item_attachment(self, list_id: str, item_id: str, attachment_id: str) -> bool:
        """Delete an attachment from a list item."""
        endpoint = f"/sites/{self.graph_client.site_id}/lists/{list_id}/items/{item_id}/attachments/{attachment_id}"
        return await self.graph_client.delete(endpoint)

    @handle_sharepoint_errors("get list schema")
    async def get_list_schema(self, list_id: str, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Get list schema including columns."""
        target_site = site_id or self.graph_client.site_id
        list_endpoint = f"/sites/{target_site}/lists/{list_id}"
        list_data = await self.graph_client.get(list_endpoint)
        columns_endpoint = f"/sites/{target_site}/lists/{list_id}/columns"
        columns_data = await self.graph_client.get(columns_endpoint)
        return {"list": list_data, "columns": columns_data.get("value", [])}

    @handle_sharepoint_errors("create list view")
    async def create_list_view(self, list_id: str, view_name: str, view_fields: List[str], view_query: Optional[str] = None, is_default: bool = False) -> Dict[str, Any]:
        """Create a custom view for a list."""
        endpoint = f"/sites/{self.graph_client.site_id}/lists/{list_id}/views"
        payload = {"displayName": view_name, "columns": [{"name": field} for field in view_fields]}
        if view_query:
            payload["viewQuery"] = view_query
        return await self.graph_client.post(endpoint, payload)

    @handle_sharepoint_errors("get list views")
    async def get_list_views(self, list_id: str) -> List[Dict[str, Any]]:
        """Get all views for a list."""
        endpoint = f"/sites/{self.graph_client.site_id}/lists/{list_id}/views"
        data = await self.graph_client.get(endpoint)
        return data.get("value", [])

    @handle_sharepoint_errors("delete list view")
    async def delete_list_view(self, list_id: str, view_id: str) -> bool:
        """Delete a custom view from a list."""
        endpoint = f"/sites/{self.graph_client.site_id}/lists/{list_id}/views/{view_id}"
        return await self.graph_client.delete(endpoint)
