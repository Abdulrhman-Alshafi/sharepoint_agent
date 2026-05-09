"""Chat controller — HTTP endpoints for the unified chat gateway.

Provides the POST / and POST /upload endpoints. All business logic is
delegated to the ChatOrchestrator and UploadService.
"""

import logging
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status

from src.infrastructure.rate_limiter import limiter
from src.infrastructure.config import settings
from src.presentation.api import get_provisioning_service, get_data_query_service, get_intent_classifier, ServiceContainer, get_repository
from src.presentation.api.dependencies import get_current_user
from src.infrastructure.services.user_status_service import require_active_user
from src.presentation.api.schemas.chat_schemas import ChatRequest, ChatResponse
from src.presentation.api.orchestrators.chat_orchestrator import ChatOrchestrator

# Services
from src.presentation.api.services.validation_service import extract_raw_token, extract_page_context, extract_site_id, extract_user_info
from src.presentation.api.services import conversation_state
from src.presentation.api.services.upload_service import validate_uploads, format_pending_upload_prompt, format_upload_response
from src.presentation.api.services.library_matcher import match_library_from_message, extract_named_library

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post(
    "/upload",
    response_model=ChatResponse,
    summary="Chat File Upload",
    description="Upload a file and optionally specify a SharePoint library via a natural-language message."
)
@limiter.limit("10/minute")
async def chat_upload(
    request: Request,
    response: Response,
    files: Optional[List[UploadFile]] = File(None, description="One or more files (multi-file field name)"),
    file: Optional[UploadFile] = File(None, description="Single file (legacy field name)"),
    message: Optional[str] = Form(None, description="Optional instruction, e.g. 'add to Documents'"),
    history: Optional[str] = Form(None, description="JSON array of conversation history"),
    session_id: Optional[str] = Form(None),
    current_user: Dict = Depends(get_current_user),
    _active: bool = Depends(require_active_user),
) -> ChatResponse:
    """Handle file uploads via chat."""
    from src.infrastructure.correlation import get_correlation_id
    cid = get_correlation_id()
    response.headers["X-Correlation-ID"] = cid
    response.headers["X-Request-ID"] = cid
    
    sid = session_id or str(uuid.uuid4())
    raw_token = extract_raw_token(request)
    
    # 1. Collect files
    all_uploads: List[UploadFile] = list(files or [])
    if file is not None:
        all_uploads.append(file)
    if not all_uploads:
        return ChatResponse(
            intent="file_operation", session_id=sid,
            reply="❌ No file received. Please attach a file before sending.",
        )

    # 2. Read file bytes and construct upload tuples
    raw_files = []
    for upload in all_uploads:
        fbytes = await upload.read()
        raw_files.append((upload.filename, fbytes, upload.content_type))
        
    # 3. Validate uploads
    validated_files, errors = validate_uploads(raw_files)
    if not validated_files:
        return ChatResponse(
            intent="file_operation", session_id=sid,
            reply="\n".join(errors) if errors else "❌ No valid files were received.",
        )

    # 4. Fetch libraries
    repo = get_repository(user_token=raw_token)
    try:
        libraries = await repo.get_all_document_libraries()
    except Exception as lib_err:
        logger.error("chat_upload: failed to list libraries: %s", lib_err)
        libraries = []

    if not libraries:
        return ChatResponse(
            intent="file_operation", session_id=sid,
            reply="❌ No document libraries found. Make sure you have access to at least one SharePoint document library.",
        )

    # 5. Resolve library
    from src.presentation.api.services.library_matcher import find_best_library
    target_library = None
    named_library = None
    
    if message and message.strip():
        target_library = find_best_library(message.strip(), libraries)
        if target_library is None:
            named_library = extract_named_library(message.strip())

    if target_library is None and len(libraries) == 1:
        target_library = libraries[0]

    # 6. Upload immediately if library is known
    if target_library is not None:
        lib_id = target_library.get("id") or target_library.get("driveId", "")
        lib_name = target_library.get("displayName") or target_library.get("name", "Library")
        
        from src.presentation.api.services.upload_service import execute_uploads
        success_lines, fail_lines, last_url = await execute_uploads(validated_files, lib_id, lib_name, repo)
        
        if success_lines:
            reply_msg = format_upload_response(success_lines, fail_lines, lib_name, pre_errors=errors)
            return ChatResponse(
                intent="file_operation",
                session_id=sid,
                reply=reply_msg,
                resource_link=last_url or None,
                suggested_actions=["Upload another file", f"List files in {lib_name}"],
            )

    # 7. Library unclear — store pending and ask
    pending_id = await conversation_state.store_pending_files(validated_files)
    intro, lib_names = format_pending_upload_prompt(validated_files, libraries, named_library, message)
    
    return ChatResponse(
        intent="file_operation",
        session_id=sid,
        reply=intro,
        requires_input=True,
        question_prompt="Which library would you like to upload this file to?",
        field_type="choice",
        field_options=lib_names,
        quick_suggestions=[f"Upload to {n}" for n in lib_names],
        pending_file_id=pending_id,
    )


@router.post(
    "/",
    response_model=ChatResponse,
    summary="Unified Chat Gateway",
    description="Single endpoint for all chat interactions - automatically routes based on intent"
)
@limiter.limit("20/minute")
async def chat(
    request: Request,
    response: Response,
    body: ChatRequest,
    current_user: Dict = Depends(get_current_user),
    _active: bool = Depends(require_active_user),
    intent_classifier = Depends(get_intent_classifier),
    provisioning_service = Depends(get_provisioning_service),
    data_query_service = Depends(get_data_query_service)
) -> ChatResponse:
    """Unified chat gateway."""
    from src.infrastructure.correlation import get_correlation_id
    cid = get_correlation_id()
    response.headers["X-Correlation-ID"] = cid
    response.headers["X-Request-ID"] = cid
    
    try:
        session_id = body.session_id or str(uuid.uuid4())
        site_id = extract_site_id(body)
        page_ctx = extract_page_context(body)
        raw_token = extract_raw_token(request)
        user_email, user_login_name = extract_user_info(current_user)
        
        # Extract pending file logic (if file was pending and user replies with library choice)
        if body.pending_file_id:
            pending_files = await conversation_state.get_pending_files(body.pending_file_id)
            if not pending_files:
                return ChatResponse(
                    intent="file_operation", session_id=session_id,
                    reply="⏰ The file(s) you uploaded earlier have expired. Please attach the file(s) again.",
                )
                
            repo = get_repository(user_token=raw_token, site_id=site_id)
            try:
                libraries = await repo.get_all_document_libraries(site_id=site_id)
            except Exception:
                libraries = []
                
            target = match_library_from_message(body.message, libraries)
            if target is None and libraries:
                lib_names = [lib.get("displayName") or lib.get("name", "?") for lib in libraries[:8]]
                return ChatResponse(
                    intent="file_operation", session_id=session_id,
                    reply=f"I couldn't find that library. Please choose one of: {', '.join(lib_names)}",
                    requires_input=True,
                    field_type="choice",
                    field_options=lib_names,
                    quick_suggestions=[f"Upload to {n}" for n in lib_names],
                    pending_file_id=body.pending_file_id,
                )
                
            lib_id = target.get("id") or target.get("driveId", "") if target else ""
            lib_name = target.get("displayName") or target.get("name", "Library") if target else "Library"
            
            from src.presentation.api.services.upload_service import execute_uploads
            success_lines, fail_lines, last_url = await execute_uploads(pending_files, lib_id, lib_name, repo)
            await conversation_state.remove_pending_files(body.pending_file_id)
            
            reply_msg = format_upload_response(success_lines, fail_lines, lib_name)
            return ChatResponse(
                intent="file_operation", session_id=session_id,
                reply=reply_msg, resource_link=last_url or None,
                suggested_actions=["Upload another file", f"List files in {lib_name}"],
                pending_file_id=body.pending_file_id if fail_lines else None,
            )

        # Delegate to orchestrator
        return await ChatOrchestrator.process_chat(
            message=body.message,
            history=body.history or [],
            session_id=session_id,
            site_id=site_id,
            site_ids=body.site_ids or [],
            page_ctx=page_ctx,
            raw_token=raw_token,
            user_email=user_email,
            user_login_name=user_login_name,
            intent_classifier=intent_classifier,
            provisioning_service=provisioning_service,
            data_query_service=data_query_service,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unexpected chat error: %s", e, exc_info=True)
        from src.infrastructure.correlation import get_correlation_id
        cid = get_correlation_id()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred. Please try again.",
                    "recovery_hint": "If this persists, please contact your administrator.",
                    "correlation_id": cid,
                }
            },
            headers={"X-Request-ID": cid},
        )
