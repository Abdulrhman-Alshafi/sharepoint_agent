"""Domain value objects."""

from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional

from src.domain.value_objects.resource_candidate import ResourceCandidate

__all__ = ["SPColumn", "WebPart", "ColumnMapping", "ResourceCandidate"]


@dataclass(frozen=True)
class SPColumn:
    """Value object representing a SharePoint column."""
    name: str
    type: Literal[
        "text", "note", "number", "dateTime", "choice", "lookup", 
        "managed_metadata", "boolean", "currency", "personOrGroup", 
        "hyperlinkOrPicture", "geolocation"
    ]
    required: bool
    # For choice columns
    choices: list = field(default_factory=list)
    # For lookup columns
    lookup_list: Optional[str] = field(default=None)
    # For managed metadata
    term_set_id: Optional[str] = field(default=None)

    def __post_init__(self):
        if not self.name or len(self.name.strip()) == 0:
            raise ValueError("Column name cannot be empty")


@dataclass(frozen=True)
class WebPart:
    """Value object representing a SharePoint web part."""
    type: str
    properties: Dict[str, Any]
    id: Optional[str] = field(default=None)
    # Webpart type discriminator.
    # Supported: Text, Hero, Image, QuickLinks, News, People,
    #            List, DocumentLibrary, Events
    webpart_type: str = field(default="Text")

    def __post_init__(self):
        if not self.type or len(self.type.strip()) == 0:
            raise ValueError("WebPart type cannot be empty")


@dataclass(frozen=True)
class ColumnMapping:
    """Value object for column type mapping."""
    column_type: str
    graph_api_schema: Dict[str, Any]
