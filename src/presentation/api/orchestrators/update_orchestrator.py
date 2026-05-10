"""Handler for resource update operations."""

import re

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
    from src.infrastructure.external_services.site_resolver import SiteResolver
    from src.domain.value_objects import SPColumn
    
    try:
        message_lower = message.lower()
        message_compact = message_lower.replace(" ", "")

        def _is_library_entry(entry: dict) -> bool:
            template = str((entry.get("list") or {}).get("template", "")).lower()
            return template in {"documentlibrary", "101"}

        def _normalize(value: str) -> str:
            return (value or "").lower().replace(" ", "")

        def _is_column_match(column_data: dict, raw_name: str) -> bool:
            wanted = _normalize(raw_name)
            return wanted in {
                _normalize(column_data.get("displayName", "")),
                _normalize(column_data.get("name", "")),
            }

        # Start from context site, preferring the last-created resource site when present.
        _update_site_id = (last_created[2] if (last_created and len(last_created) > 2 and last_created[2]) else None) or site_id

        # Explicit site mentions override context site (for cross-site updates).
        try:
            _site_repo_for_resolution = get_site_repository(user_token=user_token)
            _explicit_site = SiteResolver.extract_site_mention(message)
            if _explicit_site:
                _all_sites = await _site_repo_for_resolution.get_all_sites()
                _resolved = SiteResolver.resolve_site_name(_explicit_site, _all_sites)
                if _resolved and _resolved[0]:
                    _update_site_id = _resolved[0]
                    logger.info(
                        "Update operation site override: '%s' -> %s (ID: %s)",
                        _explicit_site,
                        _resolved[1],
                        _update_site_id,
                    )
        except Exception:
            # Non-fatal: keep context/default site.
            pass

        site_repository = get_site_repository(user_token=user_token, site_id=_update_site_id)
        list_repository = get_list_repository(user_token=user_token, site_id=_update_site_id)
        page_repository = get_page_repository(user_token=user_token, site_id=_update_site_id)
        library_repository = get_library_repository(user_token=user_token, site_id=_update_site_id)
        permission_repository = get_permission_repository(user_token=user_token, site_id=_update_site_id)
        enterprise_repository = get_enterprise_repository(user_token=user_token, site_id=_update_site_id)
        update_use_case = UpdateResourceUseCase(
            list_repository=list_repository,
            page_repository=page_repository,
            library_repository=library_repository,
            site_repository=site_repository,
        )
        from src.presentation.api import ServiceContainer
        gathering_service = ServiceContainer.get_gathering_service()
        
        # Try to find which resource to update
        resource_type = None
        resource_id = None
        resource_name = None
        modifications = {}
        
        # Resolve target list/library from display name with longest-match strategy.
        all_lists = await list_repository.get_all_lists(_update_site_id)
        _wants_library = "library" in message_lower
        _wants_list = "list" in message_lower and not _wants_library

        best_match = None
        best_match_len = 0
        for lst in all_lists:
            dname = (lst.get("displayName") or "").strip()
            if not dname:
                continue

            is_lib = _is_library_entry(lst)
            if _wants_library and not is_lib:
                continue
            if _wants_list and is_lib:
                continue

            dname_lower = dname.lower()
            compact_name = dname_lower.replace(" ", "")
            direct = dname_lower in message_lower
            compact = len(compact_name) >= 4 and compact_name in message_compact
            if (direct or compact) and len(dname_lower) > best_match_len:
                best_match = lst
                best_match_len = len(dname_lower)

        if best_match:
            resource_id = best_match.get("id")
            resource_name = best_match.get("displayName")
            resource_type = "library" if _is_library_entry(best_match) else "list"

        # Explicit keyword overrides only for unresolved resources.
        if not resource_id and "page" in message_lower:
            resource_type = "page"
        
        if not resource_id:
            # Fallback: use last_created context to resolve the resource
            if last_created and last_created[1] in ("list", "library") and last_created[0]:
                _lc_name = last_created[0]
                _lc_type = last_created[1]
                _lc_site = (last_created[2] if len(last_created) > 2 and last_created[2] else None) or _update_site_id

                if _lc_site != _update_site_id:
                    _update_site_id = _lc_site
                    site_repository = get_site_repository(user_token=user_token, site_id=_update_site_id)
                    list_repository = get_list_repository(user_token=user_token, site_id=_update_site_id)
                    page_repository = get_page_repository(user_token=user_token, site_id=_update_site_id)
                    library_repository = get_library_repository(user_token=user_token, site_id=_update_site_id)
                    permission_repository = get_permission_repository(user_token=user_token, site_id=_update_site_id)
                    enterprise_repository = get_enterprise_repository(user_token=user_token, site_id=_update_site_id)
                    update_use_case = UpdateResourceUseCase(
                        list_repository=list_repository,
                        page_repository=page_repository,
                        library_repository=library_repository,
                        site_repository=site_repository,
                    )
                    all_lists = await list_repository.get_all_lists(_update_site_id)

                for lst in all_lists:
                    _dname = lst.get("displayName", "").lower()
                    if _lc_name.lower() in _dname or _dname in _lc_name.lower():
                        resource_id = lst.get("id")
                        resource_name = lst.get("displayName")
                        resource_type = "library" if (_lc_type == "library" or _is_library_entry(lst)) else "list"
                        break
        if not resource_id:
            return ChatResponse(
                intent="update",
                reply="Which resource would you like to update? Please specify the name.\n\nExample: 'Update the Tasks list to add a Priority column'"
            )

        # Column operations (rename/delete/add) execute directly for both lists and libraries.
        # This avoids destructive full-schema sync side effects from generic list update calls.
        if resource_type in ("list", "library"):
            try:
                _cols = await list_repository.get_list_columns(resource_id, site_id=_update_site_id)
            except Exception as _cols_err:
                logger.warning("Could not fetch columns for resource '%s': %s", resource_name, _cols_err)
                _cols = []

            _rename_column = re.search(
                r'(?:rename|change|update)\s+(?:the\s+)?(?:metadata\s+)?column\s+["\']?(.+?)["\']?\s+to\s+["\']?(.+?)["\']?\s*$',
                message,
                re.IGNORECASE,
            )
            _delete_column = re.search(
                r'(?:delete|remove|drop)\s+(?:the\s+)?(?:metadata\s+)?column\s+["\']?(.+?)["\']?(?:\s+(?:from|in)\b.*)?$',
                message,
                re.IGNORECASE,
            )
            _add_column = re.search(
                r'add\s+(?:a\s+)?(?:metadata\s+)?column\s+(?:called\s+|named\s+)?["\']?([A-Za-z][A-Za-z0-9 _-]*)["\']?(?:\s+(?:as|type)\s+([A-Za-z]+))?',
                message,
                re.IGNORECASE,
            )

            if _rename_column:
                from_name = _rename_column.group(1).strip()
                to_name = _rename_column.group(2).strip()
                _target_col = next((c for c in _cols if _is_column_match(c, from_name)), None)
                if not _target_col:
                    return ChatResponse(
                        intent="update",
                        reply=f"I couldn't find a column named '{from_name}' on '{resource_name}'."
                    )
                await list_repository.update_list_column(
                    resource_id,
                    _target_col["id"],
                    {"displayName": to_name},
                    site_id=_update_site_id,
                )
                return ChatResponse(
                    intent="update",
                    reply=(
                        f"✅ Column **'{_target_col.get('displayName') or _target_col.get('name')}'** "
                        f"renamed to **'{to_name}'** on '{resource_name}'."
                    ),
                    session_id=session_id,
                )

            if _delete_column:
                col_name = _delete_column.group(1).strip()
                _target_col = next((c for c in _cols if _is_column_match(c, col_name)), None)
                if not _target_col:
                    return ChatResponse(
                        intent="update",
                        reply=f"I couldn't find a column named '{col_name}' on '{resource_name}'."
                    )
                await list_repository.delete_list_column(
                    resource_id,
                    _target_col["id"],
                    site_id=_update_site_id,
                )
                return ChatResponse(
                    intent="update",
                    reply=(
                        f"✅ Deleted column **'{_target_col.get('displayName') or _target_col.get('name')}'** "
                        f"from '{resource_name}'."
                    ),
                    session_id=session_id,
                )

            if _add_column:
                col_name = _add_column.group(1).strip()
                col_type_raw = (_add_column.group(2) or "text").strip().lower()
                type_map = {
                    "text": "text",
                    "note": "note",
                    "number": "number",
                    "date": "dateTime",
                    "datetime": "dateTime",
                    "dateTime": "dateTime",
                    "choice": "choice",
                    "boolean": "boolean",
                    "person": "personOrGroup",
                    "personorgroup": "personOrGroup",
                    "url": "hyperlinkOrPicture",
                    "hyperlink": "hyperlinkOrPicture",
                    "currency": "currency",
                }
                col_type = type_map.get(col_type_raw, "text")

                await list_repository.add_list_column(
                    resource_id,
                    SPColumn(name=col_name, type=col_type, required=False),
                    site_id=_update_site_id,
                )
                return ChatResponse(
                    intent="update",
                    reply=f"✅ Added column **'{col_name}'** ({col_type}) to '{resource_name}'.",
                    session_id=session_id,
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
            # Check whether from_name is a column on this list/library
            if resource_id and resource_type in ("list", "library"):
                try:
                    _cols = await list_repository.get_list_columns(resource_id, site_id=_update_site_id)
                    for _col in _cols:
                        _col_display = _col.get("displayName", "")
                        _col_internal = _col.get("name", "")
                        if _col_display.lower() == from_name.lower() or _col_internal.lower() == from_name.lower():
                            # Column rename — execute directly (low-risk, no preview needed)
                            await list_repository.update_list_column(
                                resource_id,
                                _col["id"],
                                {"displayName": to_name},
                                site_id=_update_site_id,
                            )
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
            site_id=_update_site_id,
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
                "site_id": _update_site_id,
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
