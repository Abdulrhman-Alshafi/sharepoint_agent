"""Query controller.

Delegates data queries to the DataQueryApplicationService.
"""

import logging
from typing import Dict, Any, List

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from src.infrastructure.rate_limiter import limiter
from src.presentation.api.dependencies import get_current_user
from src.presentation.api import get_data_query_service

logger = logging.getLogger(__name__)
router = APIRouter()

class QueryRequest(BaseModel):
    question: str
    site_id: str

@router.post("/", response_model=Dict[str, Any])
@limiter.limit("20/minute")
async def execute_query(
    request: Request,
    body: QueryRequest,
    current_user: Dict = Depends(get_current_user),
    data_query_service = Depends(get_data_query_service)
) -> Dict[str, Any]:
    """Execute a data query."""
    result = await data_query_service.query_data(
        body.question, site_ids=[body.site_id]
    )
    return {"status": "success", "data": {"answer": result.answer, "sources": result.sources}}
