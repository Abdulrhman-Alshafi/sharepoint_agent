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
from src.presentation.api import ServiceContainer, get_repository

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

logger = logging.getLogger(__name__)


def _normalize_folder_paths(value: Any) -> list:
    """Normalize folder-path answers into a clean list of unique relative paths."""
    if not value:
        return []
    if isinstance(value, list):
        raw_parts = value
    else:
        raw_parts = re.split(r"[\n,;]+", str(value))

    seen = set()
    result = []
    for part in raw_parts:
        p = str(part).strip().lstrip("-*").strip().strip("/")
        if p and p.lower() not in {"none", "skip", "skip folders", "n/a"} and p not in seen:
            seen.add(p)
            result.append(p)
    return result

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
                from src.presentation.api import get_repository
                from src.application.use_cases.update_resource_use_case import UpdateResourceUseCase

                _ctx = _pending_state.context_memory
                _resource_type = _ctx.get("resource_type")
                _resource_id = _ctx.get("resource_id")
                _modifications = _ctx.get("modifications") or {}
                _target_site_id = _ctx.get("site_id") or site_id
                _resource_name = _ctx.get("resource_name") or "resource"

                try:
                    _repo = get_repository(user_token=raw_token)
                    _uc = UpdateResourceUseCase(_repo)
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
                    if isinstance(result, bool):
                        status_str = "completed successfully" if result else "failed. Please check permissions and try again"
                        success_icon = "✅" if result else "❌"
                        return ChatResponse(
                            intent="chat",
                            reply=f"{success_icon} The action on **{pending.resource_name}** {status_str}.",
                            session_id=session_id
                        )
                    return ChatResponse(
                        intent="chat",
                        reply=f"✅ Done — **{pending.resource_name}** action completed successfully.",
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
                    qsvc = data_query_service
                    if raw_token:
                        # Construct a user-scoped service here if needed,
                        # but for brevity we reuse the provided one and pass site_ids
                        pass 
                    
                    clar_result = await qsvc.query_data(
                        orig_q,
                        site_ids=[clar_site_id] if clar_site_id else site_ids,
                        user_login_name=user_login_name,
                        **page_ctx,
                    )
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

        original_enhanced_intent = detect_enhanced_intent(message)
        if original_enhanced_intent and not in_active_gathering:
            effective_message = message
            enhanced_intent = original_enhanced_intent
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
        if (_looks_like_sample_item_add or _looks_like_add_data_followup) and last_created_tuple and last_created_tuple[1] == "list":
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
                # Add personal identity if needed
                query_message = resolved_message
                
                # ... (Personal identity enrichment logic) ...
                
                # Execute query
                result_dto = await data_query_service.query_data(query_message, site_ids=site_ids, user_login_name=user_login_name, **page_ctx)
                
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
                q_source_list = getattr(result_dto, "source_list", None)
                q_source_rtype = getattr(result_dto, "source_resource_type", None) or "list"
                if q_source_list and q_source_rtype not in ("page", "site"):
                    await conversation_state.set_last_created(session_id, q_source_list, "library" if q_source_rtype == "library" else "list", site_id)

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
                    state, next_question, is_complete = gathering_service.process_answer(
                        session_id, resolved_message
                    )

                    if is_complete:
                        # All questions answered → build prompt from collected fields and provision
                        spec = state.get_current_spec()
                        collected = spec.collected_fields if spec else {}
                        resource_label = spec.resource_type.value if spec else "resource"

                        # Build a rich provisioning prompt from gathered fields
                        prompt_parts = [f"Create a {resource_label}"]
                        if collected.get("title"):
                            prompt_parts.append(f"called '{collected['title']}'")
                        if collected.get("description"):
                            prompt_parts.append(f"for {collected['description']}")
                        if collected.get("columns") and collected["columns"] != "AI_GENERATED":
                            prompt_parts.append(f"with columns: {collected['columns']}")
                        elif collected.get("columns") == "AI_GENERATED":
                            prompt_parts.append("with AI-generated columns")
                        if collected.get("template"):
                            prompt_parts.append(f"using template: {collected['template']}")
                        if collected.get("add_sample_data") and collected["add_sample_data"] not in (False, "No, I'll add data myself"):
                            prompt_parts.append("and add sample data")

                        provision_prompt = " ".join(prompt_parts)
                        logger.info("Gathering complete — provisioning with prompt: %s", provision_prompt)

                        # Mark gathering as complete
                        gathering_service.confirm_and_complete(session_id)

                        # Resolve target_site to actual site_id if provided
                        resolved_target_site_id = site_id
                        if collected.get("target_site") and collected["target_site"].strip():
                            target_site_name = collected["target_site"].strip()
                            try:
                                # Try to resolve the site name to a site ID
                                repo = get_repository(user_token=raw_token)
                                all_sites = await repo.get_all_sites()
                                matched_site = None
                                # Exact match first
                                for s in all_sites:
                                    if s.get("displayName", "").lower() == target_site_name.lower() or s.get("name", "").lower() == target_site_name.lower():
                                        matched_site = s
                                        break
                                # Partial match if no exact match
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
                                    repo = get_repository(user_token=raw_token)
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
                                                await repo.create_folder(lib_id, folder_name, parent, site_id=resolved_target_site_id)
                                                created.append(full_path)
                                            except Exception:
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
                                repo = get_repository(user_token=raw_token)
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
                                    repo = get_repository(user_token=raw_token)
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
                                                await repo.create_folder(lib_id, folder_name, parent, site_id=resolved_target_site_id)
                                                created.append(full_path)
                                            except Exception:
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
                        _fallback_repo = get_repository(user_token=raw_token)
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
                logger.warning("Chat response generation failed: %s", _chat_err)
                return ChatResponse(
                    intent="chat",
                    reply="Hi! I'm your SharePoint AI assistant. How can I help you today?",
                    session_id=session_id,
                )

