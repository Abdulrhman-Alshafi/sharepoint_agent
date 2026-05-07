"""Handler for SharePoint permission operations."""

from src.presentation.api.schemas.chat_schemas import ChatResponse
from src.presentation.api.orchestrators.orchestrator_utils import get_logger, error_response

logger = get_logger(__name__)


async def handle_permission_operations(message: str, session_id: str, site_id: str, user_token: str = None, user_login_name: str = "") -> ChatResponse:
    """Handle permission operations (grant, revoke, check, list groups)."""
    from src.presentation.api import get_repository
    from src.infrastructure.external_services.permission_operation_parser import PermissionOperationParserService
    
    try:
        repository = get_repository(user_token=user_token)
        
        # Parse the operation using AI
        operation = await PermissionOperationParserService.parse_permission_operation(message)
        
        if not operation:
            return ChatResponse(
                intent="chat",
                reply="I couldn't understand the permission operation. Please try rephrasing.\n\n"
                       "Examples:\n"
                       "- 'Grant john@company.com edit access to Documents library'\n"
                       "- 'Check what permissions sarah@company.com has'\n"
                       "- 'Show me all SharePoint groups'\n"
                       "- 'Who has access to the HR Documents library?'"
            )
        
        # ── LIST GROUPS OPERATION ───────────────────────────
        if operation.operation == "list_groups":
            groups = await repository.get_site_groups(site_id=site_id)
            
            if not groups:
                return ChatResponse(
                    intent="chat",
                    reply="No SharePoint groups found in this site."
                )
            
            reply = f"👥 Found **{len(groups)}** SharePoint group(s):\n\n"
            for idx, group in enumerate(groups[:20], 1):
                group_name = group.get('displayName') or group.get('Title', 'Unknown')
                description = group.get('description', '')
                reply += f"{idx}. **{group_name}**"
                if description:
                    reply += f" - {description}"
                reply += "\n"
            
            if len(groups) > 20:
                reply += f"\n... and {len(groups) - 20} more groups."
            
            return ChatResponse(
                intent="chat",
                reply=reply,
                data_summary={"group_count": len(groups)}
            )
        
        # ── CREATE GROUP OPERATION ──────────────────────────
        elif operation.operation == "create_group":
            if not operation.group_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify a group name.\n\nExample: 'Create a group called Finance Team'"
                )
            
            from src.domain.entities.security import SharePointGroup
            
            new_group = SharePointGroup(
                name=operation.group_name,
                description=f"SharePoint group: {operation.group_name}"
            )
            
            result = await repository.create_site_group(new_group, site_id=site_id)
            
            return ChatResponse(
                intent="chat",
                reply=f"✅ SharePoint group **{operation.group_name}** created successfully!\n\n"
                       f"🆔 Group ID: {result.get('Id', 'Unknown')}",
                data_summary=result
            )
        
        # ── CHECK PERMISSIONS OPERATION ─────────────────────
        elif operation.operation == "check":
            if not operation.user_email:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify a user email.\n\nExample: 'Check permissions for john@company.com'"
                )
            
            # Get user's effective permissions
            permissions = await repository.get_user_effective_permissions(
                user_login=operation.user_email,
                list_title=operation.resource_name,
                site_id=site_id
            )
            
            if not permissions:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Could not retrieve permissions for **{operation.user_email}**."
                )
            
            # Format permissions
            reply = f"🔐 Permissions for **{operation.user_email}**:\n\n"
            
            # Interpret permission mask (simplified)
            perm_value = permissions.get('High', 0)
            
            if perm_value == 0:
                reply += "❌ No permissions\n"
            else:
                reply += "✅ Has permissions:\n"
                # Add interpretation based on permission bits
                # This is simplified - real implementation would decode the full permission mask
                reply += f"- Permission Level: {perm_value}\n"
            
            return ChatResponse(
                intent="chat",
                reply=reply,
                data_summary=permissions
            )
        
        # ── LIST PERMISSIONS OPERATION ──────────────────────
        elif operation.operation == "list_permissions":
            if not operation.resource_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify a resource name.\n\n"
                           "Example: 'Who has access to the Documents library?'"
                )
            
            # Find the resource (library or list)
            if operation.resource_type == "library":
                resources = await repository.get_all_document_libraries(site_id=site_id)
            else:
                resources = await repository.get_all_lists(site_id=site_id)
            
            matched_resource = next(
                (res for res in resources if operation.resource_name.lower() in res.get('displayName', '').lower()),
                None
            )
            
            if not matched_resource:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ {operation.resource_type.capitalize()} '{operation.resource_name}' not found."
                )
            
            # Fetch role assignments from SharePoint REST API
            try:
                permissions_data = await repository.get_list_permissions(
                    matched_resource.get("id"), site_id=site_id
                )
            except Exception as perm_err:
                logger.warning("Failed to fetch permissions for '%s': %s", operation.resource_name, perm_err)
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Could not retrieve permissions for **{operation.resource_name}**: {perm_err}"
                )

            role_assignments = permissions_data.get("roleAssignments", [])
            if not role_assignments:
                return ChatResponse(
                    intent="chat",
                    reply=f"📋 **{operation.resource_name}** has no explicit role assignments "
                           f"(inheriting from parent site)."
                )

            reply = f"📋 Permissions for **{operation.resource_name}**:\n\n"
            reply += "| Principal | Type | Permission Level(s) |\n"
            reply += "|-----------|------|---------------------|\n"
            for ra in role_assignments[:30]:
                member = ra.get("Member", {})
                principal_name = (
                    member.get("Title") or member.get("LoginName") or member.get("Email", "Unknown")
                )
                principal_type = "Group" if member.get("PrincipalType") == 8 else "User"
                role_defs = ra.get("RoleDefinitionBindings", {}).get("results", [])
                perm_names = ", ".join(
                    rd.get("Name", "") for rd in role_defs if rd.get("Hidden") is not True
                ) or "(hidden)"
                reply += f"| {principal_name} | {principal_type} | {perm_names} |\n"

            if len(role_assignments) > 30:
                reply += f"\n... and {len(role_assignments) - 30} more entries."

            return ChatResponse(
                intent="chat",
                reply=reply,
                data_summary={"resource": operation.resource_name, "assignment_count": len(role_assignments)}
            )
        
        # ── GRANT/REVOKE OPERATIONS ─────────────────────────
        elif operation.operation in ["grant", "revoke"]:
            if not operation.user_email:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify the user's email address.\n\n"
                           "Example: 'Grant john@company.com edit access to Documents'"
                )

            # Resolve the user's numeric principal ID
            try:
                principal_id = await repository.ensure_user_principal_id(operation.user_email, site_id=site_id)
            except Exception as e:
                logger.warning("Could not resolve principal for '%s': %s", operation.user_email, e)
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Could not find user **{operation.user_email}** in this SharePoint site.\n"
                           f"Please ensure the user has been added to the site first."
                )

            # Resolve list/library ID from resource name
            list_id: str | None = None
            if operation.resource_name:
                if operation.resource_type == "library":
                    resources = await repository.get_all_document_libraries(site_id=site_id)
                else:
                    resources = await repository.get_all_lists(site_id=site_id)
                matched = next(
                    (r for r in resources if operation.resource_name.lower() in r.get("displayName", "").lower()),
                    None
                )
                if not matched:
                    return ChatResponse(
                        intent="chat",
                        reply=f"❌ Could not find resource **{operation.resource_name}** in this site."
                    )
                list_id = matched.get("id")

            if operation.operation == "grant":
                if not list_id:
                    return ChatResponse(
                        intent="chat",
                        reply="⚠️ Please specify which list or library to grant access to.\n\n"
                               "Example: 'Grant john@company.com edit access to Documents'"
                    )
                permission_level = operation.permission_level or "read"
                await repository.grant_list_permissions(list_id, str(principal_id), permission_level, site_id=site_id)
                return ChatResponse(
                    intent="chat",
                    reply=f"✅ Granted **{permission_level}** access on **{operation.resource_name}** "
                           f"to **{operation.user_email}**.",
                    data_summary={"principal_id": principal_id, "list_id": list_id, "permission_level": permission_level}
                )

            else:  # revoke
                if not list_id:
                    return ChatResponse(
                        intent="chat",
                        reply="⚠️ Please specify which list or library to revoke access from.\n\n"
                               "Example: 'Revoke john@company.com access from Documents'"
                    )
                await repository.revoke_list_permissions(list_id, str(principal_id), site_id=site_id)
                return ChatResponse(
                    intent="chat",
                    reply=f"✅ Revoked all permissions on **{operation.resource_name}** "
                           f"from **{operation.user_email}**.",
                    data_summary={"principal_id": principal_id, "list_id": list_id}
                )
        
        # ── UNSUPPORTED OPERATION ───────────────────────────
        else:
            return ChatResponse(
                intent="chat",
                reply=f"⚠️ Operation '{operation.operation}' is not yet implemented."
            )
    
    except Exception as e:
        from src.domain.exceptions import PermissionDeniedException, AuthenticationException, DomainException
        from src.presentation.api.orchestrators.orchestrator_utils import (
            domain_error_response, permission_denied_response, auth_expired_response,
        )
        if isinstance(e, PermissionDeniedException):
            return permission_denied_response(session_id=session_id)
        if isinstance(e, AuthenticationException):
            return auth_expired_response(session_id=session_id)
        if isinstance(e, DomainException):
            return domain_error_response(e, intent="chat", session_id=session_id)
        return error_response(logger, "chat", "An error occurred with the permission operation: {error}", e,
                              error_category="internal",
                              recovery_hint="Please try again. If this persists, contact your administrator.")
