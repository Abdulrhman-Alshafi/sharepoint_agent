"""Use case for updating existing SharePoint resources."""

from typing import Dict, Any
from src.domain.entities.preview import ProvisioningPreview, ResourceChange, OperationType, RiskLevel
from src.domain.entities.core import SPPermissionMask, SPList, ActionType
from src.domain.value_objects import SPColumn


class UpdateResourceUseCase:
    """Update existing SharePoint resources with preview support."""
    
    def __init__(self, list_repository=None, page_repository=None, library_repository=None, site_repository=None):
        """Initialize use case with specific repositories."""
        self.list_repository = list_repository
        self.page_repository = page_repository
        self.library_repository = library_repository
        self.site_repository = site_repository
    
    async def execute(self, resource_type: str, site_id: str, resource_id: str, 
                      modifications: Dict[str, Any], preview_only: bool = True,
                      user_email: str = None) -> Dict[str, Any]:
        """Update a SharePoint resource.
        
        Args:
            resource_type: Type of resource ("list", "page", "library")
            site_id: SharePoint site ID
            resource_id: Resource ID to update
            modifications: Dictionary of modifications to apply
            preview_only: If True, generate preview without executing
            user_email: Optional email of the user to check permissions against
            
        Returns:
            Dictionary with preview and/or result
        """
        from src.domain.exceptions import PermissionDeniedException

        # Enforce user permissions — identity is mandatory
        if not user_email:
            raise PermissionDeniedException(
                "No user identity provided. Authentication is required to update resources."
            )
        
        # Check permissions using the appropriate repository
        repo = None
        if resource_type == "list" and self.list_repository:
            repo = self.list_repository
        elif resource_type == "page" and self.page_repository:
            repo = self.page_repository
        elif resource_type == "library" and self.library_repository:
            repo = self.library_repository
        elif resource_type == "site" and self.site_repository:
            repo = self.site_repository
            
        if repo and hasattr(repo, "check_user_permission"):
            has_perms = await repo.check_user_permission(user_email, SPPermissionMask.MANAGE_LISTS)
            if not has_perms:
                raise PermissionDeniedException(
                    f"User '{user_email}' does not have sufficient SharePoint permissions (ManageLists) to update this resource."
                )

        # Generate preview
        preview = await self._generate_update_preview(resource_type, site_id, resource_id, modifications)
        
        if preview_only:
            return {
                "preview": preview,
                "requires_confirmation": True
            }
        
        # Execute update
        result = await self._execute_update(resource_type, site_id, resource_id, modifications)
        
        return {
            "preview": preview,
            "result": result,
            "success": result is not None
        }
    
    async def _generate_update_preview(self, resource_type: str, site_id: str, 
                                        resource_id: str, modifications: Dict[str, Any]) -> ProvisioningPreview:
        """Generate preview of update operation."""
        # Fetch current state
        if resource_type == "list":
            sp_list_entity = await self.list_repository.get_list(resource_id, site_id)
            current = {
                "displayName": sp_list_entity.title,
                "description": sp_list_entity.description,
                "columns": [c.name for c in sp_list_entity.columns],
            }
        else:
            current = {}
        
        # Build change description
        change = ResourceChange(
            resource_type=resource_type,
            resource_name=current.get("displayName", current.get("name", "Unknown")),
            change_type="modify",
            before_state=self._extract_state(current),
            after_state=self._merge_state(current, modifications),
            description=self._describe_modifications(modifications)
        )
        
        preview = ProvisioningPreview(
            operation_type=OperationType.UPDATE,
            affected_resources=[change],
            risk_level=RiskLevel.MEDIUM,
            visual_representation=f"**Updating {resource_type}: {change.resource_name}**\n\n{self._format_diff(change)}"
        )
        
        return preview
    
    async def _execute_update(self, resource_type: str, site_id: str,
                               resource_id: str, modifications: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the update operation."""
        if resource_type == "list":
            # IMPORTANT: avoid implicit schema sync on metadata-only updates.
            # Updating name/description should not touch columns.
            metadata_payload: Dict[str, Any] = {}
            if "displayName" in modifications or "title" in modifications:
                metadata_payload["displayName"] = modifications.get("displayName") or modifications.get("title")
            if "description" in modifications:
                metadata_payload["description"] = modifications.get("description")

            if metadata_payload:
                target_site = site_id or self.list_repository.graph_client.site_id
                endpoint = f"/sites/{target_site}/lists/{resource_id}"
                return await self.list_repository.graph_client.patch(endpoint, metadata_payload)

            # Explicit add-column operation.
            add_column = modifications.get("add_column")
            if isinstance(add_column, dict) and add_column.get("name"):
                col_type = add_column.get("type", "text")
                column = SPColumn(name=add_column["name"], type=col_type, required=False)
                return await self.list_repository.add_list_column(resource_id, column, site_id=site_id)

            # Full schema update path (only when explicit columns are supplied).
            raw_columns = modifications.get("columns")
            if raw_columns and isinstance(raw_columns, list):
                columns = [
                    SPColumn(name=c.get("name", c) if isinstance(c, dict) else str(c), type="text", required=False)
                    for c in raw_columns
                ]
            else:
                raise ValueError("No supported list update operation provided.")

            title = modifications.get("title", modifications.get("displayName", ""))
            description = modifications.get("description", "")
            sp_list_entity = SPList(
                title=title or "Updated List",
                description=description,
                columns=columns,
                action=ActionType.UPDATE,
                list_id=resource_id,
            )
            return await self.list_repository.update_list(resource_id, sp_list_entity, site_id=site_id)
        elif resource_type == "page":
            from src.domain.entities import SPPage
            sp_page = SPPage(title=modifications.get("title", modifications.get("displayName", "")), page_id=resource_id)
            return await self.page_repository.update_page_content(resource_id, sp_page, site_id=site_id)
        elif resource_type == "library":
            return await self.library_repository.update_document_library(resource_id, modifications, site_id=site_id)
        elif resource_type == "site":
            return await self.site_repository.update_site(resource_id, modifications)
        else:
            raise ValueError(f"Unsupported resource_type for update: '{resource_type}'.")
    
    def _extract_state(self, resource: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant state from resource."""
        return {
            "title": resource.get("displayName", resource.get("name", "")),
            "description": resource.get("description", ""),
            "columns": len(resource.get("columns", []))
        }
    
    def _merge_state(self, current: Dict[str, Any], modifications: Dict[str, Any]) -> Dict[str, Any]:
        """Merge modifications into current state."""
        merged = self._extract_state(current)
        merged.update(modifications)
        return merged
    
    def _describe_modifications(self, modifications: Dict[str, Any]) -> str:
        """Generate human-readable description of modifications."""
        changes = [f"{key}: {value}" for key, value in modifications.items()]
        return ", ".join(changes)
    
    def _format_diff(self, change: ResourceChange) -> str:
        """Format before/after diff."""
        lines = []
        if change.before_state and change.after_state:
            for key in change.after_state:
                before = change.before_state.get(key, "(none)")
                after = change.after_state.get(key, "(none)")
                if before != after:
                    lines.append(f"  - **{key}**: {before} → {after}")
        return "\n".join(lines) if lines else "No changes"
