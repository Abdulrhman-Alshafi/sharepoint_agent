"""Use case for analyzing SharePoint content to understand purpose and structure."""

from src.domain.entities.conversation import ContentAnalysis
from src.domain.entities.core import SPPermissionMask
from src.domain.exceptions import PermissionDeniedException
from src.infrastructure.services.content_analyzer import ContentAnalyzerService


class AnalyzeContentUseCase:
    """Analyze SharePoint sites, pages, and lists to understand their content."""
    
    def __init__(self, content_analyzer: ContentAnalyzerService, permission_repository=None):
        self.content_analyzer = content_analyzer
        self.permission_repository = permission_repository
    
    async def execute(self, resource_type: str, site_id: str, resource_id: str = None, user_login: str = "") -> ContentAnalysis:
        """Analyze a SharePoint resource."""
        if not user_login:
            raise PermissionDeniedException("No user identity provided. Authentication is required to analyze content.")
        if self.permission_repository:
            has_perms = await self.permission_repository.check_user_permission(user_login, SPPermissionMask.VIEW_LIST_ITEMS)
            if not has_perms:
                raise PermissionDeniedException(f"User '{user_login}' does not have permission to view SharePoint content.")
        
        if resource_type.lower() == "site":
            return await self.content_analyzer.analyze_site(site_id)
        
        elif resource_type.lower() == "page":
            if not resource_id:
                raise ValueError("resource_id required for page analysis")
            return await self.content_analyzer.analyze_page(site_id, resource_id)
        
        elif resource_type.lower() in ["list", "library"]:
            if not resource_id:
                raise ValueError("resource_id required for list/library analysis")
            return await self.content_analyzer.analyze_list(site_id, resource_id)
        
        else:
            raise ValueError(f"Unknown resource type: {resource_type}")
