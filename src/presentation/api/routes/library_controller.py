"""Library controller.

Delegates library operations to the library_orchestrator / LibraryAnalysisUseCase.
"""

import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from src.infrastructure.rate_limiter import limiter
from src.presentation.api.dependencies import get_current_user
from src.presentation.api import get_repository, ServiceContainer
from src.application.use_cases.library_analysis_use_case import LibraryAnalysisUseCase

logger = logging.getLogger(__name__)
router = APIRouter()

class AnalyzeLibraryRequest(BaseModel):
    site_id: str
    library_name: str
    force_refresh: bool = False

@router.post("/analyze", response_model=Dict[str, Any])
@limiter.limit("10/minute")
async def analyze_library(
    request: Request,
    body: AnalyzeLibraryRequest,
    current_user: Dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """Analyze a library's metadata structure."""
    raw_token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip() or None
    repo = get_repository(user_token=raw_token)
    ai_client, ai_model = ServiceContainer.get_ai_client()
    
    use_case = LibraryAnalysisUseCase(repo, ai_client, ai_model)
    return await use_case.analyze_library(
        site_id=body.site_id,
        library_name=body.library_name,
        force_refresh=body.force_refresh
    )
