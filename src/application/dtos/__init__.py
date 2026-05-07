"""Application DTOs (Data Transfer Objects)."""

from dataclasses import dataclass, field
from typing import List, Any, Dict


@dataclass
class SiteDTO:
    """DTO for SharePoint site."""
    title: str
    description: str
    name: str = ""
    template: str = "sts"
    owner_email: str = ""
    action: str = "CREATE"


@dataclass
class ColumnDTO:
    """DTO for SharePoint column."""
    name: str
    type: str
    required: bool
    choices: List[str] = field(default_factory=list)
    lookup_list: str = ""
    term_set_id: str = ""


@dataclass
class WebPartDTO:
    """DTO for SharePoint web part."""
    type: str
    properties: Dict[str, Any]


@dataclass
class CustomWebPartCodeDTO:
    """DTO for custom SPFx React web part code."""
    component_name: str
    tsx_content: str
    scss_content: str


@dataclass
class TermSetDTO:
    """DTO for Term Set."""
    name: str
    terms: List[str]
    group_name: str
    action: str = "CREATE"


@dataclass
class ContentTypeDTO:
    """DTO for Content Type."""
    name: str
    description: str
    parent_type: str
    columns: List[str]
    action: str = "CREATE"


@dataclass
class SPViewDTO:
    """DTO for SharePoint List View."""
    title: str
    target_list_title: str
    columns: List[str]
    row_limit: int
    query: str
    action: str = "CREATE"


@dataclass
class WorkflowScaffoldDTO:
    """DTO for Workflow Scaffolding."""
    name: str
    trigger_type: str
    target_list_title: str
    actions: List[str]
    action: str = "CREATE"


@dataclass
class ListDTO:
    """DTO for SharePoint list."""
    title: str
    description: str
    columns: List[ColumnDTO]
    content_types: List[str] = field(default_factory=list)
    seed_data: List[Dict[str, Any]] = field(default_factory=list)
    action: str = "CREATE"


@dataclass
class PageDTO:
    """DTO for SharePoint page."""
    title: str
    webparts: List[WebPartDTO]
    action: str = "CREATE"


@dataclass
class DocumentLibraryDTO:
    """DTO for SharePoint Document Library."""
    title: str
    description: str
    content_types: List[str] = field(default_factory=list)
    seed_data: List[Dict[str, Any]] = field(default_factory=list)
    action: str = "CREATE"


@dataclass
class SharePointGroupDTO:
    """DTO for SharePoint Group with permission assignment."""
    name: str
    permission_level: str
    target_library_title: str = ""
    description: str = ""
    action: str = "CREATE"


@dataclass
class BlueprintDTO:
    """DTO for provisioning blueprint."""
    reasoning: str
    sites: List[SiteDTO] = field(default_factory=list)
    lists: List[ListDTO] = field(default_factory=list)
    pages: List[PageDTO] = field(default_factory=list)
    custom_components: List[CustomWebPartCodeDTO] = field(default_factory=list)
    document_libraries: List[DocumentLibraryDTO] = field(default_factory=list)
    groups: List[SharePointGroupDTO] = field(default_factory=list)
    term_sets: List[TermSetDTO] = field(default_factory=list)
    content_types: List[ContentTypeDTO] = field(default_factory=list)
    views: List[SPViewDTO] = field(default_factory=list)
    workflows: List[WorkflowScaffoldDTO] = field(default_factory=list)


@dataclass
class ProvisionResourcesRequestDTO:
    """Request DTO for provision resources command."""
    prompt: str
    user_email: str = ""
    user_login_name: str = ""


@dataclass
class ProvisionResourcesResponseDTO:
    """Response DTO for provision resources."""
    blueprint: BlueprintDTO
    created_sites: List[Dict[str, Any]] = field(default_factory=list)
    created_lists: List[Dict[str, Any]] = field(default_factory=list)
    created_pages: List[Dict[str, Any]] = field(default_factory=list)
    resource_links: List[str] = field(default_factory=list)
    created_document_libraries: List[Dict[str, Any]] = field(default_factory=list)
    deleted_document_libraries: List[Dict[str, Any]] = field(default_factory=list)
    created_groups: List[Dict[str, Any]] = field(default_factory=list)
    created_term_sets: List[Dict[str, Any]] = field(default_factory=list)
    created_content_types: List[Dict[str, Any]] = field(default_factory=list)
    created_views: List[Dict[str, Any]] = field(default_factory=list)
    created_workflows: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class DataQueryCommand:
    """Command to execute a data intelligence query."""
    question: str


@dataclass
class DataQueryResponseDTO:
    """Response DTO for data intelligence queries."""
    answer: str
    data_summary: Dict[str, Any]
    source_list: str
    resource_link: str
    suggested_actions: List[str]
    # Site-context fields
    source_site_name: str = ""
    source_site_url: str = ""
    source_resource_type: str = ""  # "list" | "library" | ""
    sources: List[Dict[str, Any]] = field(default_factory=list)
    # Candidates emitted when a clarification question was returned, so the
    # presentation layer can store them in session for the next turn.
    clarification_candidates: List[Any] = field(default_factory=list)
