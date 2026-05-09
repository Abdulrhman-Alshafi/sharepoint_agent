"""Query and validation result entities."""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class QuerySource:
    """Represents a single source that contributed to a query answer."""
    type:  str   # "page" | "list" | "library" | "section"
    id:    str
    title: str = ""
    url:   str = ""


@dataclass
class DataQueryResult:
    """Entity representing the result of a data intelligence query."""
    answer: str
    data_summary: Dict[str, Any] = field(default_factory=dict)
    source_list: str = ""
    resource_link: str = ""
    suggested_actions: List[str] = field(default_factory=list)
    # Site-context fields (populated whenever a specific resource is queried)
    source_site_id: str = ""
    source_site_name: str = ""
    source_site_url: str = ""
    source_resource_type: str = ""  # "list" | "library" | ""
    sources: List[QuerySource] = field(default_factory=list)
    # When needs_clarification is True, holds the ResourceCandidate list so the
    # chat layer can store them in session and resolve the next user reply.
    clarification_candidates: List[Any] = field(default_factory=list)


@dataclass
class PromptValidationResult:
    """Entity representing the result of pre-blueprint prompt validation."""
    is_valid: bool
    risk_level: str = "low"  # "low", "medium", "high"
    warnings: List[str] = field(default_factory=list)
    rejection_reason: str = ""
