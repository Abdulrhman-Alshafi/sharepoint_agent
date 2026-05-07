"""Document library entities."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime
from src.domain.entities.core import ActionType


@dataclass
class DocumentLibrary:
    """Entity representing a SharePoint Document Library."""
    title: str
    description: str
    content_types: List[str] = field(default_factory=list)
    seed_data: List[Dict[str, Any]] = field(default_factory=list)
    library_id: str = field(default="")
    action: ActionType = field(default=ActionType.CREATE)

    def __post_init__(self):
        if not self.title or len(self.title.strip()) == 0:
            raise ValueError("Document library title cannot be empty")

    def to_graph_api_payload(self) -> Dict[str, Any]:
        """Convert to Microsoft Graph API payload for document library creation."""
        return {
            "displayName": self.title,
            "description": self.description,
            "list": {"template": "documentLibrary"},
        }


@dataclass
class LibraryItem:
    """Entity representing a file in a SharePoint Document Library."""
    name: str
    item_id: str
    library_id: str
    drive_id: str
    size: int  # bytes
    created_datetime: Optional[datetime] = None
    modified_datetime: Optional[datetime] = None
    created_by: Optional[str] = None
    modified_by: Optional[str] = None
    web_url: Optional[str] = None
    download_url: Optional[str] = None
    file_type: Optional[str] = None  # extension
    mime_type: Optional[str] = None
    custom_metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.name or len(self.name.strip()) == 0:
            raise ValueError("File name cannot be empty")
        if self.size < 0:
            raise ValueError("File size cannot be negative")
    
    @property
    def size_mb(self) -> float:
        """Get file size in megabytes."""
        return self.size / (1024 * 1024)

    @property
    def is_parseable(self) -> bool:
        """Check if file type can be parsed for content extraction."""
        parseable_extensions = {'.pdf', '.docx', '.doc', '.xlsx', '.xls', '.txt', '.csv'}
        if self.file_type:
            return self.file_type.lower() in parseable_extensions
        return False

    @classmethod
    def from_graph_api_response(
        cls,
        data: Dict[str, Any],
        library_id: str,
        drive_id: str,
    ) -> "LibraryItem":
        """Create a LibraryItem from a Microsoft Graph API drive item response."""
        def _parse_dt(s: Optional[str]) -> Optional[datetime]:
            if s:
                try:
                    return datetime.fromisoformat(s.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    return None
            return None

        name: str = data.get("name", "")
        file_type: Optional[str] = None
        if "." in name:
            file_type = "." + name.rsplit(".", 1)[-1]

        created_by: Optional[str] = None
        cb = data.get("createdBy", {})
        if cb and "user" in cb:
            created_by = cb["user"].get("displayName")

        modified_by: Optional[str] = None
        mb = data.get("lastModifiedBy", {})
        if mb and "user" in mb:
            modified_by = mb["user"].get("displayName")

        file_info = data.get("file") or {}
        mime_type: Optional[str] = file_info.get("mimeType")

        return cls(
            name=name,
            item_id=data.get("id", ""),
            library_id=library_id,
            drive_id=drive_id,
            size=data.get("size", 0),
            created_datetime=_parse_dt(data.get("createdDateTime")),
            modified_datetime=_parse_dt(data.get("lastModifiedDateTime")),
            created_by=created_by,
            modified_by=modified_by,
            web_url=data.get("webUrl"),
            download_url=data.get("@microsoft.graph.downloadUrl"),
            file_type=file_type,
            mime_type=mime_type,
        )
