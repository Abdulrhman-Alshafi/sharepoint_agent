"""Schemas for prompt validation."""

from pydantic import BaseModel, field_validator, Field
from typing import Literal, List, Any

class ValidationModel(BaseModel):
    is_valid: bool = True
    risk_level: Literal["low", "medium", "high"] = "low"
    warnings: List[str] = Field(default_factory=list)
    rejection_reason: str = ""

    @field_validator("is_valid", mode="before")
    @classmethod
    def normalize_is_valid(cls, value: Any) -> Any:
        """Treat missing/null is_valid as True (permissive validator policy)."""
        if value is None:
            return True
        return bool(value)

    @field_validator("risk_level", mode="before")
    @classmethod
    def normalize_risk_level(cls, value: Any) -> Any:
        """Normalize empty strings or invalid values to 'low'."""
        if not value or (isinstance(value, str) and not value.strip()):
            return "low"
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in ("low", "medium", "high"):
                return normalized
            # Default to "low" for unrecognized values
            return "low"
        return value

    @field_validator("warnings", mode="before")
    @classmethod
    def normalize_warnings(cls, value: Any) -> List[str]:
        """Accept null/single-string warnings and normalize to list[str]."""
        if value is None:
            return []
        if isinstance(value, str):
            txt = value.strip()
            return [txt] if txt else []
        if isinstance(value, list):
            return [str(v).strip() for v in value if v is not None and str(v).strip()]
        return []

    @field_validator("rejection_reason", mode="before")
    @classmethod
    def normalize_rejection_reason(cls, value: Any) -> str:
        """Convert null rejection reason to empty string to avoid validation errors."""
        if value is None:
            return ""
        return str(value).strip()
