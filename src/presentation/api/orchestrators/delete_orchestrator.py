"""Handler for resource deletion operations."""

import re
from typing import List, Dict, Any, Tuple

from src.presentation.api.schemas.chat_schemas import ChatResponse
from src.presentation.api.orchestrators.orchestrator_utils import (
    get_logger, error_response,
    PendingAction, store_pending_action,
)
from src.application.services import ProvisioningApplicationService

logger = get_logger(__name__)


def _resolve_last_resource_from_history(history: List[Dict[str, Any]]) -> Tuple[str, str]:
    """Scan recent conversation history for the last explicitly named resource.

    Returns (resource_name, resource_type) or ("", "") if nothing found.
    """
    _PATTERNS = [
        # ✅ Successfully created 'Project tracker' list!
        (re.compile(r"Successfully created ['\"](.+?)['\"](?:\s*(list|page|library|site))?", re.I), "list"),
        # ✅ Document library theColors created successfully!
        (re.compile(r"Document\s+library\s+\*\*(.+?)\*\*\s+created\s+successfully", re.I), "library"),
        (re.compile(r"Document\s+library\s+(.+?)\s+created\s+successfully", re.I), "library"),
        # ⚠️ Deleting 'Test1' (list)
        (re.compile(r"Deleting ['\"](.+?)['\"]\s*\((list|page|library|site)\)", re.I), None),
        # ✅ Done — Test1 list action completed
        (re.compile(r"Done — (.+?) action completed", re.I), "list"),
    ]
    for msg in reversed((history or [])[-10:]):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        for pattern, default_type in _PATTERNS:
            m = pattern.search(content)
            if not m:
                continue
            name = m.group(1).strip()
            # Second capture group may contain the resource type
            try:
                rtype = m.group(2) or default_type or "list"
            except IndexError:
                rtype = default_type or "list"
            return name, rtype.lower()
    return "", ""


async def handle_delete_operations(message: str, session_id: str, site_id: str, provisioning_service: ProvisioningApplicationService, user_email: str = None, user_login_name: str = None, user_token: str = None, history: List[Dict[str, Any]] = None, last_created: tuple = None) -> ChatResponse:
    """Handle resource deletion requests with impact analysis."""
    from src.presentation.api import get_site_repository, get_list_repository, get_page_repository, get_library_repository, get_permission_repository, get_enterprise_repository
    from src.domain.exceptions import PermissionDeniedException
    from src.application.use_cases.delete_resource_use_case import DeleteResourceUseCase
    
    try:
        site_repository = get_site_repository(user_token=user_token)
        list_repository = get_list_repository(user_token=user_token)
        page_repository = get_page_repository(user_token=user_token)
        library_repository = get_library_repository(user_token=user_token)
        permission_repository = get_permission_repository(user_token=user_token)
        enterprise_repository = get_enterprise_repository(user_token=user_token)
        delete_use_case = DeleteResourceUseCase(
            list_repository=list_repository,
            site_repository=site_repository,
            page_repository=page_repository,
            library_repository=library_repository
        )
        
        message_lower = message.lower()
        message_tokens = set(message_lower.split())
        # Tracks the effective site for this delete.
        # Seed from last_created's site so that "delete Cars list" after creating Cars on IT Support
        # correctly targets IT Support without needing a pronoun.
        _delete_site_id = (last_created[2] if (last_created and len(last_created) > 2 and last_created[2]) else None) or site_id

        # ── Guard: "delete list item" / "delete item from list" must go to item_handler ──
        if ("item" in message_tokens or "items" in message_tokens
                or "list item" in message_lower or "record" in message_tokens):
            from src.presentation.api.orchestrators.item_orchestrator import handle_item_operations
            return await handle_item_operations(message, session_id, _delete_site_id, user_token=user_token, last_created=last_created)

        # Extract resource to delete
        resource_type = None
        resource_id = None
        resource_name = None
        
        if "list" in message_lower:
            resource_type = "list"
            all_lists = await list_repository.get_all_lists(_delete_site_id)
            # Use longest match to avoid picking a shorter name that is a substring of the intended one
            # (e.g. "Announcements" must not win over "Team Announcements")
            # Also try space-compact matching so "Test1" matches when user types "test 1" and vice versa.
            best_match = None
            best_match_len = 0
            _msg_compact = message_lower.replace(" ", "")
            for lst in all_lists:
                list_name = lst.get("displayName", "").lower()
                if not list_name:
                    continue
                list_compact = list_name.replace(" ", "")
                direct = list_name in message_lower
                # Compact match: require length >= 4 to avoid spurious short-name matches
                compact = (len(list_compact) >= 4) and (list_compact in _msg_compact)
                if (direct or compact) and len(list_name) > best_match_len:
                    best_match = lst
                    best_match_len = len(list_name)
            if best_match:
                resource_id = best_match.get("id")
                resource_name = best_match.get("displayName")
        elif "page" in message_lower:
            resource_type = "page"
            # Resolve page ID by searching for the page name in the message
            try:
                pages = await page_repository.get_all_pages(site_id=_delete_site_id)
                for page in pages:
                    page_name = (page.get("name") or page.get("title") or "").lower().replace(".aspx", "")
                    if page_name and page_name in message_lower:
                        resource_id = page.get("id")
                        resource_name = page.get("name") or page.get("title")
                        break
            except Exception:
                pass
        elif "library" in message_lower:
            resource_type = "library"
            # Resolve library ID from lists (libraries are lists in Graph API)
            try:
                all_libraries = await library_repository.get_all_document_libraries(site_id=_delete_site_id)
                _msg_compact = message_lower.replace(" ", "")
                best_match = None
                best_match_len = 0
                for lst in all_libraries:
                    list_name = lst.get("displayName", "").lower()
                    if list_name in message_lower:
                        if len(list_name) > best_match_len:
                            best_match = lst
                            best_match_len = len(list_name)
                        continue
                    compact_name = list_name.replace(" ", "")
                    if len(compact_name) >= 4 and compact_name in _msg_compact and len(list_name) > best_match_len:
                        best_match = lst
                        best_match_len = len(list_name)
                if best_match:
                    resource_id = best_match.get("id")
                    resource_name = best_match.get("displayName")
            except Exception:
                pass
        elif "site" in message_lower:
            resource_type = "site"
            # Resolve site ID from sites
            try:
                all_sites = await site_repository.get_all_sites()
                for site in all_sites:
                    if isinstance(site, dict):
                        site_name_val = site.get("name", "")
                        site_display_name_val = site.get("displayName", "")
                        site_id_val = site.get("id")
                    else:
                        site_name_val = getattr(site, "name", "")
                        site_display_name_val = getattr(site, "displayName", "")
                        site_id_val = getattr(site, "id", None)
                        
                    site_name = (site_name_val or "").lower()
                    site_display = (site_display_name_val or "").lower()
                    
                    if (site_name and site_name in message_lower) or (site_display and site_display in message_lower):
                        resource_id = site_id_val
                        resource_name = site_display_name_val or site_name_val
                        break
            except Exception:
                pass
        else:
            # No resource type word in message (e.g. "delete Test1").
            # Scan lists using direct + compact name matching to infer the resource.
            try:
                _msg_compact = message_lower.replace(" ", "")
                all_lists = await list_repository.get_all_lists(_delete_site_id)
                best_match = None
                best_match_len = 0
                for lst in all_lists:
                    list_name = lst.get("displayName", "").lower()
                    if not list_name:
                        continue
                    list_compact = list_name.replace(" ", "")
                    direct = list_name in message_lower
                    compact = (len(list_compact) >= 3) and (list_compact in _msg_compact)
                    if (direct or compact) and len(list_name) > best_match_len:
                        best_match = lst
                        best_match_len = len(list_name)
                if best_match:
                    resource_type = "list"
                    resource_id = best_match.get("id")
                    resource_name = best_match.get("displayName")
            except Exception:
                pass
        
        if not resource_id or not resource_name:
            # Try to resolve pronoun references ("delete it", "remove this") using context
            _pronoun_tokens = {"it", "this", "that", "these", "those", "them"}
            _uses_pronoun = bool(set(message_lower.split()) & _pronoun_tokens)
            if _uses_pronoun:
                # Primary: server-side last-created tracker (most reliable)
                hist_name, hist_type = "", ""
                if last_created and last_created[0]:
                    hist_name, hist_type = last_created[0], last_created[1]
                    # Prefer the site where the resource was created (3rd element of tuple)
                    _last_created_site = last_created[2] if len(last_created) > 2 else None
                    if _last_created_site:
                        _delete_site_id = _last_created_site
                # Fallback: parse history text
                if not hist_name and history:
                    hist_name, hist_type = _resolve_last_resource_from_history(history)
                if hist_name:
                    _hist_type_lower = (hist_type or "list").lower()
                    if _hist_type_lower == "page":
                        # Resolve page by name using the repository directly
                        try:
                            _all_pages = await page_repository.get_all_pages(site_id=_delete_site_id)
                            _hist_compact = hist_name.lower().replace(" ", "").replace(".aspx", "")
                            for _pg in _all_pages:
                                _pg_name = (_pg.get("name") or _pg.get("title") or "").lower().replace(".aspx", "")
                                if _pg_name and (_pg_name == hist_name.lower() or _pg_name.replace(" ", "") == _hist_compact):
                                    resource_type = "page"
                                    resource_id = _pg.get("id")
                                    resource_name = _pg.get("name") or _pg.get("title") or hist_name
                                    break
                        except Exception:
                            pass
                    elif _hist_type_lower == "site":
                        # Resolve site by its last-created name/displayName.
                        try:
                            _all_sites = await site_repository.get_all_sites()
                            _hist_lower = hist_name.lower()
                            _hist_compact = _hist_lower.replace(" ", "")
                            _best_site = None
                            _best_len = 0
                            for _st in _all_sites:
                                _dn = (_st.get("displayName") or "").lower()
                                _nm = (_st.get("name") or "").lower()
                                _dn_compact = _dn.replace(" ", "")
                                _nm_compact = _nm.replace(" ", "")
                                _exact = _dn == _hist_lower or _nm == _hist_lower or _dn_compact == _hist_compact or _nm_compact == _hist_compact
                                _partial = (_hist_lower and (_hist_lower in _dn or _hist_lower in _nm))
                                _score_len = max(len(_dn), len(_nm))
                                if (_exact or _partial) and _score_len > _best_len:
                                    _best_site = _st
                                    _best_len = _score_len
                            if _best_site:
                                resource_type = "site"
                                resource_id = _best_site.get("id")
                                resource_name = _best_site.get("displayName") or _best_site.get("name") or hist_name
                        except Exception:
                            pass
                    elif _hist_type_lower == "library":
                        # Resolve library by name
                        try:
                            _all_libs = await library_repository.get_all_document_libraries(site_id=_delete_site_id)
                            _hist_compact = hist_name.lower().replace(" ", "")
                            _best_lib = None
                            _best_len = 0
                            for _lib in _all_libs:
                                ln = (_lib.get("displayName") or "").lower()
                                if not ln:
                                    continue
                                lc = ln.replace(" ", "")
                                exact = ln == hist_name.lower() or lc == _hist_compact
                                partial = hist_name.lower() in ln or ln in hist_name.lower()
                                if (exact or partial) and len(ln) > _best_len:
                                    _best_lib = _lib
                                    _best_len = len(ln)
                            if _best_lib:
                                resource_type = "library"
                                resource_id = _best_lib.get("id")
                                resource_name = _best_lib.get("displayName")
                        except Exception:
                            pass
                    else:
                        # Default: try to match the resolved name against actual lists
                        try:
                            _msg_compact2 = hist_name.lower().replace(" ", "")
                            all_lists2 = await list_repository.get_all_lists(_delete_site_id)
                            best2 = None
                            best2_len = 0
                            for lst in all_lists2:
                                ln = lst.get("displayName", "").lower()
                                if not ln:
                                    continue
                                lc = ln.replace(" ", "")
                                if (ln == hist_name.lower() or lc == _msg_compact2) and len(ln) > best2_len:
                                    best2 = lst
                                    best2_len = len(ln)
                            if best2:
                                resource_type = _hist_type_lower or "list"
                                resource_id = best2.get("id")
                                resource_name = best2.get("displayName")
                        except Exception:
                            pass

            if not resource_id or not resource_name:
                # If we couldn't resolve any resource (list, page, library, site), it might be an item!
                from src.presentation.api.orchestrators.item_orchestrator import handle_item_operations
                return await handle_item_operations(message, session_id, _delete_site_id, user_token=user_token, last_created=last_created)
        
        # Check if this is a confirmation — accept with or without comma
        # e.g. "yes, delete test1" OR "yes delete test1"
        _rname_lower = resource_name.lower()
        confirmed = (
            f"yes, delete {_rname_lower}" in message_lower
            or f"yes delete {_rname_lower}" in message_lower
        )
        
        # Execute delete with impact analysis
        result = await delete_use_case.execute(
            resource_type=resource_type,
            site_id=_delete_site_id,
            resource_id=resource_id,
            resource_name=resource_name,
            confirmed=confirmed,
            user_login_name=user_login_name,
        )
        
        if result.get("requires_confirmation"):
            impact = result["impact"]
            _captured_delete_site_id = _delete_site_id
            
            # Store pending deletion action to be executed when user confirms
            async def _execute_deletion():
                delete_result = await delete_use_case.execute(
                    resource_type=resource_type,
                    site_id=_captured_delete_site_id,
                    resource_id=resource_id,
                    resource_name=resource_name,
                    confirmed=True,
                    user_login_name=user_login_name,
                )
                return delete_result.get("success", False)
            
            store_pending_action(
                session_id=session_id,
                action=PendingAction(
                    action_type="delete_resource",
                    resource_name=resource_name,
                    callable=_execute_deletion,
                ),
            )
            
            return ChatResponse(
                intent="delete",
                reply="",
                deletion_impact={
                    "resource_type": impact.target_resource_type,
                    "resource_name": impact.target_resource_name,
                    "item_count": impact.item_count,
                    "dependent_resources": impact.dependent_resources,
                    "data_loss": impact.data_loss_summary,
                    "reversibility": impact.reversibility,
                    "risk_level": impact.risk_level.value
                },
                confirmation_text=result.get("confirmation_text"),
                session_id=session_id,
                requires_confirmation=True,
                data_summary={
                    f"{resource_type}_name": resource_name,
                    "site_id": _delete_site_id,
                },
            )
        
        if result.get("success"):
            return ChatResponse(
                intent="delete",
                reply=result["message"],
                session_id=session_id,
                data_summary={
                    f"{resource_type}_name": resource_name,
                    "site_id": _delete_site_id,
                },
            )
        else:
            return ChatResponse(
                intent="delete",
                reply="Deletion failed. Please try again or contact support.",
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
            return domain_error_response(e, intent="delete", session_id=session_id)
        return error_response(logger, "delete", "Sorry, I couldn't delete that resource: {error}", e,
                              error_category="internal",
                              recovery_hint="Please try again. If this persists, contact your administrator.")
