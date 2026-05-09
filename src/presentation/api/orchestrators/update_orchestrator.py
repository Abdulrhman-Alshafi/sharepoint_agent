"""Handler for resource update operations."""

from src.presentation.api.schemas.chat_schemas import ChatResponse
from src.presentation.api.orchestrators.orchestrator_utils import get_logger, error_response
from src.application.services import ProvisioningApplicationService

logger = get_logger(__name__)


async def handle_update_operations(message: str, session_id: str, site_id: str, provisioning_service: ProvisioningApplicationService, user_email: str = None, user_login_name: str = None, user_token: str = None, last_created: tuple = None) -> ChatResponse:
    """Handle resource update requests."""
    from src.presentation.api import get_site_repository, get_list_repository, get_page_repository, get_library_repository, get_permission_repository, get_enterprise_repository
    from src.domain.exceptions import PermissionDeniedException
    from src.application.use_cases.update_resource_use_case import UpdateResourceUseCase
    from src.domain.entities.conversation import ConversationState, GatheringPhase
    
    try:
        site_repository = get_site_repository(user_token=user_token)
        list_repository = get_list_repository(user_token=user_token)
        page_repository = get_page_repository(user_token=user_token)
        library_repository = get_library_repository(user_token=user_token)
        permission_repository = get_permission_repository(user_token=user_token)
        enterprise_repository = get_enterprise_repository(user_token=user_token)
        update_use_case = UpdateResourceUseCase(repository)
        from src.presentation.api import ServiceContainer
        gathering_service = ServiceContainer.get_gathering_service()
        
        import re

        # Simple resource extraction (would be enhanced with better NLP)
        message_lower = message.lower()
        
        # Try to find which resource to update
        resource_type = None
        resource_id = None
        resource_name = None
        modifications = {}
        
        # Always search all lists by display name — catches "update IT Service Requests to X"
        # even when the word "list" is not in the message.
        all_lists = await list_repository.get_all_lists(site_id)
        for lst in all_lists:
            list_name = lst.get("displayName", "")
            if list_name.lower() in message_lower:
                resource_id = lst.get("id")
                resource_name = lst.get("displayName")
                resource_type = "list"
                break

        # Explicit keyword overrides (only when no list name matched)
        if not resource_id:
            if "page" in message_lower:
                resource_type = "page"
            elif "library" in message_lower:
                resource_type = "library"
        
        if not resource_id:
            # Fallback: use last_created context to resolve the resource
            if last_created and last_created[1] in ("list", "library") and last_created[0]:
                _lc_name = last_created[0]
                _lc_site = (last_created[2] if len(last_created) > 2 and last_created[2] else None) or site_id
                for lst in all_lists:
                    _dname = lst.get("displayName", "").lower()
                    if _lc_name.lower() in _dname or _dname in _lc_name.lower():
                        resource_id = lst.get("id")
                        resource_name = lst.get("displayName")
                        resource_type = "list"
                        site_id = _lc_site
                        break
        if not resource_id:
            return ChatResponse(
                intent="update",
                reply="Which resource would you like to update? Please specify the name.\n\nExample: 'Update the Tasks list to add a Priority column'"
            )
        
        # --- Extract modifications ---
        # Pattern: "update/rename/change [X] to [Y]"
        # X can be a column name → column rename; otherwise → resource rename.
        _update_to = re.search(
            r'(?:update|rename|change)\s+(?:the\s+)?["\']?([^"\']+?)["\']?\s+to\s+["\']?([^"\']+?)["\']?\s*$',
            message, re.IGNORECASE
        )
        if _update_to:
            from_name = _update_to.group(1).strip()
            to_name = _update_to.group(2).strip()
            # Check whether from_name is a column on this list
            if resource_id and resource_type == "list":
                try:
                    _cols = await list_repository.get_list_columns(resource_id, site_id=site_id)
                    for _col in _cols:
                        _col_display = _col.get("displayName", "")
                        _col_internal = _col.get("name", "")
                        if _col_display.lower() == from_name.lower() or _col_internal.lower() == from_name.lower():
                            # Column rename — execute directly (low-risk, no preview needed)
                            await list_repository.update_list_column(resource_id, _col["id"], {"displayName": to_name})
                            return ChatResponse(
                                intent="update",
                                reply=f"✅ Column **'{_col_display}'** renamed to **'{to_name}'** on '{resource_name}'.",
                                session_id=session_id,
                            )
                except Exception as _col_err:
                    logger.warning("Could not check columns for rename hint: %s", _col_err)
            # Not a column — rename the resource itself
            modifications["displayName"] = to_name

        elif "add column" in message_lower:
            # Extract column name if possible
            column_match = re.search(r'add (?:a )?(?:column )?(?:called |named )?["\']?(\w+)["\']?', message_lower)
            if column_match:
                column_name = column_match.group(1).title()
                modifications["add_column"] = {"name": column_name, "type": "text"}
        elif "rename" in message_lower:
            # Extract new name
            rename_match = re.search(r'rename (?:to |as )?["\']?([^"\']+)["\']?', message_lower)
            if rename_match:
                modifications["displayName"] = rename_match.group(1).strip()
        
        if not modifications:
            return ChatResponse(
                intent="update",
                reply=f"What changes would you like to make to '{resource_name}'?\n\nI can help you:\n- Add columns\n- Rename the resource\n- Update descriptions\n- Modify settings"
            )
        
        # Generate preview first
        result = await update_use_case.execute(
            resource_type=resource_type,
            site_id=site_id,
            resource_id=resource_id,
            modifications=modifications,
            preview_only=True,
            user_email=user_login_name or user_email
        )
        
        if result.get("requires_confirmation"):
            preview = result["preview"]
            # Store in session for confirmation
            update_state = ConversationState(
                session_id=session_id,
                phase=GatheringPhase.CONFIRMATION,
                original_prompt=message
            )
            update_state.context_memory = {
                "operation": "update",
                "resource_type": resource_type,
                "resource_id": resource_id,
                "resource_name": resource_name,
                "site_id": site_id,
                "modifications": modifications
            }
            gathering_service.conversation_repo.save(update_state)
            
            return ChatResponse(
                intent="update",
                reply=preview.get_summary() + "\n\nReply 'yes' to apply these changes.",
                preview={
                    "operation_type": preview.operation_type.value,
                    "affected_resources": [
                        {
                            "type": change.resource_type,
                            "name": change.resource_name,
                            "change_type": change.change_type,
                            "description": change.description
                        }
                        for change in preview.affected_resources
                    ],
                    "risk_level": preview.risk_level.value,
                    "visual": preview.visual_representation
                },
                preview_type="update",
                session_id=session_id,
                requires_confirmation=True
            )
        
        return ChatResponse(
            intent="update",
            reply="Update completed successfully!",
            session_id=session_id
        )
    
    except PermissionDeniedException:
        from src.presentation.api.orchestrators.orchestrator_utils import permission_denied_response
        return permission_denied_response(session_id=session_id)
    except Exception as e:
        from src.domain.exceptions import AuthenticationException, DomainException
        from src.presentation.api.orchestrators.orchestrator_utils import domain_error_response, auth_expired_response
        if isinstance(e, AuthenticationException):
            return auth_expired_response(session_id=session_id)
        if isinstance(e, DomainException):
            return domain_error_response(e, intent="update", session_id=session_id)
        return error_response(logger, "update", "Sorry, I couldn't update that resource: {error}", e,
                              error_category="internal",
                              recovery_hint="Please try again. If this persists, contact your administrator.")
