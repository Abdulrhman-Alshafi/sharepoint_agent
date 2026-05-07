"""Page repository interface - focused on SharePoint page operations."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from src.domain.entities import SPPage


class IPageRepository(ABC):
    """Repository interface for SharePoint page operations."""

    # ── PAGE CRUD ───────────────────────────────────────────
    
    @abstractmethod
    async def create_page(self, sp_page: SPPage, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a page in SharePoint.
        
        Args:
            sp_page: Page entity to create
            site_id: Optional site ID
            
        Returns:
            Created page metadata
        """
        pass

    @abstractmethod
    async def get_page(self, page_id: str, site_id: Optional[str] = None) -> SPPage:
        """Get a page by ID from SharePoint.
        
        Args:
            page_id: ID of the page
            site_id: Optional site ID
            
        Returns:
            SPPage entity
        """
        pass

    @abstractmethod
    async def get_all_pages(self, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all pages from a site.
        
        Args:
            site_id: Optional site ID
            
        Returns:
            List of page metadata
        """
        pass

    @abstractmethod
    async def get_page_by_name(self, page_name: str, site_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get a page by its name/path.
        
        Args:
            page_name: Name of the page
            site_id: Optional site ID
            
        Returns:
            Page metadata or None if not found
        """
        pass

    @abstractmethod
    async def search_pages(self, query: str, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search pages by title or content.
        
        Args:
            query: Search query string
            site_id: Optional site ID
            
        Returns:
            List of matching pages
        """
        pass

    @abstractmethod
    async def update_page_content(
        self, 
        page_id: str, 
        sp_page: SPPage, 
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update the content/webparts of an existing page.
        
        Args:
            page_id: ID of the page
            sp_page: Updated page entity
            site_id: Optional site ID
            
        Returns:
            Updated page metadata
        """
        pass

    @abstractmethod
    async def delete_page(self, page_id: str, site_id: Optional[str] = None) -> bool:
        """Delete a page from SharePoint.
        
        Args:
            page_id: ID of the page
            site_id: Optional site ID
            
        Returns:
            True if deletion was successful
        """
        pass

    # ── PAGE LIFECYCLE ──────────────────────────────────────
    
    @abstractmethod
    async def publish_page(self, page_id: str, site_id: Optional[str] = None) -> bool:
        """Publish a page.
        
        Args:
            page_id: ID of the page
            site_id: Optional site ID
            
        Returns:
            True if successful
        """
        pass

    @abstractmethod
    async def unpublish_page(self, page_id: str, site_id: Optional[str] = None) -> bool:
        """Unpublish a page (revert to draft).
        
        Args:
            page_id: ID of the page
            site_id: Optional site ID
            
        Returns:
            True if successful
        """
        pass

    @abstractmethod
    async def checkout_page(self, page_id: str, site_id: Optional[str] = None) -> bool:
        """Check out a page for editing.
        
        Args:
            page_id: ID of the page
            site_id: Optional site ID
            
        Returns:
            True if successful
        """
        pass

    @abstractmethod
    async def checkin_page(
        self, 
        page_id: str, 
        comment: Optional[str] = None, 
        site_id: Optional[str] = None
    ) -> bool:
        """Check in a page after editing.
        
        Args:
            page_id: ID of the page
            comment: Optional checkin comment
            site_id: Optional site ID
            
        Returns:
            True if successful
        """
        pass

    @abstractmethod
    async def discard_page_checkout(self, page_id: str, site_id: Optional[str] = None) -> bool:
        """Discard page checkout.
        
        Args:
            page_id: ID of the page
            site_id: Optional site ID
            
        Returns:
            True if successful
        """
        pass

    # ── PAGE VERSIONING ─────────────────────────────────────
    
    @abstractmethod
    async def get_page_versions(self, page_id: str, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all versions of a page.
        
        Args:
            page_id: ID of the page
            site_id: Optional site ID
            
        Returns:
            List of page versions
        """
        pass

    @abstractmethod
    async def restore_page_version(
        self, 
        page_id: str, 
        version_id: str, 
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Restore a specific page version.
        
        Args:
            page_id: ID of the page
            version_id: ID of the version to restore
            site_id: Optional site ID
            
        Returns:
            Restored page metadata
        """
        pass

    # ── PAGE OPERATIONS ─────────────────────────────────────
    
    @abstractmethod
    async def copy_page(
        self, 
        source_page_id: str, 
        new_title: str, 
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Copy a page to create a new one.
        
        Args:
            source_page_id: ID of the source page
            new_title: Title for the new page
            site_id: Optional site ID
            
        Returns:
            Created page metadata
        """
        pass

    @abstractmethod
    async def promote_page_as_news(self, page_id: str, site_id: Optional[str] = None) -> bool:
        """Promote a page as a news post.
        
        Args:
            page_id: ID of the page
            site_id: Optional site ID
            
        Returns:
            True if successful
        """
        pass

    @abstractmethod
    async def create_page_share_link(
        self, 
        page_id: str, 
        link_type: str = "view", 
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a sharing link for a page.
        
        Args:
            page_id: ID of the page
            link_type: Type of link ("view", "edit", etc.)
            site_id: Optional site ID
            
        Returns:
            Share link metadata
        """
        pass
    @abstractmethod
    async def get_page_analytics(self, page_id: str, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Fetch view analytics for a page (views, unique viewers, reactions)."""
        pass

    @abstractmethod
    async def schedule_page_publish(self, page_id: str, scheduled_datetime: str, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Schedule a page to be published at a future ISO 8601 datetime."""
        pass