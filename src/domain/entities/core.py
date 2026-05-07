"""Core domain entities for SharePoint resources."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from src.domain.value_objects import SPColumn, WebPart

if TYPE_CHECKING:
    from src.domain.entities.document import DocumentLibrary
    from src.domain.entities.security import SharePointGroup
    from src.domain.entities.enterprise import TermSet, ContentType, SPView, WorkflowScaffold


class ActionType(str, Enum):
    """Supported lifecycle actions for SharePoint resources."""
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


class SPPermissionMask(str, Enum):
    """Common SharePoint BasePermissions types."""
    VIEW_LIST_ITEMS = "ViewListItems"
    ADD_LIST_ITEMS = "AddListItems"
    EDIT_LIST_ITEMS = "EditListItems"
    DELETE_LIST_ITEMS = "DeleteListItems"
    MANAGE_LISTS = "ManageLists"
    MANAGE_WEB = "ManageWeb"
    FULL_MASK = "FullMask"


@dataclass
class SPSite:
    """Entity representing a SharePoint site."""
    title: str
    description: str
    name: str = field(default="")  # URL name. Graph API uses this.
    template: str = field(default="teamSite")  # teamSite | communicationSite | sts (legacy) | sitepagepublishing (legacy)
    owner_email: str = field(default="")
    site_id: str = field(default="")
    action: ActionType = field(default=ActionType.CREATE)

    def __post_init__(self):
        if not self.title or len(self.title.strip()) == 0:
            raise ValueError("Site title cannot be empty")
        valid_templates = ["sts", "sitepagepublishing", "teamSite", "communicationSite"]
        if self.template not in valid_templates:
            raise ValueError(f"Site template must be one of {valid_templates}")



@dataclass
class SPList:
    """Entity representing a SharePoint list."""
    title: str
    description: str
    columns: List[SPColumn]
    content_types: List[str] = field(default_factory=list)
    seed_data: List[Dict[str, Any]] = field(default_factory=list)
    template: str = field(default="genericList")  # Added: template support (genericList, tasks, calendar, etc.)
    list_id: str = field(default="")
    item_count: int = field(default=0)
    action: ActionType = field(default=ActionType.CREATE)

    def __post_init__(self):
        if not self.title or len(self.title.strip()) == 0:
            raise ValueError("List title cannot be empty")
        # Columns are only required for CREATE / UPDATE, not DELETE
        if self.action != ActionType.DELETE:
            if not self.columns or len(self.columns) == 0:
                raise ValueError("List must have at least one column")

    def get_required_columns(self) -> List[SPColumn]:
        """Get all required columns in this list."""
        return [col for col in self.columns if col.required]

    def to_graph_api_payload(self) -> Dict[str, Any]:
        """Convert to Microsoft Graph API payload for list creation."""
        _type_map: Dict[str, str] = {
            "text": "text",
            "note": "text",
            "number": "number",
            "dateTime": "dateTime",
            "boolean": "boolean",
            "lookup": "lookup",
            "managed_metadata": "term",
            "currency": "currency",
            "personOrGroup": "personOrGroup",
            "hyperlinkOrPicture": "hyperlinkOrPicture",
            "geolocation": "geolocation",
            "choice": "choice",
        }
        columns = []
        for col in self.columns:
            if col.name == "Title":
                continue
            type_key = _type_map.get(col.type, col.type)
            col_payload: Dict[str, Any] = {"name": col.name, "required": col.required}
            if type_key == "choice":
                choice_obj: Dict[str, Any] = {}
                if col.choices:
                    choice_obj["choices"] = col.choices
                col_payload["choice"] = choice_obj
            else:
                col_payload[type_key] = {}
            columns.append(col_payload)
        return {
            "displayName": self.title,
            "description": self.description,
            "list": {"template": self.template},
            "columns": columns,
        }


@dataclass
class SPPage:
    """Entity representing a SharePoint page."""
    title: str
    webparts: List[WebPart]
    page_id: str = field(default="")
    layout: str = field(default="article")  # article | home | singleWebPartApp
    action: ActionType = field(default=ActionType.CREATE)

    def __post_init__(self):
        if not self.title or len(self.title.strip()) == 0:
            raise ValueError("Page title cannot be empty")
        # Webparts are only required for CREATE / UPDATE, not DELETE
        if self.action != ActionType.DELETE:
            if not self.webparts or len(self.webparts) == 0:
                raise ValueError("Page must have at least one web part")

    def to_graph_api_payload(self) -> Dict[str, Any]:
        """Convert to Microsoft Graph API canvas layout payload."""
        webpart_items = []
        for wp in self.webparts:
            item: Dict[str, Any] = {}
            if wp.id:
                item["id"] = wp.id
            if wp.type in ("text", "rte"):
                item["type"] = "rte"
                item["innerHtml"] = wp.properties.get("content", wp.properties.get("text", ""))
            else:
                item["type"] = "custom"
                item["customWebPart"] = {
                    "type": wp.type,
                    "properties": wp.properties,
                }
            webpart_items.append(item)
        return {
            "title": self.title,
            "canvasLayout": {
                "horizontalSections": [{
                    "columns": [{
                        "webparts": webpart_items
                    }]
                }]
            },
        }


@dataclass
class CustomWebPartCode:
    """Entity representing custom SPFx React web part source code."""
    component_name: str
    tsx_content: str
    scss_content: str
    action: ActionType = field(default=ActionType.CREATE)

    def __post_init__(self):
        if not self.component_name or len(self.component_name.strip()) == 0:
            raise ValueError("Component name cannot be empty")
        if not self.tsx_content or len(self.tsx_content.strip()) == 0:
            raise ValueError("tsx_content cannot be empty")
        if not self.scss_content or len(self.scss_content.strip()) == 0:
            raise ValueError("scss_content cannot be empty")


@dataclass
class ProvisioningBlueprint:
    """Entity representing a complete provisioning blueprint."""
    reasoning: str
    sites: List[SPSite] = field(default_factory=list)
    lists: List[SPList] = field(default_factory=list)
    pages: List[SPPage] = field(default_factory=list)
    custom_components: List[CustomWebPartCode] = field(default_factory=list)
    document_libraries: List[DocumentLibrary] = field(default_factory=list)
    groups: List[SharePointGroup] = field(default_factory=list)
    term_sets: List[TermSet] = field(default_factory=list)
    content_types: List[ContentType] = field(default_factory=list)
    views: List[SPView] = field(default_factory=list)
    workflows: List[WorkflowScaffold] = field(default_factory=list)

    def __post_init__(self):
        if not self.reasoning or len(self.reasoning.strip()) == 0:
            raise ValueError("Blueprint reasoning cannot be empty")
        if (
            not self.sites
            and not self.lists
            and not self.pages
            and not self.custom_components
            and not self.document_libraries
            and not self.groups
            and not self.term_sets
            and not self.content_types
        ):
            raise ValueError("Blueprint must have at least one resource to provision")

    def get_all_sites(self) -> List[SPSite]:
        """Get all sites in the blueprint."""
        return self.sites

    def get_all_lists(self) -> List[SPList]:
        """Get all lists in the blueprint."""
        return self.lists

    def get_all_pages(self) -> List[SPPage]:
        """Get all pages in the blueprint."""
        return self.pages

    def get_all_custom_components(self) -> List[CustomWebPartCode]:
        """Get all custom SPFx code components in the blueprint."""
        return self.custom_components

    def get_all_document_libraries(self) -> List[DocumentLibrary]:
        """Get all document libraries in the blueprint."""
        return self.document_libraries

    def get_all_groups(self) -> List[SharePointGroup]:
        """Get all SharePoint groups in the blueprint."""
        return self.groups

    def is_valid(self) -> bool:
        """Check if blueprint is valid for provisioning."""
        return (
            len(self.sites) > 0
            or len(self.lists) > 0
            or len(self.pages) > 0
            or len(self.custom_components) > 0
            or len(self.document_libraries) > 0
            or len(self.groups) > 0
            or len(self.term_sets) > 0
            or len(self.content_types) > 0
            or len(self.views) > 0
            or len(self.workflows) > 0
        )
