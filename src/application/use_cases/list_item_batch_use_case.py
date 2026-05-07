"""Use case for batch and advanced-query operations on SharePoint list items."""

from typing import Dict, Any, List, Optional
from src.domain.repositories import IListRepository
from src.domain.exceptions import SharePointProvisioningException
from src.application.use_cases.list_item_crud_use_case import ListItemCRUDUseCase
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class ListItemBatchUseCase:
    """Handle batch create/update and advanced OData queries on list items."""

    def __init__(self, repository: IListRepository):
        self.repository = repository
        self._crud = ListItemCRUDUseCase(repository)

    async def batch_create_items(
        self,
        list_id: str,
        items_data: List[Dict[str, Any]],
        site_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create multiple items sequentially; implements atomic rollback on failure."""
        created_items: List[Dict[str, Any]] = []
        created_ids: List[str] = []
        
        for item_data in items_data:
            try:
                created_item = await self._crud.create_item(list_id, item_data, site_id)
                created_items.append(created_item)
                created_ids.append(created_item.get("id"))
            except Exception as e:
                logger.error("Batch failure, attempting rollback of %d items", len(created_ids))
                for cid in created_ids:
                    if cid:
                        try:
                            await self._crud.delete_item(list_id, cid, site_id)
                        except Exception:
                            logger.warning("Failed to rollback item %s", cid)
                return {"success": False, "error": str(e)}
                
        return {"success": True, "items": created_items}

    async def batch_update_items(
        self,
        list_id: str,
        updates: List[Dict[str, Any]],
        site_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Update multiple items; each dict must include ``item_id``."""
        updated_items: List[Dict[str, Any]] = []
        for update_data in updates:
            item_id = update_data.pop("item_id", None)
            if not item_id:
                continue
            try:
                updated_item = await self._crud.update_item(list_id, item_id, update_data, site_id)
                updated_items.append(updated_item)
            except Exception as e:
                logger.warning("Failed to update item %s: %s", item_id, e)
        return updated_items

    async def query_items_advanced(
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
        """Query items with advanced OData parameters.

        Returns a dict with ``items`` list and optional ``next_link`` for
        pagination.
        """
        try:
            return await self.repository.query_list_items_advanced(
                list_id=list_id,
                filter_query=filter_query,
                select_fields=select_fields,
                order_by=order_by,
                top=top,
                skip=skip,
                expand=expand,
                site_id=site_id,
            )
        except Exception as e:
            raise SharePointProvisioningException(f"Failed to query list items: {e}")
