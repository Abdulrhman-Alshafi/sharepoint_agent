"""Provisioning controller.

Delegates to the ProvisioningApplicationService.
"""

import logging
from typing import Dict, Any, List

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from src.infrastructure.rate_limiter import limiter
from src.presentation.api.dependencies import get_current_user, get_current_user_token
from src.presentation.api import get_provisioning_service

logger = logging.getLogger(__name__)
router = APIRouter()

class ProvisionRequest(BaseModel):
    prompt: str
    site_id: str

@router.post("/", response_model=Dict[str, Any])
@limiter.limit("10/minute")
async def provision_resources(
    request: Request,
    body: ProvisionRequest,
    current_user: str = Depends(get_current_user),
    user_token: str = Depends(get_current_user_token),
    provisioning_service = Depends(get_provisioning_service)
) -> Dict[str, Any]:
    """Execute direct provisioning from a prompt."""
    result = await provisioning_service.provision_resources(
        body.prompt, target_site_id=body.site_id, user_email=current_user, user_token=user_token
    )
    return {"status": "success", "data": result}
