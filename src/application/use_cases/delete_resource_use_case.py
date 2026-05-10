"""Use case for safely deleting SharePoint resources with impact analysis."""

from typing import Dict, Any, List
from src.domain.entities.preview import DeletionImpact, RiskLevel
from src.domain.entities.core import SPPermissionMask
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class DeleteResourceUseCase:
    """Delete SharePoint resources with safety checks and impact analysis."""
    
    def __init__(self, list_repository=None, site_repository=None, page_repository=None, library_repository=None):
        """Initialize use case with specific repositories."""
        self.list_repository = list_repository
        self.site_repository = site_repository
        self.page_repository = page_repository
        self.library_repository = library_repository
    
    async def execute(self, resource_type: str, site_id: str, resource_id: str, 
                      resource_name: str, confirmed: bool = False,
                      user_email: str = None, user_login_name: str = None) -> Dict[str, Any]:
        """Delete a SharePoint resource with impact analysis.
        
        Args:
            resource_type: Type of resource ("list", "page", "library", "site")
            site_id: SharePoint site ID
            resource_id: Resource ID to delete
            resource_name: Resource name for confirmation
            confirmed: Whether deletion is confirmed
            user_email: Optional email of the user to check permissions against
            
        Returns:
            Dictionary with impact analysis or deletion result
        """
        from src.domain.exceptions import PermissionDeniedException

        # Enforce user permissions — identity is mandatory
        user_identity = user_login_name or user_email
        if not user_identity:
            raise PermissionDeniedException(
                "No user identity provided. Authentication is required to delete resources."
            )
        # Select appropriate repository for permission check
        repo = None
        if resource_type == "site" and self.site_repository:
            repo = self.site_repository
        elif resource_type == "list" and self.list_repository:
            repo = self.list_repository
        elif resource_type == "page" and self.page_repository:
            repo = self.page_repository
        elif resource_type == "library" and self.library_repository:
            repo = self.library_repository

        required_mask = SPPermissionMask.MANAGE_WEB if resource_type == "site" else SPPermissionMask.MANAGE_LISTS
        has_perms = True
        if repo and hasattr(repo, "check_user_permission"):
            has_perms = await repo.check_user_permission(user_identity, required_mask)
        
        if not has_perms:
            raise PermissionDeniedException(
                f"User '{user_identity}' does not have sufficient SharePoint permissions ({required_mask.value}) to delete this resource."
            )

        # Generate impact analysis
        impact = await self._analyze_deletion_impact(resource_type, site_id, resource_id, resource_name)
        
        if not confirmed:
            return {
                "impact": impact,
                "requires_confirmation": True,
                "confirmation_text": f"yes, delete {resource_name.lower()}"
            }
        
        # Execute deletion
        success = await self._execute_deletion(resource_type, site_id, resource_id)
        
        return {
            "impact": impact,
            "success": success,
            "message": f"{resource_type.capitalize()} '{resource_name}' deleted successfully" if success else "Deletion failed"
        }
    
    async def _analyze_deletion_impact(self, resource_type: str, site_id: str, 
                                        resource_id: str, resource_name: str) -> DeletionImpact:
        """Analyze impact of deleting a resource."""
        dependent_resources: List[Dict[str, Any]] = []
        item_count = 0
        last_modified = None
        reversibility = "reversible"
        data_loss_summary = ""
        
        if resource_type == "list" and self.list_repository:
            try:
                list_info = await self.list_repository.get_list(resource_id)
                if list_info:
                    item_count = list_info.item_count
                    data_loss_summary = f"{item_count} list items will be moved to recycle bin"
            except Exception as e:
                logger.warning("Could not fetch list details: %s", e)
        
        elif resource_type == "page":
            data_loss_summary = "Page content will be moved to recycle bin"
        
        elif resource_type == "library":
            data_loss_summary = "All files in library will be moved to recycle bin"
        
        elif resource_type == "site":
            data_loss_summary = "Entire site and all content will be deleted"
        
        # Assess risk
        risk_level = RiskLevel.LOW
        if resource_type == "site":
            risk_level = RiskLevel.HIGH
        elif item_count > 100 or dependent_resources:
            risk_level = RiskLevel.HIGH
        elif item_count > 10:
            risk_level = RiskLevel.MEDIUM
        
        return DeletionImpact(
            target_resource_type=resource_type,
            target_resource_id=resource_id,
            target_resource_name=resource_name,
            dependent_resources=dependent_resources,
            data_loss_summary=data_loss_summary,
            item_count=item_count,
            last_modified=last_modified,
            reversibility=reversibility,
            confirmation_required=True,
            risk_level=risk_level
        )
    
    async def _execute_deletion(self, resource_type: str, site_id: str, resource_id: str) -> bool:
        """Execute the deletion operation."""
        try:
            if resource_type == "site" and self.site_repository:
                return await self.site_repository.delete_site(resource_id)
            elif resource_type == "list" and self.list_repository:
                return await self.list_repository.delete_list(resource_id, site_id)
            elif resource_type == "page" and self.page_repository:
                return await self.page_repository.delete_page(site_id, resource_id)
            elif resource_type == "library" and self.library_repository:
                return await self.library_repository.delete_document_library(resource_id, site_id=site_id)
            else:
                from src.domain.exceptions import SharePointProvisioningException
                raise SharePointProvisioningException(f"Deletion not supported for type: {resource_type}")
        except Exception as e:
            logger.error("Error deleting %s: %s", resource_type, e)
            return False
