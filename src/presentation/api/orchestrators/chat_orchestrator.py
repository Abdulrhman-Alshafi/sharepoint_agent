"""Orchestrator for chat interactions.

Replaces the routing logic previously found in chat.py.
Delegates to specific intent orchestrators.
"""

import logging
import re
from typing import Dict, Any, Optional

from pydantic import BaseModel
from src.infrastructure.external_services.ai_client_factory import get_instructor_client
from src.presentation.api.schemas.chat_schemas import ChatResponse
from src.presentation.api.services.validation_service import is_confirmation
from src.presentation.api.services import conversation_state
from src.presentation.api.services.clarification_service import resolve_clarification_pick, is_location_hint, resolve_search_hint
from src.presentation.api.intent.intent_router import detect_enhanced_intent
from src.presentation.api.orchestrators.orchestrator_utils import pop_pending_action
from src.presentation.api import ServiceContainer, get_site_repository, get_list_repository, get_library_repository, get_page_repository, get_drive_repository

# Intent orchestrators
from src.presentation.api.orchestrators.item_orchestrator import handle_item_operations
from src.presentation.api.orchestrators.site_orchestrator import handle_site_operations
from src.presentation.api.orchestrators.page_orchestrator import handle_page_operations
from src.presentation.api.orchestrators.library_orchestrator import handle_library_operations
from src.presentation.api.orchestrators.permission_orchestrator import handle_permission_operations
from src.presentation.api.orchestrators.enterprise_orchestrator import handle_enterprise_operations
from src.presentation.api.orchestrators.file_orchestrator import handle_file_operations
from src.presentation.api.orchestrators.analysis_orchestrator import handle_analysis_operations
from src.presentation.api.orchestrators.update_orchestrator import handle_update_operations
from src.presentation.api.orchestrators.delete_orchestrator import handle_delete_operations

# Specific handling flows
from src.presentation.api.utils.message_resolver import resolve_followup_message
from src.domain.entities.conversation import GatheringPhase, ResourceType
from src.application.services.question_templates import QuestionTemplates

logger = logging.getLogger(__name__)


def _normalize_folder_paths(value: Any) -> list:
    """Normalize folder-path answers into unique relative paths.

    Also harmonizes trivial singular/plural root variants so mixed inputs like
    "project, project/2026, projects/2026/Q2" end up in one tree.
    """
    if not value:
        return []
    if isinstance(value, list):
        raw_parts = value
    else:
        raw_parts = re.split(r"[\n,;]+", str(value))

    # Root canonicalisation map (e.g., projects -> project when project already seen).
    root_alias: Dict[str, str] = {}

    seen = set()
    result = []
    for part in raw_parts:
        p = str(part).strip().lstrip("-*").strip().strip("/")
        if not p or p.lower() in {"none", "skip", "skip folders", "n/a"}:
            continue

        segs = [seg.strip() for seg in p.split("/") if seg.strip()]
        if not segs:
            continue

        root = segs[0]
        root_l = root.lower()
        singular = root_l[:-1] if root_l.endswith("s") else root_l
        plural = singular + "s"

        canonical_root = root_alias.get(root_l) or root_alias.get(singular) or root_alias.get(plural)
        if not canonical_root:
            canonical_root = root
            root_alias[root_l] = canonical_root
            root_alias[singular] = canonical_root
            root_alias[plural] = canonical_root

        segs[0] = canonical_root
        normalized_path = "/".join(segs)

        if normalized_path not in seen:
            seen.add(normalized_path)
            result.append(normalized_path)
    return result


def _is_nonfatal_folder_exists_error(exc: Exception) -> bool:
    """Return True when folder creation failed only because the folder already exists."""
    msg = str(exc).lower()
    indicators = (
        "already exists",
        "namealreadyexists",
        "resourcealreadyexists",
        "item with the same name",
        "conflict",
    )
    return any(token in msg for token in indicators)


def _is_personal_scope_query(message: str, enhanced_intent: Optional[str]) -> bool:
    """Detect queries that should be scoped to the authenticated user identity."""
    if enhanced_intent == "personal_query":
        return True

    msg = (message or "").strip().lower()
    personal_patterns = (
        r"\bmy\b",
        r"\bmine\b",
        r"assigned to me",
        r"for me",
        r"\bi gave\b",
        r"\bi created\b",
        r"\bi submitted\b",
        r"\bi reported\b",
        r"\bdid i\b",
        r"\bwhat have i\b",
        r"\bi have received\b",
        r"\bi received\b",
        r"received by me",
    )
    return any(re.search(pattern, msg) for pattern in personal_patterns)

_CHAT_SYSTEM_PROMPT = (
    "You are a helpful and professional SharePoint AI Assistant. "
    "You help users create and manage SharePoint lists, pages, document libraries, sites, and more. "
    "You can also answer questions about data in their SharePoint site. "
    "Be concise, professional, friendly, and helpful.\n\n"
    "CRITICAL RULES — you MUST follow these at all times:\n"
    "1. You are a CONVERSATIONAL assistant in this context. Real SharePoint write operations "
    "(create, update, delete) are routed automatically by the system when the user types a command. "
    "You do NOT fabricate success messages or simulate results for operations you did not perform.\n"
    "2. NEVER claim you have added, created, updated, or deleted anything in SharePoint unless the "
    "system has confirmed it. Do not fake item lists or simulated results.\n"
    "3. If a user asks WHETHER you can create a list, library, page, or site — answer YES enthusiastically "
    "and ask them what they would like to name it. For example:\n"
    "   - User: 'can you create a list?' → Reply: 'Yes! I can create a list for you. What would you like to name it?'\n"
    "   - User: 'can you create a library?' → Reply: 'Absolutely! What should the document library be called?'\n"
    "   - User: 'can you create a page?' → Reply: 'Of course! What would you like to name the page?'\n"
    "   - User: 'can you create a site?' → Reply: 'Yes! What would you like to name the new site?'\n"
    "4. If a user provides the name in their message (e.g., 'can you create a list called Projects?'), "
    "tell them you are starting the creation process and ask for any details needed (like a description).\n"
    "5. If a user asks you to add data, add items, or perform write operations without a clear command, "
    "guide them: e.g., 'Sure! Just say \"Add an item to [list name]\" and I\\'ll do it right away.'"
)


class _ChatReplyModel(BaseModel):
    reply: str


def _build_user_query_service(raw_token: Optional[str], site_id: str):
    """Build a per-request user-scoped DataQueryApplicationService when a bearer token is available.

    Returns None if raw_token is absent so callers fall back to the singleton.
    """
    if not raw_token:
        return None
    from src.application.services import DataQueryApplicationService
    from src.infrastructure.external_services.ai_data_query_service import AIDataQueryService
    from src.infrastructure.services.smart_resource_discovery import SmartResourceDiscoveryService

    user_site_repo = get_site_repository(user_token=raw_token, site_id=site_id)
    user_list_repo = get_list_repository(user_token=raw_token, site_id=site_id)
    user_library_repo = get_library_repository(user_token=raw_token, site_id=site_id)
    user_page_repo = get_page_repository(user_token=raw_token, site_id=site_id)
    user_drive_repo = get_drive_repository(user_token=raw_token, site_id=site_id)

    graph_client = getattr(user_site_repo, "graph_client", None)
    ai_client, ai_model = ServiceContainer.get_ai_client()
    smart_discovery = SmartResourceDiscoveryService(
        site_repository=user_site_repo,
        list_repository=user_list_repo,
        library_repository=user_library_repo,
        page_repository=user_page_repo,
        ai_client=ai_client,
        ai_model=ai_model,
    )
    inner = AIDataQueryService(
        site_repository=user_site_repo,
        list_repository=user_list_repo,
        library_repository=user_library_repo,
        page_repository=user_page_repo,
        drive_repository=user_drive_repo,
        graph_client=graph_client,
        site_id=site_id,
        smart_discovery_service=smart_discovery,
        ai_client=ai_client,
        ai_model=ai_model,
    )
    return DataQueryApplicationService(inner)


class ChatOrchestrator:
    """Main orchestrator for processing chat messages."""

    @staticmethod
    async def process_chat(
        message: str,
        history: list,
        session_id: str,
        site_id: str,
        site_ids: list,
        page_ctx: dict,
        raw_token: Optional[str],
        user_email: str,
        user_login_name: str,
        intent_classifier: Any,
        provisioning_service: Any,
        data_query_service: Any,
    ) -> ChatResponse:
        """Process a single chat interaction."""
        # Truncate history to prevent context window overflow
        MAX_HISTORY = 10
        if history and len(history) > MAX_HISTORY:
            history = history[-MAX_HISTORY:]
            
        message_lower_check = message.strip().lower()


        _gathering_service = ServiceContainer.get_gathering_service()
        _pending_state = _gathering_service.conversation_repo.get(session_id)
        if (
            _pending_state
            and _pending_state.phase == GatheringPhase.CONFIRMATION
            and isinstance(getattr(_pending_state, "context_memory", None), dict)
            and _pending_state.context_memory.get("operation") == "update"
        ):
            _msg_l = message_lower_check
            _cancel_update = _msg_l in {"no", "cancel", "stop", "never mind", "nevermind"} or _msg_l.startswith("no ")
            if _cancel_update:
                _gathering_service.conversation_repo.delete(session_id)
                return ChatResponse(
                    intent="update",
                    reply="Update canceled. No changes were applied.",
                    session_id=session_id,
                )
            if is_confirmation(message):
                from src.application.use_cases.update_resource_use_case import UpdateResourceUseCase

                _ctx = _pending_state.context_memory
                _resource_type = _ctx.get("resource_type")
                _resource_id = _ctx.get("resource_id")
                _modifications = _ctx.get("modifications") or {}
                _target_site_id = _ctx.get("site_id") or site_id
                _resource_name = _ctx.get("resource_name") or "resource"

                try:
                    _list_repo = get_list_repository(user_token=raw_token, site_id=_target_site_id)
                    _page_repo = get_page_repository(user_token=raw_token, site_id=_target_site_id)
                    _lib_repo = get_library_repository(user_token=raw_token, site_id=_target_site_id)
                    _site_repo = get_site_repository(user_token=raw_token, site_id=_target_site_id)
                    
                    _uc = UpdateResourceUseCase(
                        list_repository=_list_repo,
                        page_repository=_page_repo,
                        library_repository=_lib_repo,
                        site_repository=_site_repo
                    )
                    
                    _exec_result = await _uc.execute(
                        resource_type=_resource_type,
                        site_id=_target_site_id,
                        resource_id=_resource_id,
                        modifications=_modifications,
                        preview_only=False,
                        user_email=user_login_name or user_email,
                    )
                    _gathering_service.conversation_repo.delete(session_id)
                    return ChatResponse(
                        intent="update",
                        reply=f"✅ Successfully updated **{_resource_name}**.",
                        data_summary={
                            "operation": "update",
                            "resource_type": _resource_type,
                            "resource_id": _resource_id,
                            "site_id": _target_site_id,
                            "modifications": _modifications,
                            "result": _exec_result.get("result", {}),
                        },
                        session_id=session_id,
                    )
                except Exception as _upd_confirm_err:
                    logger.error("Update confirmation execution failed: %s", _upd_confirm_err, exc_info=True)
                    return ChatResponse(
                        intent="update",
                        reply=f"❌ Couldn't apply the update: {_upd_confirm_err}",
                        session_id=session_id,
                    )
            # If user started a new update request, replace pending confirmation with new intent flow.
            if _msg_l.startswith(("update", "rename", "change", "modify")):
                _gathering_service.conversation_repo.delete(session_id)
            else:
                return ChatResponse(
                    intent="update",
                    reply="I still have your update preview pending. Reply with 'yes' to apply it, or 'cancel' to discard it.",
                    session_id=session_id,
                )

        # 1. Pending Action Confirmation
        if is_confirmation(message):
            pending = pop_pending_action(session_id)
            if pending and not pending.is_expired():
                try:
                    result = await pending.callable()

                    action_success_label = {
                        "delete_resource": "deleted",
                        "delete_site": "deleted",
                        "empty_recycle_bin": "emptied",
                    }.get(pending.action_type, "completed")

                    action_failure_label = {
                        "delete_resource": "delete",
                        "delete_site": "delete",
                        "empty_recycle_bin": "empty",
                    }.get(pending.action_type, "complete")

                    if isinstance(result, bool):
                        if result:
                            return ChatResponse(
                                intent="chat",
                                reply=f"✅ Successfully {action_success_label} **{pending.resource_name}**.",
                                session_id=session_id
                            )

                        return ChatResponse(
                            intent="chat",
                            reply=f"❌ Failed to {action_failure_label} **{pending.resource_name}**. Please check permissions and try again.",
                            session_id=session_id
                        )
                    return ChatResponse(
                        intent="chat",
                        reply=f"✅ Successfully {action_success_label} **{pending.resource_name}**.",
                        session_id=session_id
                    )
                except Exception as confirm_err:
                    logger.error("Confirmed action failed: %s", confirm_err, exc_info=True)
                    return ChatResponse(
                        intent="chat",
                        reply=f"❌ The confirmed action failed: {confirm_err}",
                        session_id=session_id
                    )

        # 2. High-Risk Confirmation
        hr_original = await conversation_state.get_high_risk_pending(session_id)
        if hr_original and (message_lower_check.startswith("yes") or message_lower_check.startswith("confirm")):
            await conversation_state.pop_high_risk_pending(session_id)
            _prov_svc = ServiceContainer.get_provisioning_service()
            try:
                from src.presentation.api.utils.response_formatter import format_provisioning_success_message
                _hr_result = await _prov_svc.provision_resources(hr_original, skip_high_risk_check=True, user_email=user_email, user_login_name=user_login_name, user_token=raw_token, target_site_id=site_id)
                _hr_msg = format_provisioning_success_message(None, _hr_result)
                return ChatResponse(
                    intent="provision",
                    reply=_hr_msg,
                    resource_links=_hr_result.resource_links,
                    blueprint=_hr_result.blueprint.__dict__ if _hr_result.blueprint else None,
                    session_id=session_id,
                )
            except Exception as _hr_err:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ The action failed: {_hr_err}",
                    session_id=session_id,
                )

        # 3. Pending Clarification (Disambiguation)
        pending_clar = await conversation_state.pop_pending_clarification(session_id)
        if pending_clar:
            matched_candidate = resolve_clarification_pick(
                message, pending_clar["candidates"],
                clarification_reason=pending_clar.get("clarification_reason", ""),
            )
            if matched_candidate is not None:
                orig_q = pending_clar["original_question"]
                clar_site_id = getattr(matched_candidate, "site_id", None)
                
                # Re-run query logic (simplified for orchestrator)
                try:
                    qsvc = _build_user_query_service(raw_token, clar_site_id or site_id) or data_query_service

                    clar_result = await qsvc.query_data(
                        orig_q,
                        site_ids=[clar_site_id] if clar_site_id else site_ids,
                        user_login_name=user_login_name,
                        **page_ctx,
                    )
                    # Update context for clarification query
                    q_source_site_id = getattr(clar_result, "source_site_id", None) or clar_site_id or site_id
                    q_source_list = getattr(clar_result, "source_list", None)
                    q_source_rtype = getattr(clar_result, "source_resource_type", None) or "list"
                    
                    if q_source_list and q_source_rtype not in ("page", "site"):
                        await conversation_state.set_last_created(session_id, q_source_list, "library" if q_source_rtype == "library" else "list", q_source_site_id)
                    elif q_source_site_id and getattr(clar_result, "source_site_name", None):
                        await conversation_state.set_last_created(session_id, getattr(clar_result, "source_site_name", ""), "site", q_source_site_id)

                    return ChatResponse(
                        intent="query",
                        reply=clar_result.answer,
                        source_list=clar_result.source_list,
                        resource_link=clar_result.resource_link,
                        data_summary=clar_result.data_summary,
                        suggested_actions=clar_result.suggested_actions,
                        source_site_name=clar_result.source_site_name or None,
                        source_site_url=clar_result.source_site_url or None,
                        source_resource_type=clar_result.source_resource_type or None,
                        sources=clar_result.sources if getattr(clar_result, "sources", None) else None,
                        session_id=session_id,
                    )
                except Exception as clar_err:
                    logger.error("Clarification resolution failed: %s", clar_err, exc_info=True)

        # 4. Pending Search Hint
        pending_hint = await conversation_state.pop_pending_search_hint(session_id)
        if pending_hint and is_location_hint(message):
            hint_response = await resolve_search_hint(
                hint_msg=message,
                pending=pending_hint,
                session_id=session_id,
                raw_token=raw_token,
                default_site_id=site_id,
                default_site_ids=site_ids,
                page_ctx=page_ctx,
                data_query_service=data_query_service,
            )
            if hint_response is not None:
                return hint_response

        # 5. Gathering Session Guard
        active_gathering = ServiceContainer.get_gathering_service().conversation_repo.get(session_id)
        in_active_gathering = (
            active_gathering is not None
            and active_gathering.phase not in (GatheringPhase.CONFIRMATION, GatheringPhase.COMPLETE)
        )

        from src.presentation.api.utils.message_resolver import needs_resolution
        
        original_enhanced_intent = detect_enhanced_intent(message)
        
        # If the message needs resolution (has pronouns), we shouldn't trust the 
        # static detector's guess because it lacks context. Resolve it first.
        if needs_resolution(message) and not in_active_gathering:
            resolved_message = resolve_followup_message(message, history)
            effective_message = resolved_message
            enhanced_intent = detect_enhanced_intent(resolved_message)
        elif original_enhanced_intent and not in_active_gathering:
            effective_message = message
            enhanced_intent = original_enhanced_intent
            resolved_message = message
        elif in_active_gathering:
            effective_message = message
            enhanced_intent = None
            resolved_message = message
        else:
            resolved_message = resolve_followup_message(message, history)
            effective_message = resolved_message
            enhanced_intent = detect_enhanced_intent(resolved_message)

        # 6. Route to Intent Orchestrators/Handlers
        last_created_tuple = await conversation_state.get_last_created(session_id)

        if enhanced_intent == "analyze":
            return await handle_analysis_operations(effective_message, site_id, provisioning_service, history=history, user_token=raw_token, user_login_name=user_login_name, user_email=user_email)

        elif enhanced_intent == "item_operation":
            item_resp = await handle_item_operations(effective_message, session_id, site_id, user_token=raw_token, last_created=last_created_tuple, user_login_name=user_login_name)
            await conversation_state.update_last_context_from_response(session_id, item_resp, site_id)
            return item_resp

        elif enhanced_intent == "update":
            _msg_l = effective_message.lower()
            _item_ref_tokens = (
                " first one", " first item", " this item", " that item", " row ", " record ", " entry ",
            )
            _itemish_update = (
                any(tok in f" {_msg_l} " for tok in _item_ref_tokens)
                or (" from " in _msg_l and " to " in _msg_l and ("title" in _msg_l or "status" in _msg_l or "name" in _msg_l))
            )
            _resource_update_tokens = (
                "add column", "rename list", "list settings", "update list", "description", "library", "page",
            )
            if _itemish_update and not any(tok in _msg_l for tok in _resource_update_tokens):
                item_resp = await handle_item_operations(
                    effective_message,
                    session_id,
                    site_id,
                    user_token=raw_token,
                    last_created=last_created_tuple,
                    user_login_name=user_login_name,
                )
                await conversation_state.update_last_context_from_response(session_id, item_resp, site_id)
                return item_resp
            return await handle_update_operations(effective_message, session_id, site_id, provisioning_service, user_email, user_login_name, user_token=raw_token, last_created=last_created_tuple)

        elif enhanced_intent == "delete":
            del_resp = await handle_delete_operations(effective_message, session_id, site_id, provisioning_service, user_email, user_login_name, user_token=raw_token, history=history, last_created=last_created_tuple)
            await conversation_state.update_last_context_from_response(session_id, del_resp, site_id)
            return del_resp

        elif enhanced_intent == "site_operation":
            site_resp = await handle_site_operations(effective_message, session_id, site_id, user_token=raw_token)
            await conversation_state.update_last_context_from_response(session_id, site_resp, site_id)
            return site_resp

        elif enhanced_intent == "page_operation":
            page_resp = await handle_page_operations(effective_message, session_id, site_id, user_token=raw_token, user_login_name=user_login_name, last_created=last_created_tuple)
            await conversation_state.update_last_context_from_response(session_id, page_resp, site_id)
            return page_resp

        elif enhanced_intent == "library_operation":
            lib_resp = await handle_library_operations(effective_message, session_id, site_id, user_token=raw_token, user_login_name=user_login_name, last_created=last_created_tuple)
            await conversation_state.update_last_context_from_response(session_id, lib_resp, site_id)
            return lib_resp

        elif enhanced_intent == "file_operation":
            file_resp = await handle_file_operations(effective_message, session_id, site_id, user_token=raw_token, user_login_name=user_login_name, last_created=last_created_tuple)
            await conversation_state.update_last_context_from_response(session_id, file_resp, site_id)
            return file_resp

        elif enhanced_intent == "permission_operation":
            perm_resp = await handle_permission_operations(effective_message, session_id, site_id, user_token=raw_token, user_login_name=user_login_name)
            await conversation_state.update_last_context_from_response(session_id, perm_resp, site_id)
            return perm_resp

        elif enhanced_intent == "enterprise_operation":
            ent_resp = await handle_enterprise_operations(effective_message, session_id, site_id, user_token=raw_token, user_login_name=user_login_name)
            await conversation_state.update_last_context_from_response(session_id, ent_resp, site_id)
            return ent_resp

        # Set resolved message for normal intent flow
        if in_active_gathering or not original_enhanced_intent:
            resolved_message = effective_message
        else:
            resolved_message = resolve_followup_message(message, history)

        # Guard: route sample-item follow-ups to item operations, not provisioning.
        _msg_for_item_guard = (resolved_message or "").strip().lower()
        _looks_like_sample_item_add = bool(
            re.search(r"\b(add|generate)\s+\d+\s+sample\s+item(s)?\b", _msg_for_item_guard)
        )
        _looks_like_add_data_followup = (
            "add data" in _msg_for_item_guard
            and any(p in _msg_for_item_guard for p in ("this list", "the list", "to it", "to this"))
        )
        _looks_like_inline_field_values = bool(
            re.search(r"\b[\w\s]+:\s*[^,\n]+", resolved_message or "")
        )
        _assistant_last_msg = ""
        for _h in reversed(history or []):
            if _h.get("role") == "assistant":
                _assistant_last_msg = (_h.get("content") or "").lower()
                break
        _assistant_prompted_for_item_values = any(
            p in _assistant_last_msg
            for p in (
                "what data would you like to add",
                "this list has these columns",
                "you can tell me the values",
                "or i can generate sample data",
            )
        )
        _looks_like_item_value_reply = _looks_like_inline_field_values and _assistant_prompted_for_item_values

        if (_looks_like_sample_item_add or _looks_like_add_data_followup or _looks_like_item_value_reply) and last_created_tuple and last_created_tuple[1] == "list":
            item_resp = await handle_item_operations(
                resolved_message,
                session_id,
                site_id,
                user_token=raw_token,
                last_created=last_created_tuple,
                user_login_name=user_login_name,
            )
            await conversation_state.update_last_context_from_response(session_id, item_resp, site_id)
            return item_resp

        # 7. Classify Main Intent
        if in_active_gathering:
            main_intent = "provision"
        elif enhanced_intent in ("personal_query", "page_query"):
            main_intent = "query"
        else:
            main_intent = await intent_classifier.classify_intent(resolved_message, history)

        logger.info("Classified intent: %s", main_intent)

        # 8. Main Intent Routing
        if main_intent == "query":
            # Simplified query routing logic
            try:
                query_message = resolved_message

                # Enrich personal-scope queries with the authenticated user context.
                # The query service expects this tag for accurate personal filtering.
                if _is_personal_scope_query(query_message, enhanced_intent):
                    _identity_email = (user_login_name or user_email or "").strip()
                    if _identity_email and not query_message.startswith("[Current user:"):
                        _name_part = _identity_email.split("@")[0].replace(".", " ").replace("_", " ").strip()
                        _display_name = _name_part.title() if _name_part else _identity_email
                        query_message = f"[Current user: {_display_name} (email: {_identity_email})] {query_message}"

                # Execute query using a user-scoped service when a token is available
                _eff_query_svc = _build_user_query_service(raw_token, site_id) or data_query_service
                result_dto = await _eff_query_svc.query_data(query_message, site_ids=site_ids, user_login_name=user_login_name, **page_ctx)
                
                # Handle clarification
                if getattr(result_dto, "clarification_candidates", None):
                    await conversation_state.set_pending_clarification(
                        session_id, query_message, result_dto.clarification_candidates,
                        (result_dto.data_summary or {}).get("clarification_reason", "")
                    )
                elif (result_dto.data_summary or {}).get("needs_location_hint"):
                    await conversation_state.set_pending_search_hint(session_id, query_message, resolved_message)
                    hint_suffix = "\n\nDo you know which **site** or **page** it's on? Just tell me and I'll search there."
                    result_dto.answer += hint_suffix

                # Update context
                q_source_site_id = getattr(result_dto, "source_site_id", None) or site_id
                q_source_list = getattr(result_dto, "source_list", None)
                q_source_rtype = getattr(result_dto, "source_resource_type", None) or "list"
                
                # If they queried a specific list, save it
                if q_source_list and q_source_rtype not in ("page", "site"):
                    await conversation_state.set_last_created(session_id, q_source_list, "library" if q_source_rtype == "library" else "list", q_source_site_id)
                # Else if they queried a specific site (e.g. meta query), save the site context
                elif q_source_site_id and getattr(result_dto, "source_site_name", None):
                    await conversation_state.set_last_created(session_id, getattr(result_dto, "source_site_name", ""), "site", q_source_site_id)

                return ChatResponse(
                    intent="query",
                    reply=result_dto.answer,
                    source_list=result_dto.source_list,
                    resource_link=result_dto.resource_link,
                    data_summary=result_dto.data_summary,
                    suggested_actions=result_dto.suggested_actions,
                    source_site_name=result_dto.source_site_name or None,
                    source_site_url=result_dto.source_site_url or None,
                    source_resource_type=result_dto.source_resource_type or None,
                    sources=result_dto.sources if getattr(result_dto, "sources", None) else None,
                    session_id=session_id,
                )
            except Exception as e:
                # Error handling
                from src.domain.exceptions import DomainException
                from src.presentation.api.orchestrators.orchestrator_utils import domain_error_response
                if isinstance(e, DomainException):
                    return domain_error_response(e, intent="query", session_id=session_id)
                logger.error("Query error: %s", e, exc_info=True)
                return ChatResponse(intent="chat", reply=f"Error processing query: {e}", session_id=session_id)

        elif main_intent == "provision":
            # ── Gathering-aware provisioning flow ──────────────────────
            gathering_service = ServiceContainer.get_gathering_service()
            try:
                # Check if we're continuing an active gathering session
                if in_active_gathering and active_gathering:
                    try:
                        state, next_question, is_complete = gathering_service.process_answer(
                            session_id, resolved_message
                        )
                    except ValueError as validation_err:
                        # Keep user on the same question and explain why the answer is invalid.
                        current_state = gathering_service.conversation_repo.get(session_id)
                        if current_state:
                            current_spec = current_state.get_current_spec()
                            if current_spec:
                                current_questions = QuestionTemplates.get_questions(current_spec.resource_type)
                                if 0 <= current_state.current_question_index < len(current_questions):
                                    current_question = current_questions[current_state.current_question_index]
                                    return ChatResponse(
                                        intent="provision",
                                        reply=f"⚠️ {validation_err}\n\n{current_question.question_text}",
                                        requires_input=True,
                                        question_prompt=current_question.question_text,
                                        field_type=current_question.field_type,
                                        field_options=current_question.options,
                                        quick_suggestions=current_question.options[:3] if current_question.options else None,
                                        session_id=session_id,
                                    )
                        return ChatResponse(
                            intent="provision",
                            reply=f"⚠️ {validation_err}",
                            session_id=session_id,
                        )

                    if is_complete:
                        # All questions answered → build prompt from collected fields and provision
                        spec = state.get_current_spec()
                        collected = spec.collected_fields if spec else {}
                        from src.presentation.api.utils.prompt_builder import build_provisioning_prompt_from_spec

                        # Auto-populate owner_email with authenticated user's email for sites
                        if spec and spec.resource_type == ResourceType.SITE and user_email:
                            spec.collected_fields["owner_email"] = user_email
                        
                        provision_prompt = build_provisioning_prompt_from_spec(spec) if spec else "Create a resource"
                        logger.info("Gathering complete — provisioning with prompt: %s", provision_prompt)

                        # Mark gathering as complete
                        gathering_service.confirm_and_complete(session_id)

                        # Resolve target_site to actual site_id if provided
                        resolved_target_site_id = site_id
                        if collected.get("target_site") and collected["target_site"].strip():
                            target_site_name = collected["target_site"].strip()
                            normalized_target_site = target_site_name.lower()
                            if target_site_name == "CURRENT_SITE" or normalized_target_site in {"current site", "use current site", "this site", "same site", "here"}:
                                resolved_target_site_id = site_id
                            else:
                                try:
                                    # Try to resolve the site name to a site ID
                                    repo = get_site_repository(user_token=raw_token)
                                    matched_site = None
                                    
                                    # First try search_sites
                                    search_results = await repo.search_sites(target_site_name)
                                    for s in search_results:
                                        if s.get("displayName", "").lower() == normalized_target_site or s.get("name", "").lower() == normalized_target_site:
                                            matched_site = s
                                            break
                                            
                                    if not matched_site:
                                        all_sites = await repo.get_all_sites()
                                        # Exact match first
                                        for s in all_sites:
                                            if s.get("displayName", "").lower() == normalized_target_site or s.get("name", "").lower() == normalized_target_site:
                                                matched_site = s
                                                break
                                        # Partial match if no exact match
                                        if not matched_site:
                                            for s in all_sites:
                                                if normalized_target_site in s.get("displayName", "").lower() or normalized_target_site in s.get("name", "").lower():
                                                    matched_site = s
                                                    break
                                                    
                                    if matched_site:
                                        resolved_target_site_id = matched_site.get("id") or site_id
                                        logger.info("Resolved target_site '%s' to site ID: %s", target_site_name, resolved_target_site_id)
                                    else:
                                        # We could not find the target site! Do not silently fallback.
                                        logger.warning("Failed to resolve target_site '%s'. Sending error back to user.", target_site_name)
                                        return ChatResponse(
                                            intent="provision",
                                            reply=f"⚠️ I couldn't find a SharePoint site named '{target_site_name}'. Please make sure the site exists and you have access to it. You can try again using the exact site name, or say 'current site' to build it here.",
                                            session_id=session_id,
                                        )
                                except Exception as site_resolve_err:
                                    logger.warning("Error while resolving target_site '%s': %s", target_site_name, site_resolve_err)
                                    return ChatResponse(
                                        intent="provision",
                                        reply=f"⚠️ There was an error looking up the site '{target_site_name}'. Please try again, or use 'current site'.",
                                        session_id=session_id,
                                    )

                        result_dto = await provisioning_service.provision_resources(
                            provision_prompt,
                            user_email=user_email,
                            user_login_name=user_login_name,
                            user_token=raw_token,
                            target_site_id=resolved_target_site_id,
                        )
                        from src.presentation.api.utils.response_formatter import format_provisioning_success_message
                        success_msg = format_provisioning_success_message(None, result_dto)

                        # If the user asked for starter folders in a new library, create them now.
                        if spec and spec.resource_type == ResourceType.LIBRARY:
                            create_pref = str(collected.get("create_folders", "")).lower()
                            folder_paths = _normalize_folder_paths(collected.get("folder_paths"))
                            if "no folders" not in create_pref and folder_paths and getattr(result_dto, "created_document_libraries", None):
                                lib_meta = result_dto.created_document_libraries[0] if result_dto.created_document_libraries else {}
                                lib_id = lib_meta.get("id")
                                if lib_id:
                                    repo = get_drive_repository(user_token=raw_token)
                                    created = []
                                    failed = []
                                    for raw_path in folder_paths:
                                        segments = [seg.strip() for seg in raw_path.split("/") if seg.strip()]
                                        for idx, folder_name in enumerate(segments):
                                            parent = "/".join(segments[:idx]) if idx > 0 else "/"
                                            full_path = "/".join(segments[: idx + 1])
                                            if full_path in created:
                                                continue
                                            try:
                                                await repo.create_folder(
                                                    lib_id,
                                                    folder_name,
                                                    parent if parent != "/" else None,
                                                    site_id=resolved_target_site_id,
                                                )
                                                created.append(full_path)
                                            except Exception as folder_err:
                                                if _is_nonfatal_folder_exists_error(folder_err):
                                                    # Already created during blueprint provisioning; treat as success.
                                                    created.append(full_path)
                                                    continue
                                                failed.append(full_path)
                                                break
                                    if created:
                                        success_msg += f"\n\n📁 Created folders: {', '.join(created)}"
                                    if failed:
                                        success_msg += "\n⚠️ Some folders could not be created automatically."

                        await conversation_state.update_last_context_from_provision(session_id, result_dto, resolved_target_site_id)
                        return ChatResponse(
                            intent="provision",
                            reply=success_msg,
                            resource_links=result_dto.resource_links if result_dto.resource_links else None,
                            session_id=session_id,
                        )
                    else:
                        # More questions to ask
                        return ChatResponse(
                            intent="provision",
                            reply=next_question.question_text,
                            requires_input=True,
                            question_prompt=next_question.question_text,
                            field_type=next_question.field_type,
                            field_options=next_question.options,
                            quick_suggestions=next_question.options[:3] if next_question.options else None,
                            session_id=session_id,
                        )

                # Not in active gathering — detect if we should start one
                resource_type = gathering_service.detect_resource_intent(resolved_message)
                if resource_type is not None:
                    state, first_question = gathering_service.start_gathering(
                        session_id, resolved_message, resource_type
                    )

                    if first_question is None:
                        # All fields pre-extracted from the message → go straight to provisioning
                        gathering_service.confirm_and_complete(session_id)
                        
                        # Resolve target_site to actual site_id if provided in pre-extracted fields
                        resolved_target_site_id = site_id
                        spec = state.get_current_spec() if state else None
                        if spec and spec.collected_fields.get("target_site"):
                            target_site_name = spec.collected_fields["target_site"].strip()
                            try:
                                repo = get_site_repository(user_token=raw_token)
                                all_sites = await repo.get_all_sites()
                                matched_site = None
                                for s in all_sites:
                                    if s.get("displayName", "").lower() == target_site_name.lower() or s.get("name", "").lower() == target_site_name.lower():
                                        matched_site = s
                                        break
                                if not matched_site:
                                    for s in all_sites:
                                        if target_site_name.lower() in s.get("displayName", "").lower() or target_site_name.lower() in s.get("name", "").lower():
                                            matched_site = s
                                            break
                                if matched_site:
                                    resolved_target_site_id = matched_site.get("id") or site_id
                                    logger.info("Resolved target_site '%s' to site ID: %s", target_site_name, resolved_target_site_id)
                            except Exception as site_resolve_err:
                                logger.warning("Failed to resolve target_site '%s': %s", target_site_name, site_resolve_err)
                                resolved_target_site_id = site_id
                        
                        result_dto = await provisioning_service.provision_resources(
                            resolved_message,
                            user_email=user_email,
                            user_login_name=user_login_name,
                            user_token=raw_token,
                            target_site_id=resolved_target_site_id,
                        )
                        from src.presentation.api.utils.response_formatter import format_provisioning_success_message
                        success_msg = format_provisioning_success_message(None, result_dto)

                        if spec and spec.resource_type == ResourceType.LIBRARY:
                            collected = spec.collected_fields if spec else {}
                            create_pref = str(collected.get("create_folders", "")).lower()
                            folder_paths = _normalize_folder_paths(collected.get("folder_paths"))
                            if "no folders" not in create_pref and folder_paths and getattr(result_dto, "created_document_libraries", None):
                                lib_meta = result_dto.created_document_libraries[0] if result_dto.created_document_libraries else {}
                                lib_id = lib_meta.get("id")
                                if lib_id:
                                    repo = get_drive_repository(user_token=raw_token)
                                    created = []
                                    failed = []
                                    for raw_path in folder_paths:
                                        segments = [seg.strip() for seg in raw_path.split("/") if seg.strip()]
                                        for idx, folder_name in enumerate(segments):
                                            parent = "/".join(segments[:idx]) if idx > 0 else "/"
                                            full_path = "/".join(segments[: idx + 1])
                                            if full_path in created:
                                                continue
                                            try:
                                                await repo.create_folder(
                                                    lib_id,
                                                    folder_name,
                                                    parent if parent != "/" else None,
                                                    site_id=resolved_target_site_id,
                                                )
                                                created.append(full_path)
                                            except Exception as folder_err:
                                                if _is_nonfatal_folder_exists_error(folder_err):
                                                    # Already created during blueprint provisioning; treat as success.
                                                    created.append(full_path)
                                                    continue
                                                failed.append(full_path)
                                                break
                                    if created:
                                        success_msg += f"\n\n📁 Created folders: {', '.join(created)}"
                                    if failed:
                                        success_msg += "\n⚠️ Some folders could not be created automatically."

                        await conversation_state.update_last_context_from_provision(session_id, result_dto, resolved_target_site_id)
                        return ChatResponse(
                            intent="provision",
                            reply=success_msg,
                            resource_links=result_dto.resource_links if result_dto.resource_links else None,
                            session_id=session_id,
                        )

                    # Ask the first question
                    return ChatResponse(
                        intent="provision",
                        reply=f"Sure! Let me help you set that up. 🚀\n\n{first_question.question_text}",
                        requires_input=True,
                        question_prompt=first_question.question_text,
                        field_type=first_question.field_type,
                        field_options=first_question.options,
                        quick_suggestions=first_question.options[:3] if first_question.options else None,
                        session_id=session_id,
                    )

                # Could not detect resource type — fall back to direct provisioning
                # Guardrail: vague create-library requests must enter question flow,
                # not direct provisioning with AI-invented defaults.
                _msg_l = (resolved_message or "").lower()
                _vague_library_create = (
                    any(tok in _msg_l for tok in ("library", "libary", "document library"))
                    and any(tok in _msg_l for tok in ("create", "add", "new", "make"))
                    and not any(tok in _msg_l for tok in ("called", "named", "name is", "titled", "with name"))
                )
                if _vague_library_create:
                    state, first_question = gathering_service.start_gathering(
                        session_id, resolved_message, ResourceType.LIBRARY
                    )
                    if first_question is not None:
                        return ChatResponse(
                            intent="provision",
                            reply=f"Sure! Let me help you set that up.\n\n{first_question.question_text}",
                            requires_input=True,
                            question_prompt=first_question.question_text,
                            field_type=first_question.field_type,
                            field_options=first_question.options,
                            quick_suggestions=first_question.options[:3] if first_question.options else None,
                            session_id=session_id,
                        )

                # Try to extract and resolve target_site from message if provided
                fallback_resolved_site_id = site_id
                try:
                    _fallback_msg_lower = resolved_message.lower()
                    _site_patterns = ["in ", "in the ", "on ", "on the ", "for ", "for the ", "from ", "from the "]
                    _potential_site = None
                    for pat in _site_patterns:
                        if pat in _fallback_msg_lower:
                            _after_pat = _fallback_msg_lower.split(pat)[-1].split(" ")[0]
                            if _after_pat and len(_after_pat) > 2:
                                _potential_site = _after_pat
                                break
                    if _potential_site:
                        _fallback_repo = get_site_repository(user_token=raw_token)
                        _fallback_sites = await _fallback_repo.get_all_sites()
                        _matched_fallback = None
                        for _s in _fallback_sites:
                            if _potential_site.lower() in _s.get("displayName", "").lower() or _potential_site.lower() in _s.get("name", "").lower():
                                _matched_fallback = _s
                                break
                        if _matched_fallback:
                            fallback_resolved_site_id = _matched_fallback.get("id") or site_id
                except Exception:
                    pass  # Non-critical, use default site_id
                
                result_dto = await provisioning_service.provision_resources(
                    resolved_message,
                    user_email=user_email,
                    user_login_name=user_login_name,
                    user_token=raw_token,
                    target_site_id=fallback_resolved_site_id,
                )
                from src.presentation.api.utils.response_formatter import format_provisioning_success_message
                success_msg = format_provisioning_success_message(None, result_dto)
                await conversation_state.update_last_context_from_provision(session_id, result_dto, fallback_resolved_site_id)
                return ChatResponse(
                    intent="provision",
                    reply=success_msg,
                    resource_links=result_dto.resource_links if result_dto.resource_links else None,
                    session_id=session_id,
                )
            except Exception as e:
                logger.error("Provisioning error: %s", e, exc_info=True)
                return ChatResponse(intent="chat", reply=f"Provisioning error: {e}", session_id=session_id)

        else:  # Chat intent — generate a real conversational response via LLM
            try:
                client, model = get_instructor_client()
                _kwargs: Dict[str, Any] = {
                    "messages": [
                        {"role": "system", "content": _CHAT_SYSTEM_PROMPT},
                        {"role": "user", "content": resolved_message},
                    ],
                    "response_model": _ChatReplyModel,
                }
                if model:
                    _kwargs["model"] = model
                _chat_result = client.chat.completions.create(**_kwargs)
                return ChatResponse(intent="chat", reply=_chat_result.reply, session_id=session_id)
            except Exception as _chat_err:
                logger.error("Chat response generation failed: %s", _chat_err, exc_info=True)
                return ChatResponse(
                    intent="chat",
                    reply=f"I'm sorry, I encountered an error while processing your message: {_chat_err}",
                    session_id=session_id,
                )

