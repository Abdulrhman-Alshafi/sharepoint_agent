"""Use case for generating previews of provisioning operations before execution."""

import logging
from typing import List
from src.domain.entities import ProvisioningBlueprint, ActionType

logger = logging.getLogger(__name__)
from src.domain.entities.preview import (
    ProvisioningPreview,
    ResourceChange,
    OperationType,
    RiskLevel
)
from src.domain.repositories import IListRepository


class GeneratePreviewUseCase:
    """Generate preview of what will be created/updated/deleted."""
    
    def __init__(self, repository: IListRepository):
        """Initialize use case.
        
        Args:
            repository: SharePoint repository for checking existing resources
        """
        self.repository = repository
    
    async def execute(self, blueprint: ProvisioningBlueprint, site_id: str, user_login: str = "") -> ProvisioningPreview:
        """Generate preview from provisioning blueprint."""
        from src.domain.entities.core import SPPermissionMask
        from src.domain.exceptions import PermissionDeniedException
        if not user_login:
            raise PermissionDeniedException("No user identity provided. Authentication is required to generate a provisioning preview.")
        if hasattr(self.repository, 'check_user_permission'):
            has_perms = await self.repository.check_user_permission(user_login, SPPermissionMask.MANAGE_WEB)
            if not has_perms:
                raise PermissionDeniedException(f"User '{user_login}' does not have sufficient SharePoint permissions (ManageWeb) to preview provisioning operations.")
        # Determine overall operation type
        operation_type = self._determine_operation_type(blueprint)
        
        # Create preview
        preview = ProvisioningPreview(
            operation_type=operation_type,
            affected_resources=[],
            warnings=[],
            risk_level=RiskLevel.LOW
        )
        
        # Analyze lists
        for sp_list in blueprint.lists:
            change = await self._analyze_list_change(sp_list, site_id)
            preview.add_change(change)
        
        # Analyze pages
        for sp_page in blueprint.pages:
            change = await self._analyze_page_change(sp_page, site_id)
            preview.add_change(change)
        
        # Analyze libraries
        for library in blueprint.document_libraries:
            change = await self._analyze_library_change(library, site_id)
            preview.add_change(change)
        
        # Analyze groups
        for group in blueprint.groups:
            change = await self._analyze_group_change(group, site_id)
            preview.add_change(change)
        
        # Generate visual representation
        preview.visual_representation = self._generate_visual_representation(preview.affected_resources)
        
        # Assess risk level
        preview.risk_level = self._assess_risk_level(preview.affected_resources)
        
        # Estimate duration
        preview.estimated_duration_seconds = self._estimate_duration(preview.affected_resources)
        
        return preview
    
    def _determine_operation_type(self, blueprint: ProvisioningBlueprint) -> OperationType:
        """Determine the primary operation type from blueprint.
        
        Args:
            blueprint: Provisioning blueprint
            
        Returns:
            OperationType
        """
        all_resources = blueprint.lists + blueprint.pages + blueprint.document_libraries + blueprint.groups
        
        if not all_resources:
            return OperationType.CREATE
        
        # Check for DELETE actions
        delete_count = sum(1 for r in all_resources if r.action == ActionType.DELETE)
        update_count = sum(1 for r in all_resources if r.action == ActionType.UPDATE)
        create_count = sum(1 for r in all_resources if r.action == ActionType.CREATE)
        
        if delete_count > 0:
            return OperationType.DELETE
        elif update_count > create_count:
            return OperationType.UPDATE
        else:
            return OperationType.CREATE
    
    async def _analyze_list_change(self, sp_list, site_id: str) -> ResourceChange:
        """Analyze list change.
        
        Args:
            sp_list: SPList entity
            site_id: Site ID
            
        Returns:
            ResourceChange describing the list change
        """
        change_type = "add" if sp_list.action == ActionType.CREATE else \
                      "modify" if sp_list.action == ActionType.UPDATE else "remove"
        
        before_state = None
        after_state = {
            "title": sp_list.title,
            "columns": [{"name": col.name, "type": col.type} for col in sp_list.columns],
            "column_count": len(sp_list.columns)
        }
        
        # If UPDATE, get current state
        if sp_list.action == ActionType.UPDATE and sp_list.list_id:
            try:
                existing = await self.repository.get_list(sp_list.list_id, site_id)
                if existing:
                    before_state = {
                        "title": existing.title,
                        "column_count": len(existing.columns)
                    }
            except Exception as e:
                logger.warning("Could not fetch existing list state for preview diff (list_id=%s): %s", sp_list.list_id, e)
        
        # Generate description
        if sp_list.action == ActionType.CREATE:
            description = f"{len(sp_list.columns)} columns"
            if sp_list.seed_data:
                description += f", {len(sp_list.seed_data)} sample items"
        elif sp_list.action == ActionType.UPDATE:
            if before_state:
                col_diff = after_state["column_count"] - before_state["column_count"]
                if col_diff > 0:
                    description = f"Adding {col_diff} new column(s)"
                elif col_diff < 0:
                    description = f"Removing {abs(col_diff)} column(s)"
                else:
                    description = "Modifying columns"
            else:
                description = "Will be updated"
        else:
            description = "Will be deleted"
        
        return ResourceChange(
            resource_type="list",
            resource_name=sp_list.title,
            change_type=change_type,
            before_state=before_state,
            after_state=after_state if sp_list.action != ActionType.DELETE else None,
            description=description
        )
    
    async def _analyze_page_change(self, sp_page, site_id: str) -> ResourceChange:
        """Analyze page change.
        
        Args:
            sp_page: SPPage entity
            site_id: Site ID
            
        Returns:
            ResourceChange describing the page change
        """
        change_type = "add" if sp_page.action == ActionType.CREATE else \
                      "modify" if sp_page.action == ActionType.UPDATE else "remove"
        
        after_state = {
            "title": sp_page.title,
            "web_parts": [{"type": wp.type} for wp in sp_page.webparts],
            "web_part_count": len(sp_page.webparts)
        }
        
        description = f"{len(sp_page.webparts)} web part(s)"
        
        return ResourceChange(
            resource_type="page",
            resource_name=sp_page.title,
            change_type=change_type,
            before_state=None,
            after_state=after_state if sp_page.action != ActionType.DELETE else None,
            description=description
        )
    
    async def _analyze_library_change(self, library, site_id: str) -> ResourceChange:
        """Analyze library change.
        
        Args:
            library: DocumentLibrary entity
            site_id: Site ID
            
        Returns:
            ResourceChange describing the library change
        """
        change_type = "add" if library.action == ActionType.CREATE else \
                      "modify" if library.action == ActionType.UPDATE else "remove"
        
        after_state = {
            "title": library.title,
            "description": library.description
        }
        
        return ResourceChange(
            resource_type="library",
            resource_name=library.title,
            change_type=change_type,
            before_state=None,
            after_state=after_state if library.action != ActionType.DELETE else None,
            description=library.description or "Document library"
        )
    
    async def _analyze_group_change(self, group, site_id: str) -> ResourceChange:
        """Analyze group change.
        
        Args:
            group: SharePointGroup entity
            site_id: Site ID
            
        Returns:
            ResourceChange describing the group change
        """
        change_type = "add" if group.action == ActionType.CREATE else "remove"
        
        after_state = {
            "name": group.name,
            "permission_level": group.permission_level.value
        }
        
        description = f"{group.permission_level.value} permissions"
        
        return ResourceChange(
            resource_type="group",
            resource_name=group.name,
            change_type=change_type,
            before_state=None,
            after_state=after_state if group.action != ActionType.DELETE else None,
            description=description
        )
    
    def _generate_visual_representation(self, changes: List[ResourceChange]) -> str:
        """Generate visual markdown representation of changes.
        
        Args:
            changes: List of resource changes
            
        Returns:
            Markdown formatted visual representation
        """
        lines = []
        
        # Group by resource type
        lists = [c for c in changes if c.resource_type == "list"]
        pages = [c for c in changes if c.resource_type == "page"]
        libraries = [c for c in changes if c.resource_type == "library"]
        groups = [c for c in changes if c.resource_type == "group"]
        
        if lists:
            lines.append(f"\n**📋 Lists ({len(lists)}):**")
            for change in lists:
                icon = "✅" if change.change_type == "add" else "❌" if change.change_type == "remove" else "✏️"
                lines.append(f"  {icon} {change.resource_name}")
                if change.description:
                    lines.append(f"     → {change.description}")
        
        if pages:
            lines.append(f"\n**📄 Pages ({len(pages)}):**")
            for change in pages:
                icon = "✅" if change.change_type == "add" else "❌" if change.change_type == "remove" else "✏️"
                lines.append(f"  {icon} {change.resource_name}")
                if change.description:
                    lines.append(f"     → {change.description}")
        
        if libraries:
            lines.append(f"\n**📁 Libraries ({len(libraries)}):**")
            for change in libraries:
                icon = "✅" if change.change_type == "add" else "❌" if change.change_type == "remove" else "✏️"
                lines.append(f"  {icon} {change.resource_name}")
                if change.description:
                    lines.append(f"     → {change.description}")
        
        if groups:
            lines.append(f"\n**👥 Groups ({len(groups)}):**")
            for change in groups:
                icon = "✅" if change.change_type == "add" else "❌" if change.change_type == "remove" else "✏️"
                lines.append(f"  {icon} {change.resource_name}")
                if change.description:
                    lines.append(f"     → {change.description}")
        
        return "\n".join(lines)
    
    def _assess_risk_level(self, changes: List[ResourceChange]) -> RiskLevel:
        """Assess overall risk level of changes.
        
        Args:
            changes: List of resource changes
            
        Returns:
            RiskLevel assessment
        """
        # Check for deletions
        deletions = [c for c in changes if c.change_type == "remove"]
        if deletions:
            return RiskLevel.HIGH
        
        # Check for updates
        updates = [c for c in changes if c.change_type == "modify"]
        if updates:
            return RiskLevel.MEDIUM
        
        # Only creates
        return RiskLevel.LOW
    
    def _estimate_duration(self, changes: List[ResourceChange]) -> int:
        """Estimate provisioning duration in seconds.
        
        Args:
            changes: List of resource changes
            
        Returns:
            Estimated duration in seconds
        """
        # Simple estimation: 10 seconds per resource + 5 seconds base
        return 5 + (len(changes) * 10)
