"""File controller.

Delegates file management logic to the file_orchestrator / FileOperationsUseCase.
"""

import logging
from typing import Dict, Any, List

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from src.infrastructure.rate_limiter import limiter
from src.presentation.api.dependencies import get_current_user
from src.presentation.api import get_drive_repository, get_permission_repository
from src.application.use_cases.file_operations_use_case import FileOperationsUseCase

logger = logging.getLogger(__name__)
router = APIRouter()

class FileQueryRequest(BaseModel):
    query: str
    site_id: str
    library_id: str

@router.post("/query", response_model=Dict[str, Any])
@limiter.limit("20/minute")
async def query_files(
    request: Request,
    body: FileQueryRequest,
    current_user: Dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """Query and filter files via natural language."""
    raw_token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip() or None
    drive_repo = get_drive_repository(user_token=raw_token)
    perm_repo = get_permission_repository(user_token=raw_token)
    use_case = FileOperationsUseCase(drive_repo, perm_repo)
    return await use_case.query_files(body.site_id, body.library_id, body.query)
