"""Group provisioner for SharePoint groups and permissions."""

from typing import List, Dict, Tuple, Any
from src.domain.entities import ProvisioningBlueprint, ActionType
from src.domain.repositories import IPermissionRepository
from src.domain.exceptions import SharePointProvisioningException
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)

# Default SharePoint groups that are automatically created with every site
DEFAULT_SHAREPOINT_GROUPS = {
    "Owners": "Full Control",
    "Members": "Edit",
    "Visitors": "Read",
}


class GroupProvisioner:
    """Handles provisioning of SharePoint groups and permissions.
    
    NOTE: Custom group creation via REST API requires delegated permissions 
    (user context). Since this application uses app-only tokens, we use the
    default SharePoint groups (Owners, Members, Visitors) instead.
    """

    def __init__(self, repository: IPermissionRepository):
        """Initialize group provisioner.
        
        Args:
            repository: Permission repository for group and permission operations
        """
        self.repository = repository

    async def provision(
        self,
        blueprint: ProvisioningBlueprint,
        lib_title_to_id: Dict[str, str]
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Provision group permissions using default SharePoint groups.
        
        IMPORTANT: This application uses app-only authentication which does not
        support creating custom groups via REST API. Instead, we leverage the
        default SharePoint groups (Owners, Members, Visitors) that are 
        automatically created with every site.
        
        Args:
            blueprint: Provisioning blueprint containing groups
            lib_title_to_id: Mapping of library titles to IDs for permission assignment
            
        Returns:
            Tuple of (count of default groups used, list of warnings)
        """
        created_groups = []
        warnings = []
        
        logger.info("[GroupProvisioner] Using default SharePoint groups (Owners/Members/Visitors)")
        logger.info("[GroupProvisioner] Custom group creation skipped (requires delegated permissions)")

        for group in blueprint.groups:
            try:
                if group.action == ActionType.CREATE:
                    logger.info(f"[GroupProvisioner] Processing group: {group.name}")
                    
                    # Map custom group name to default SharePoint group
                    default_group = self._get_default_group(group.name)
                    
                    if not default_group:
                        warnings.append(
                            f"Group '{group.name}' cannot be mapped to default groups. Using 'Members' as fallback."
                        )
                        default_group = "Members"
                    
                    # Assign permissions if target library specified
                    if group.target_library_title:
                        lib_id = lib_title_to_id.get(group.target_library_title)
                        if lib_id:
                            try:
                                logger.info(
                                    f"[GroupProvisioner] Assigning '{default_group}' to library '{group.target_library_title}'"
                                )
                                # Note: Permission assignment typically requires delegated permissions
                                # This may be skipped if using app-only tokens
                                await self.repository.assign_library_permission(
                                    lib_id,
                                    default_group,
                                    group.permission_level.value
                                )
                                created_groups.append({
                                    "name": default_group,
                                    "mapped_from": group.name,
                                    "type": "default_sharepoint_group"
                                })
                            except Exception as e:
                                logger.warning(
                                    f"[GroupProvisioner] Permission assignment for '{default_group}' failed: {str(e)}"
                                )
                                warnings.append(
                                    f"Could not assign '{default_group}' to library '{group.target_library_title}': {str(e)}"
                                )
                        else:
                            logger.warning(f"[GroupProvisioner] Target library '{group.target_library_title}' not found")
                            warnings.append(
                                f"Target library '{group.target_library_title}' not found for group '{group.name}'"
                            )
                    else:
                        # No target library, just note the default group
                        created_groups.append({
                            "name": default_group,
                            "mapped_from": group.name,
                            "type": "default_sharepoint_group"
                        })
                        logger.info(f"[GroupProvisioner] Using default group: {default_group}")
                            
            except Exception as e:
                logger.error(f"[GroupProvisioner] Error processing group '{group.name}': {str(e)}")
                warnings.append(f"Error processing group '{group.name}': {str(e)}")
                continue

        logger.info(f"[GroupProvisioner] Provisioning complete. Default groups used: {len(created_groups)}, Warnings: {len(warnings)}")
        return created_groups, warnings

    @staticmethod
    def _get_default_group(custom_group_name: str) -> str:
        """Map custom group name to default SharePoint group.
        
        Args:
            custom_group_name: Name of custom group from blueprint
            
        Returns:
            Name of corresponding default SharePoint group, or None if no mapping
        """
        name_lower = custom_group_name.lower()
        
        # Map common group names to defaults
        mappings = {
            "owner": "Owners",
            "admin": "Owners",
            "editor": "Members",
            "contributor": "Members",
            "member": "Members",
            "viewer": "Visitors",
            "reader": "Visitors",
            "visitor": "Visitors",
        }
        
        # Check for exact or partial matches
        for key, default_group in mappings.items():
            if key in name_lower:
                return default_group
        
        # Default fallback
        return "Members"
