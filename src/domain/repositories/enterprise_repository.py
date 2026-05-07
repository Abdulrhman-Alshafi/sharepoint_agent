"""Enterprise repository interface - focused on content types, term sets, and views."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from src.domain.entities import ContentType, TermSet, SPView


class IEnterpriseRepository(ABC):
    """Repository interface for SharePoint enterprise architecture operations."""

    # ── CONTENT TYPES ───────────────────────────────────────
    
    @abstractmethod
    async def create_content_type(
        self, 
        content_type: ContentType, 
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a content type.
        
        Args:
            content_type: ContentType entity to create
            site_id: Optional site ID
            
        Returns:
            Created content type metadata
        """
        pass

    @abstractmethod
    async def get_content_types(self, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all content types in a site.
        
        Args:
            site_id: Optional site ID
            
        Returns:
            List of content type metadata
        """
        pass

    @abstractmethod
    async def get_content_type(
        self, 
        content_type_id: str, 
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get a specific content type by ID.
        
        Args:
            content_type_id: ID of the content type
            site_id: Optional site ID
            
        Returns:
            Content type metadata
        """
        pass

    @abstractmethod
    async def update_content_type(
        self,
        content_type_id: str,
        updates: Dict[str, Any],
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update content type properties.
        
        Args:
            content_type_id: ID of the content type
            updates: Properties to update
            site_id: Optional site ID
            
        Returns:
            Updated content type metadata
        """
        pass

    @abstractmethod
    async def delete_content_type(
        self, 
        content_type_id: str, 
        site_id: Optional[str] = None
    ) -> bool:
        """Delete a content type.
        
        Args:
            content_type_id: ID of the content type
            site_id: Optional site ID
            
        Returns:
            True if deletion was successful
        """
        pass

    @abstractmethod
    async def add_content_type_to_list(
        self,
        list_id: str,
        content_type_id: str,
        site_id: Optional[str] = None
    ) -> bool:
        """Associate a content type with a list.
        
        Args:
            list_id: ID of the list
            content_type_id: ID of the content type
            site_id: Optional site ID
            
        Returns:
            True if successful
        """
        pass

    # ── TERM SETS ───────────────────────────────────────────
    
    @abstractmethod
    async def create_term_set(
        self, 
        term_set: TermSet, 
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a term set (managed metadata).
        
        Args:
            term_set: TermSet entity to create
            site_id: Optional site ID
            
        Returns:
            Created term set metadata
        """
        pass

    @abstractmethod
    async def get_term_sets(self, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all term sets.
        
        Args:
            site_id: Optional site ID
            
        Returns:
            List of term set metadata
        """
        pass

    @abstractmethod
    async def get_term_set(
        self, 
        term_set_id: str, 
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get a specific term set by ID.
        
        Args:
            term_set_id: ID of the term set
            site_id: Optional site ID
            
        Returns:
            Term set metadata
        """
        pass

    @abstractmethod
    async def add_term_to_set(
        self,
        term_set_id: str,
        term_label: str,
        parent_term_id: Optional[str] = None,
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Add a term to a term set.
        
        Args:
            term_set_id: ID of the term set
            term_label: Label for the new term
            parent_term_id: Optional parent term ID for hierarchical terms
            site_id: Optional site ID
            
        Returns:
            Created term metadata
        """
        pass

    @abstractmethod
    async def delete_term_set(
        self, 
        term_set_id: str, 
        site_id: Optional[str] = None
    ) -> bool:
        """Delete a term set.
        
        Args:
            term_set_id: ID of the term set
            site_id: Optional site ID
            
        Returns:
            True if deletion was successful
        """
        pass

    # ── VIEWS ───────────────────────────────────────────────
    
    @abstractmethod
    async def create_view(
        self,
        list_id: str,
        view: SPView,
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a view for a list.
        
        Args:
            list_id: ID of the list
            view: SPView entity to create
            site_id: Optional site ID
            
        Returns:
            Created view metadata
        """
        pass

    @abstractmethod
    async def get_views(
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

    @abstractmethod
    async def get_view(
        self,
        list_id: str,
        view_id: str,
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get a specific view by ID.
        
        Args:
            list_id: ID of the list
            view_id: ID of the view
            site_id: Optional site ID
            
        Returns:
            View metadata
        """
        pass

    @abstractmethod
    async def update_view(
        self,
        list_id: str,
        view_id: str,
        updates: Dict[str, Any],
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update view properties.
        
        Args:
            list_id: ID of the list
            view_id: ID of the view
            updates: Properties to update
            site_id: Optional site ID
            
        Returns:
            Updated view metadata
        """
        pass

    @abstractmethod
    async def delete_view(
        self,
        list_id: str,
        view_id: str,
        site_id: Optional[str] = None
    ) -> bool:
        """Delete a view.
        
        Args:
            list_id: ID of the list
            view_id: ID of the view
            site_id: Optional site ID
            
        Returns:
            True if deletion was successful
        """
        pass
