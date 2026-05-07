"""List repository interface - focused on SharePoint list operations."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from src.domain.entities import SPList, SPView


class IListRepository(ABC):
    """Repository interface for SharePoint list operations."""

    # ── LIST CRUD ───────────────────────────────────────────
    
    @abstractmethod
    async def create_list(self, sp_list: SPList, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a list in SharePoint.
        
        Args:
            sp_list: List entity to create
            site_id: Optional site ID. If None, uses default configured site.
            
        Returns:
            Created list metadata
        """
        pass

    @abstractmethod
    async def get_list(self, list_id: str, site_id: Optional[str] = None) -> SPList:
        """Get a list by ID from SharePoint.
        
        Args:
            list_id: ID of the list
            site_id: Optional site ID
            
        Returns:
            SPList entity
        """
        pass

    @abstractmethod
    async def get_all_lists(self, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all lists on the SharePoint site.
        
        Args:
            site_id: Optional site ID. If None, uses default configured site.
            
        Returns:
            List of list metadata
        """
        pass

    @abstractmethod
    async def search_lists(self, query: str, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search for lists by display name.
        
        Args:
            query: Search query string
            site_id: Optional site ID
            
        Returns:
            List of matching lists
        """
        pass

    @abstractmethod
    async def update_list(self, list_id: str, sp_list: SPList, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Update an existing list in SharePoint.
        
        Args:
            list_id: ID of the list to update
            sp_list: Updated list entity
            site_id: Optional site ID
            
        Returns:
            Updated list metadata
        """
        pass

    @abstractmethod
    async def delete_list(self, list_id: str, site_id: Optional[str] = None) -> bool:
        """Delete a list from SharePoint.
        
        Args:
            list_id: ID of the list to delete
            site_id: Optional site ID
            
        Returns:
            True if deletion was successful
        """
        pass

    # ── LIST ITEMS ──────────────────────────────────────────
    
    @abstractmethod
    async def get_list_items(
        self, 
        list_id: str, 
        site_id: Optional[str] = None,
        filter_query: Optional[str] = None,
        select_fields: Optional[List[str]] = None,
        order_by: Optional[str] = None,
        top: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get all items from a SharePoint list.
        
        Args:
            list_id: ID of the list
            site_id: Optional site ID
            filter_query: Optional OData filter query
            select_fields: Optional fields to select
            order_by: Optional field to order by
            top: Optional maximum number of items to return
            
        Returns:
            List of list items
        """
        pass

    @abstractmethod
    async def create_list_item(
        self,
        list_id: str,
        item_data: Dict[str, Any],
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new item in a SharePoint list.
        
        Args:
            list_id: ID of the list
            item_data: Item field values
            site_id: Optional site ID
            
        Returns:
            Created item metadata
        """
        pass

    @abstractmethod
    async def update_list_item(
        self,
        list_id: str,
        item_id: str,
        item_data: Dict[str, Any],
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update an existing list item.
        
        Args:
            list_id: ID of the list
            item_id: ID of the item
            item_data: Updated field values
            site_id: Optional site ID
            
        Returns:
            Updated item metadata
        """
        pass

    @abstractmethod
    async def delete_list_item(
        self,
        list_id: str,
        item_id: str,
        site_id: Optional[str] = None
    ) -> bool:
        """Delete an item from a list.
        
        Args:
            list_id: ID of the list
            item_id: ID of the item
            site_id: Optional site ID
            
        Returns:
            True if deletion was successful
        """
        pass

    @abstractmethod
    async def get_list_item(
        self,
        list_id: str,
        item_id: str,
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get a specific list item by ID.
        
        Args:
            list_id: ID of the list
            item_id: ID of the item
            site_id: Optional site ID
            
        Returns:
            List item metadata
        """
        pass

    # ── LIST VIEWS ──────────────────────────────────────────
    
    @abstractmethod
    async def create_list_view(
        self,
        list_id: str,
        view: SPView,
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a view for a list.
        
        Args:
            list_id: ID of the list
            view: View entity
            site_id: Optional site ID
            
        Returns:
            Created view metadata
        """
        pass

    @abstractmethod
    async def get_list_views(
        self,
        list_id: str,
        site_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all views for a list.
        
        Args:
            list_id: ID of the list
            site_id: Optional site ID
            
        Returns:
            List of view metadata
        """
        pass

    # ── LIST METADATA ───────────────────────────────────────
    
    @abstractmethod
    async def get_list_columns(
        self,
        list_id: str,
        site_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all columns for a list.
        
        Args:
            list_id: ID of the list
            site_id: Optional site ID
            
        Returns:
            List of column definitions
        """
        pass

    @abstractmethod
    async def add_list_column(
        self,
        list_id: str,
        column_data: Dict[str, Any],
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Add a column to a list.
        
        Args:
            list_id: ID of the list
            column_data: Column definition
            site_id: Optional site ID
            
        Returns:
            Created column metadata
        """
        pass
    @abstractmethod
    async def seed_list_data(
        self,
        list_id: str,
        seed_data: List[Dict[str, Any]],
        site_id: str = None
    ) -> bool:
        """Seed a list with initial data items.
        
        Args:
            list_id: ID of the list to seed
            seed_data: List of item field value dicts
            
        Returns:
            True if seeding was successful
        """
        pass