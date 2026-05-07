"""Permission repository interface - focused on SharePoint permissions and groups."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from src.domain.entities import SharePointGroup, PermissionLevel
from src.domain.entities.core import SPPermissionMask


class IPermissionRepository(ABC):
    """Repository interface for SharePoint permission and group operations."""

    # ── GROUPS ──────────────────────────────────────────────
    
    @abstractmethod
    async def create_group(
        self, 
        group: SharePointGroup, 
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a SharePoint group.
        
        Args:
            group: SharePointGroup entity to create
            site_id: Optional site ID
            
        Returns:
            Created group metadata
        """
        pass

    @abstractmethod
    async def get_all_groups(self, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all groups in a site.
        
        Args:
            site_id: Optional site ID
            
        Returns:
            List of group metadata
        """
        pass

    @abstractmethod
    async def get_group(
        self, 
        group_id: str, 
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get a specific group by ID.
        
        Args:
            group_id: ID of the group
            site_id: Optional site ID
            
        Returns:
            Group metadata
        """
        pass

    @abstractmethod
    async def update_group(
        self,
        group_id: str,
        updates: Dict[str, Any],
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update group properties.
        
        Args:
            group_id: ID of the group
            updates: Properties to update
            site_id: Optional site ID
            
        Returns:
            Updated group metadata
        """
        pass

    @abstractmethod
    async def delete_group(
        self, 
        group_id: str, 
        site_id: Optional[str] = None
    ) -> bool:
        """Delete a group.
        
        Args:
            group_id: ID of the group
            site_id: Optional site ID
            
        Returns:
            True if deletion was successful
        """
        pass

    # ── GROUP MEMBERS ───────────────────────────────────────
    
    @abstractmethod
    async def add_user_to_group(
        self,
        group_id: str,
        user_email: str,
        site_id: Optional[str] = None
    ) -> bool:
        """Add a user to a SharePoint group.
        
        Args:
            group_id: ID of the group
            user_email: Email of the user to add
            site_id: Optional site ID
            
        Returns:
            True if successful
        """
        pass

    @abstractmethod
    async def remove_user_from_group(
        self,
        group_id: str,
        user_id: str,
        site_id: Optional[str] = None
    ) -> bool:
        """Remove a user from a group.
        
        Args:
            group_id: ID of the group
            user_id: ID of the user to remove
            site_id: Optional site ID
            
        Returns:
            True if successful
        """
        pass

    @abstractmethod
    async def get_group_members(
        self, 
        group_id: str, 
        site_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all members of a group.
        
        Args:
            group_id: ID of the group
            site_id: Optional site ID
            
        Returns:
            List of user profiles
        """
        pass

    # ── PERMISSIONS ─────────────────────────────────────────
    
    @abstractmethod
    async def get_site_permissions(self, site_id: str) -> Dict[str, Any]:
        """Get site-level permissions.
        
        Args:
            site_id: ID of the site
            
        Returns:
            Permission information
        """
        pass

    @abstractmethod
    async def get_list_permissions(
        self, 
        list_id: str, 
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get list-level permissions.
        
        Args:
            list_id: ID of the list
            site_id: Optional site ID
            
        Returns:
            Permission information
        """
        pass

    @abstractmethod
    async def get_item_permissions(
        self,
        list_id: str,
        item_id: str,
        site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get item-level permissions.
        
        Args:
            list_id: ID of the list
            item_id: ID of the item
            site_id: Optional site ID
            
        Returns:
            Permission information
        """
        pass

    @abstractmethod
    async def grant_list_permissions(
        self,
        list_id: str,
        principal_id: str,
        permission_level: PermissionLevel,
        site_id: Optional[str] = None
    ) -> bool:
        """Grant permissions on a list to a user or group.
        
        Args:
            list_id: ID of the list
            principal_id: ID of the user or group
            permission_level: Permission level to grant
            site_id: Optional site ID
            
        Returns:
            True if successful
        """
        pass

    @abstractmethod
    async def revoke_list_permissions(
        self,
        list_id: str,
        principal_id: str,
        site_id: Optional[str] = None
    ) -> bool:
        """Revoke permissions on a list from a user or group.
        
        Args:
            list_id: ID of the list
            principal_id: ID of the user or group
            site_id: Optional site ID
            
        Returns:
            True if successful
        """
        pass

    @abstractmethod
    async def break_permission_inheritance(
        self,
        list_id: str,
        copy_role_assignments: bool = True,
        site_id: Optional[str] = None
    ) -> bool:
        """Break permission inheritance for a list.
        
        Args:
            list_id: ID of the list
            copy_role_assignments: Whether to copy parent permissions
            site_id: Optional site ID
            
        Returns:
            True if successful
        """
        pass

    @abstractmethod
    async def reset_permission_inheritance(
        self, 
        list_id: str, 
        site_id: Optional[str] = None
    ) -> bool:
        """Reset permission inheritance for a list.
        
        Args:
            list_id: ID of the list
            site_id: Optional site ID
            
        Returns:
            True if successful
        """
        pass

    # ── PERMISSION LEVELS ───────────────────────────────────
    
    @abstractmethod
    async def get_permission_levels(self, site_id: str) -> List[Dict[str, Any]]:
        """Get all available permission levels for a site.
        
        Args:
            site_id: ID of the site
            
        Returns:
            List of permission level definitions
        """
        pass

    @abstractmethod
    async def create_custom_permission_level(
        self,
        site_id: str,
        level_name: str,
        permissions: List[str]
    ) -> Dict[str, Any]:
        """Create a custom permission level.
        
        Args:
            site_id: ID of the site
            level_name: Name for the permission level
            permissions: List of permissions to include
            
        Returns:
            Created permission level metadata
        """
        pass

    @abstractmethod
    async def check_user_permission(
        self,
        user_login: str,
        required_mask: SPPermissionMask,
        list_title: Optional[str] = None,
    ) -> bool:
        """Check whether a user has the required permission mask on a site or list.

        Args:
            user_login: UPN / login name of the user to check.
            required_mask: The ``SPPermissionMask`` the user must hold.
            list_title: Optional list title — if supplied, checks list-level
                permissions; otherwise checks site-level permissions.

        Returns:
            ``True`` when the user holds the required permission.
        """
        pass
