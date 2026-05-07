"""Schemas for prompt validation."""

from pydantic import BaseModel
from typing import Literal, List

class ValidationModel(BaseModel):
    is_valid: bool
    risk_level: Literal["low", "medium", "high"]
    warnings: List[str] = []
    rejection_reason: str = ""
