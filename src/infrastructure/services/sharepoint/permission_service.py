"""Service for SharePoint Groups and Permissions operations."""

import logging
from typing import Dict, Any, List
from src.domain.entities import SharePointGroup
from src.domain.exceptions import SharePointProvisioningException
from src.infrastructure.services.rest_api_client import RESTAPIClient
from src.infrastructure.repositories.utils.payload_builders import PayloadBuilders
from src.infrastructure.repositories.utils.constants import SharePointConstants
from src.infrastructure.repositories.utils.error_handlers import handle_sharepoint_errors

logger = logging.getLogger(__name__)


class PermissionService:
    """Handles all SharePoint Groups and Permissions operations."""

    _role_def_cache: Dict[str, Any] = {}  # site_url -> {level_name -> role_def_id}

    def __init__(self, rest_client: RESTAPIClient):
        """Initialize permission service.
        
        Args:
            rest_client: REST API client for making requests
        """
        self.rest_client = rest_client

    @handle_sharepoint_errors("get site groups")
    async def get_site_groups(self) -> List[Dict[str, Any]]:
        """Get all SharePoint site groups via REST API.
        
        Returns:
            List of all site groups
        """
        endpoint = "/_api/web/sitegroups"
        data = await self.rest_client.get(endpoint)
        return data.get("d", {}).get("results", [])

    @handle_sharepoint_errors("create site group")
    async def create_site_group(self, group: SharePointGroup) -> Dict[str, Any]:
        """Create a new SharePoint site group via REST API.
        
        Args:
            group: SharePointGroup entity to create
            
        Returns:
            Created group data including group_id
        """
        endpoint = "/_api/web/sitegroups"
        payload = PayloadBuilders.build_group_payload(group)
        
        data = await self.rest_client.post(endpoint, payload)
        result = data.get("d", data)
        result["group_id"] = str(result.get("Id", ""))
        return result

    @handle_sharepoint_errors("assign library permission")
    async def assign_library_permission(
        self,
        library_id: str,
        group_id: str,
        permission_level: str
    ) -> bool:
        """Break inheritance on a document library, then grant the group the given permission.
        
        Steps:
        1. Break role inheritance on the list
        2. Resolve the role definition ID for the requested permission level
        3. Add a role assignment for the group on the list
        
        Args:
            library_id: Document library ID (GUID)
            group_id: SharePoint group ID
            permission_level: Permission level name (e.g., "Read", "Contribute")
            
        Returns:
            True if successful
        """
        site_url = await self.rest_client.get_site_url()
        list_base = f"{site_url}/_api/web/lists(guid'{library_id}')"

        # Step 1: Break permission inheritance
        break_url = f"{list_base}/breakroleinheritance(copyRoleAssignments=false,clearSubscopes=true)"
        try:
            await self.rest_client.post(break_url, {})
        except Exception as e:
            # Non-fatal – the list may already have unique permissions
            logger.debug(f"Failed to break permission inheritance (may already be broken): {e}")

        # Step 2: Look up the role definition by name
        role_def_id = await self._get_role_definition_id(permission_level)
        
        if role_def_id is None:
            raise SharePointProvisioningException(
                f"Permission Level '{permission_level}' not found in SharePoint Role Definitions."
            )

        # Step 2.5: Resolve group_id if it's a generic name like 'Members', 'Owners', 'Visitors'
        resolved_group_id = group_id
        if not str(group_id).isdigit():
            logger.info("Group ID '%s' is not numeric. Attempting to resolve via site groups...", group_id)
            site_groups = await self.get_site_groups()
            for sg in site_groups:
                if sg.get("Title", "").endswith(group_id):
                    resolved_group_id = str(sg.get("Id"))
                    logger.info("Resolved generic group '%s' to Principal ID: %s", group_id, resolved_group_id)
                    break
            
            if resolved_group_id == group_id:
                raise SharePointProvisioningException(
                    f"Could not resolve Principal ID for generic group name: '{group_id}'"
                )

        # Step 3: Assign role
        assign_url = (
            f"{list_base}/roleassignments/addroleassignment"
            f"(principalid={resolved_group_id},roledefid={role_def_id})"
        )
        
        try:
            await self.rest_client.post(assign_url, {})
            return True
        except SharePointProvisioningException as e:
            # If the error carries a success status code it's actually successful
            if getattr(e, 'http_status', 500) in (200, 204):
                return True
            raise

    async def _get_role_definition_id(self, permission_level: str) -> int:
        """Get the role definition ID for a permission level.
        
        Args:
            permission_level: Permission level name
            
        Returns:
            Role definition ID or None if not found
        """
        site_url = await self.rest_client.get_site_url()
        cache_key = site_url
        cached = PermissionService._role_def_cache.get(cache_key)
        if cached is not None:
            result = cached.get(permission_level.lower())
            if result is not None:
                return result

        role_defs_url = f"{site_url}/_api/web/roledefinitions"
        
        try:
            data = await self.rest_client.get(role_defs_url)
            results = data.get("d", {}).get("results", [])

            # Build and cache lookup map for this site
            name_to_id: Dict[str, Any] = {rd.get("Name", "").lower(): rd.get("Id") for rd in results}
            PermissionService._role_def_cache[cache_key] = name_to_id

            # Direct match
            if permission_level.lower() in name_to_id:
                return name_to_id[permission_level.lower()]
            
            # Fallback mappings for common names
            lookup_map = SharePointConstants.PERMISSION_LEVELS
            mapped_level = lookup_map.get(permission_level.lower())
            
            if mapped_level and mapped_level.lower() in name_to_id:
                return name_to_id[mapped_level.lower()]
            
            return None
        except Exception as e:
            logger.warning(f"Failed to get role definition ID: {e}")
            return None

    @handle_sharepoint_errors("get user effective permissions")
    async def get_user_effective_permissions(self, user_login: str, list_title: str = None) -> Dict[str, int]:
        """Query SharePoint for a user's exact permissions using their login name.
        
        Args:
            user_login: The user's login name (e.g., 'user@domain.com' or 'i:0#.f|membership|user@domain.com')
            list_title: Optional title of the list to check permissions against. If None, checks web permissions.
            
        Returns:
            Dictionary with 'High' and 'Low' integer bitmasks
        """
        import urllib.parse
        
        # Ensure correct prefix for login name
        if not user_login.startswith("i:0#.f|membership|"):
            user_login = f"i:0#.f|membership|{user_login}"
            
        encoded_login = urllib.parse.quote(user_login)
        
        if list_title:
            encoded_list = urllib.parse.quote(list_title)
            endpoint = f"/_api/web/lists/getByTitle('{encoded_list}')/getUserEffectivePermissions(@u)?@u='{encoded_login}'"
        else:
            endpoint = f"/_api/web/getUserEffectivePermissions(@u)?@u='{encoded_login}'"
            
        try:
            data = await self.rest_client.get(endpoint)
            perms = data.get("d", {}).get("GetUserEffectivePermissions", {})
            return {
                "High": int(perms.get("High", 0)),
                "Low": int(perms.get("Low", 0))
            }
        except Exception as e:
            raise SharePointProvisioningException(f"Failed to resolve effective permissions for {user_login}: {str(e)}")

    async def check_user_permission(self, user_login: str, required_mask: str, list_title: str = None) -> bool:
        """Evaluate if a user possesses a specific permission mask.
        
        Args:
            user_login: The user's login name
            required_mask: SPPermissionMask string value
            list_title: Optional list title to scope the check
            
        Returns:
            True if user has permission, False otherwise
        """
        from src.domain.entities.core import SPPermissionMask
        
        perms = await self.get_user_effective_permissions(user_login, list_title)
        
        # SharePoint BasePermissions enum mapping (Low mask values)
        # 0x0000000000000001 = ViewListItems
        # 0x0000000000000002 = AddListItems
        # 0x0000000000000004 = EditListItems
        # 0x0000000000000008 = DeleteListItems
        # 0x0000000000000800 = ManageLists
        # 0x0000000040000000 = ManageWeb
        # 0x7FFFFFFFFFFFFFFF = FullMask
        
        mask_values = {
            SPPermissionMask.VIEW_LIST_ITEMS: 0x0000000000000001,
            SPPermissionMask.ADD_LIST_ITEMS: 0x0000000000000002,
            SPPermissionMask.EDIT_LIST_ITEMS: 0x0000000000000004,
            SPPermissionMask.DELETE_LIST_ITEMS: 0x0000000000000008,
            SPPermissionMask.MANAGE_LISTS: 0x0000000000000800,
            SPPermissionMask.MANAGE_WEB: 0x0000000040000000,
        }
        
        # Full control check
        if perms["High"] == 2147483647 and perms["Low"] == 4294967295:
             return True
             
        # ManageWeb is often found in High for some interpretations but standard SP says 0x40000000 Low
        # Actually ManageWeb is 0x40000000 (Low). ManagePermissions is 0x02000000 (Low)
        
        target_value = mask_values.get(required_mask)
        if not target_value:
            return False
            
        # Bitwise AND check against Low mask
        return (perms["Low"] & target_value) == target_value

    # ── GROUP MANAGEMENT ─────────────────────────────────────

    @handle_sharepoint_errors("get group")
    async def get_group(self, group_id: str) -> Dict[str, Any]:
        """Get a specific SharePoint group by ID."""
        data = await self.rest_client.get(f"/_api/web/sitegroups/getbyid({group_id})")
        return data.get("d", data)

    @handle_sharepoint_errors("update group")
    async def update_group(self, group_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update SharePoint group properties using REST MERGE."""
        site_url = await self.rest_client.get_site_url()
        url = f"{site_url}/_api/web/sitegroups/getbyid({group_id})"
        headers = await self.rest_client.auth_service.get_rest_headers(self.rest_client.site_id)
        merge_headers = {
            **headers,
            "X-HTTP-Method": "MERGE",
            "IF-MATCH": "*",
        }
        payload = {"__metadata": {"type": "SP.Group"}, **updates}
        response = await self.rest_client.http.post(url, headers=merge_headers, json=payload)
        if not response.is_success and response.status_code not in (200, 204):
            raise SharePointProvisioningException(
                f"update_group failed: {response.status_code} {response.text}"
            )
        return {"group_id": str(group_id), **updates}

    @handle_sharepoint_errors("delete group")
    async def delete_group(self, group_id: str) -> bool:
        """Remove a SharePoint group by ID."""
        await self.rest_client.post(f"/_api/web/sitegroups/removebyid({group_id})", {})
        return True

    @handle_sharepoint_errors("add user to group")
    async def add_user_to_group(self, group_id: str, user_email: str) -> bool:
        """Add a user to a SharePoint group by email."""
        if not user_email.startswith("i:0#.f|membership|"):
            login_name = f"i:0#.f|membership|{user_email}"
        else:
            login_name = user_email
        endpoint = f"/_api/web/sitegroups/getbyid({group_id})/users"
        payload = {"__metadata": {"type": "SP.User"}, "LoginName": login_name}
        await self.rest_client.post(endpoint, payload)
        return True

    @handle_sharepoint_errors("remove user from group")
    async def remove_user_from_group(self, group_id: str, user_id: str) -> bool:
        """Remove a user from a SharePoint group by user ID."""
        await self.rest_client.post(
            f"/_api/web/sitegroups/getbyid({group_id})/users/removebyid({user_id})", {}
        )
        return True

    @handle_sharepoint_errors("get group members")
    async def get_group_members(self, group_id: str) -> List[Dict[str, Any]]:
        """Get all members of a SharePoint group."""
        data = await self.rest_client.get(f"/_api/web/sitegroups/getbyid({group_id})/users")
        return data.get("d", {}).get("results", [])

    # ── LIST / ITEM PERMISSIONS ───────────────────────────────

    @handle_sharepoint_errors("get list permissions")
    async def get_list_permissions(self, list_id: str) -> Dict[str, Any]:
        """Get all role assignments for a list."""
        import urllib.parse
        endpoint = (
            f"/_api/web/lists(guid'{list_id}')/roleassignments"
            f"?$expand=Member,RoleDefinitionBindings"
        )
        data = await self.rest_client.get(endpoint)
        return {"roleAssignments": data.get("d", {}).get("results", [])}

    @handle_sharepoint_errors("get item permissions")
    async def get_item_permissions(self, list_id: str, item_id: str) -> Dict[str, Any]:
        """Get all role assignments for a specific list item."""
        endpoint = (
            f"/_api/web/lists(guid'{list_id}')/items({item_id})/roleassignments"
            f"?$expand=Member,RoleDefinitionBindings"
        )
        data = await self.rest_client.get(endpoint)
        return {"roleAssignments": data.get("d", {}).get("results", [])}

    @handle_sharepoint_errors("grant list permissions")
    async def grant_list_permissions(
        self, list_id: str, principal_id: str, permission_level: str
    ) -> bool:
        """Break inheritance on a list then grant a role to a principal."""
        site_url = await self.rest_client.get_site_url()
        list_base = f"{site_url}/_api/web/lists(guid'{list_id}')"
        # Break inheritance (ignore failure if already broken)
        try:
            await self.rest_client.post(
                f"{list_base}/breakroleinheritance(copyRoleAssignments=false,clearSubscopes=true)", {}
            )
        except Exception as e:
            logger.debug("break inheritance (may already be broken): %s", e)
        role_def_id = await self._get_role_definition_id(permission_level)
        if role_def_id is None:
            raise SharePointProvisioningException(
                f"Permission level '{permission_level}' not found."
            )
        assign_url = (
            f"{list_base}/roleassignments/addroleassignment"
            f"(principalid={principal_id},roledefid={role_def_id})"
        )
        try:
            await self.rest_client.post(assign_url, {})
        except SharePointProvisioningException as e:

            err_str = str(e)
            if "failed: 200" in err_str or "failed: 204" in err_str:
                return True
            raise
        return True

    @handle_sharepoint_errors("revoke list permissions")
    async def revoke_list_permissions(self, list_id: str, principal_id: str) -> bool:
        """Revoke all role assignments for a principal from a list."""
        site_url = await self.rest_client.get_site_url()
        list_base = f"{site_url}/_api/web/lists(guid'{list_id}')"
        # First fetch assigned role definitions for this principal
        data = await self.rest_client.get(
            f"{list_base}/roleassignments/getbyprincipalid({principal_id})"
            f"?$expand=RoleDefinitionBindings"
        )
        role_defs = data.get("d", {}).get("RoleDefinitionBindings", {}).get("results", [])
        for rd in role_defs:
            role_def_id = rd.get("Id")
            if role_def_id:
                try:
                    await self.rest_client.post(
                        f"{list_base}/roleassignments/removeroleassignment"
                        f"(principalid={principal_id},roledefid={role_def_id})",
                        {},
                    )
                except Exception as e:
                    logger.warning("Failed to remove role assignment: %s", e)
        return True

    @handle_sharepoint_errors("break permission inheritance")
    async def break_permission_inheritance(
        self, list_id: str, copy_role_assignments: bool = True
    ) -> bool:
        """Break permission inheritance for a list."""
        copy = "true" if copy_role_assignments else "false"
        site_url = await self.rest_client.get_site_url()
        url = (
            f"{site_url}/_api/web/lists(guid'{list_id}')"
            f"/breakroleinheritance(copyRoleAssignments={copy},clearSubscopes=true)"
        )
        await self.rest_client.post(url, {})
        return True

    @handle_sharepoint_errors("reset permission inheritance")
    async def reset_permission_inheritance(self, list_id: str) -> bool:
        """Reset permission inheritance for a list (re-inherit from parent)."""
        site_url = await self.rest_client.get_site_url()
        url = f"{site_url}/_api/web/lists(guid'{list_id}')/resetroleinheritance"
        await self.rest_client.post(url, {})
        return True

    @handle_sharepoint_errors("get permission levels")
    async def get_permission_levels(self) -> List[Dict[str, Any]]:
        """Return all role definitions (permission levels) for the site."""
        data = await self.rest_client.get("/_api/web/roledefinitions")
        return data.get("d", {}).get("results", [])

    @handle_sharepoint_errors("ensure user principal")
    async def ensure_user_principal_id(self, user_email: str) -> int:
        """Ensure a user exists in the site user collection and return their numeric principal ID.

        Uses the SharePoint REST ensureuser endpoint which adds the user if not already
        present and always returns the user record with their site-scoped numeric Id.

        Args:
            user_email: Email address of the user to resolve.

        Returns:
            Numeric SharePoint principal ID for the user.
        """
        login_name = user_email if user_email.startswith("i:0#") else f"i:0#.f|membership|{user_email}"
        payload = {"logonName": login_name}
        data = await self.rest_client.post("/_api/web/ensureuser", payload)
        principal_id = data.get("d", data).get("Id")
        if principal_id is None:
            raise ValueError(f"Could not resolve principal ID for user '{user_email}'.")
        return int(principal_id)
