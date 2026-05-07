"""Schemas for the chat API."""

from typing import Literal, List, Optional, Dict, Any
from pydantic import BaseModel, Field, validator


class SiteContextPayload(BaseModel):
    id: str
    url: str
    name: Optional[str] = None


class PageContextPayload(BaseModel):
    id: Optional[str] = None   # Graph GUID if available
    url: str
    title: Optional[str] = None


class RequestContext(BaseModel):
    site: SiteContextPayload
    page: PageContextPayload


class ChatRequest(BaseModel):
    """Single request schema consumed by the frontend for every message."""
    message: str = Field(..., min_length=1, max_length=2000, description="The user's raw message")
    history: Optional[List[Dict[str, Any]]] = Field(None, description="Recent conversation history")
    session_id: Optional[str] = Field(None, description="Session ID for multi-turn conversations")
    site_id: Optional[str] = Field(None, description="Target SharePoint site ID (uses default if omitted)")
    site_ids: Optional[List[str]] = Field(None, description="Optional list of site IDs to scope cross-resource discovery")
    pending_file_id: Optional[str] = Field(None, description="Temp file ID from a previous upload-without-library response")
    context: Optional[RequestContext] = None

class ChatResponse(BaseModel):
    """
    Unified response.  Every field except `intent` and `reply` is
    optional — the frontend uses `intent` to know which extras are present.
    """
    intent: Literal["query", "provision", "chat", "analyze", "update", "delete", "item_operation", "site_operation", "file_operation"]
    reply: str

    # ── query extras ────────────────────────────────────────
    source_list: Optional[str] = None
    resource_link: Optional[str] = None
    data_summary: Optional[Dict[str, Any]] = None
    suggested_actions: Optional[List[str]] = None
    # Site context
    source_site_name: Optional[str] = None
    source_site_url: Optional[str] = None
    source_resource_type: Optional[str] = None  # "list" | "library" | None
    sources: Optional[List[Dict[str, Any]]] = None  # [{type, id, title, url}]

    # ── provision extras ────────────────────────────────────
    resource_links: Optional[List[str]] = None
    blueprint: Optional[Dict[str, Any]] = None

    # ── validation extras ───────────────────────────────────
    requires_confirmation: Optional[bool] = None
    warnings: Optional[List[str]] = None

    # ── interactive gathering extras ────────────────────────
    requires_input: Optional[bool] = None  # True if waiting for user answer
    session_id: Optional[str] = None  # Session ID for conversation continuity
    question_prompt: Optional[str] = None  # The question being asked
    current_field: Optional[str] = None  # Field name being collected
    field_type: Optional[str] = None  # Type of input expected
    field_options: Optional[List[str]] = None  # Options for choice questions
    progress: Optional[str] = None  # "Step 2 of 5" or "40%" format
    specification_preview: Optional[Dict[str, Any]] = None  # Collected fields so far
    quick_suggestions: Optional[List[str]] = None  # Common/suggested answers

    @validator("quick_suggestions", pre=True, always=True)
    def _strip_empty_suggestions(cls, v):  # noqa: N805
        if v is None:
            return None
        filtered = [s for s in v if s and s.strip()]
        return filtered or None
    
    # ── ENHANCED: preview & analysis extras ─────────────────
    preview: Optional[Dict[str, Any]] = None  # ProvisioningPreview data
    preview_type: Optional[str] = None  # "create", "update", "delete"
    analysis: Optional[Dict[str, Any]] = None  # ContentAnalysis data
    deletion_impact: Optional[Dict[str, Any]] = None  # DeletionImpact data
    web_part_decision: Optional[Dict[str, Any]] = None  # WebPartDecision data
    context_summary: Optional[Dict[str, Any]] = None  # Auto-filled fields from context
    confirmation_text: Optional[str] = None  # Required confirmation text for high-risk deletions
    pending_file_id: Optional[str] = None  # Temp file ID waiting for a library choice

    # ── Error context ─────────────────────────────────────────
    error_code: Optional[str] = None          # Machine-readable: "PERMISSION_DENIED", "TIMEOUT", etc.
    error_category: Optional[str] = None      # "auth" | "permission" | "validation" | "service" | "internal"
    recovery_hint: Optional[str] = None       # User-friendly: "Please refresh and sign in again"
    correlation_id: Optional[str] = None      # For support: "abc123def456"
