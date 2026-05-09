"""Schemas for blueprint generation from AI."""

from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional, List, Dict, Any
from src.domain.entities import ActionType

class SPColumnModel(BaseModel):
    name: str
    type: Literal[
        "text", "note", "number", "dateTime", "choice", "lookup",
        "managed_metadata", "boolean", "personOrGroup", "currency",
        "hyperlinkOrPicture", "geolocation"
    ]
    required: bool = False
    choices: List[str] = []
    lookup_list: Optional[str] = None
    term_set_id: Optional[str] = None

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value: Any) -> Any:
        """Normalize common LLM aliases to supported SharePoint column types."""
        if not isinstance(value, str):
            return value

        raw = value.strip()
        key = raw.lower().replace(" ", "").replace("_", "").replace("-", "")

        aliases = {
            "text": "text",
            "string": "text",
            "singleline": "text",
            "singlelinetext": "text",
            "note": "note",
            "multiline": "note",
            "multilinetext": "note",
            "textarea": "note",
            "number": "number",
            "int": "number",
            "integer": "number",
            "float": "number",
            "decimal": "number",
            "date": "dateTime",
            "datetime": "dateTime",
            "dateandtime": "dateTime",
            "choice": "choice",
            "lookup": "lookup",
            "managedmetadata": "managed_metadata",
            "taxonomy": "managed_metadata",
            "termset": "managed_metadata",
            "boolean": "boolean",
            "bool": "boolean",
            "yesno": "boolean",
            "person": "personOrGroup",
            "people": "personOrGroup",
            "user": "personOrGroup",
            "personorgroup": "personOrGroup",
            "currency": "currency",
            "url": "hyperlinkOrPicture",
            "link": "hyperlinkOrPicture",
            "hyperlink": "hyperlinkOrPicture",
            "picture": "hyperlinkOrPicture",
            "hyperlinkorpicture": "hyperlinkOrPicture",
            "geolocation": "geolocation",
        }

        return aliases.get(key, raw)

class SPListModel(BaseModel):
    title: str
    description: str = ""
    columns: List[SPColumnModel]  # Required - no default, AI must provide columns
    content_types: List[str] = []
    seed_data: List[Dict[str, Any]] = []
    action: ActionType = ActionType.CREATE

class WebPartModel(BaseModel):
    type: str
    properties: Dict[str, Any]
    id: Optional[str] = None

class SPPageModel(BaseModel):
    title: str
    webparts: List[WebPartModel] = Field(default_factory=list, min_length=1,
        description="Every page MUST have at least one webpart. Use a Text webpart with relevant content if nothing else applies.")
    action: ActionType = ActionType.CREATE

class CustomWebPartCodeModel(BaseModel):
    component_name: str
    tsx_content: str
    scss_content: str

class DocumentLibraryModel(BaseModel):
    title: str
    description: str = ""
    content_types: List[str] = []
    seed_data: List[Dict[str, Any]] = []
    action: ActionType = ActionType.CREATE

class SharePointGroupModel(BaseModel):
    name: str
    description: str = ""
    permission_level: str = "Read"  # Read | Contribute | Edit | Full Control
    target_library_title: str = ""
    action: ActionType = ActionType.CREATE

class TermSetModel(BaseModel):
    name: str
    terms: List[str]
    group_name: str = "Default Group"
    action: ActionType = ActionType.CREATE

class ContentTypeModel(BaseModel):
    name: str
    description: str
    parent_type: str = "Item"
    columns: List[str] = []
    action: ActionType = ActionType.CREATE

class SPViewModel(BaseModel):
    title: str
    target_list_title: str
    columns: List[str]
    row_limit: int = 30
    query: str = ""
    action: ActionType = ActionType.CREATE

class WorkflowScaffoldModel(BaseModel):
    name: str
    trigger_type: str
    target_list_title: str
    actions: List[str] = []
    action: ActionType = ActionType.CREATE

class SPSiteModel(BaseModel):
    title: str
    description: str = ""
    name: str = ""
    template: str = "sts"
    owner_email: str = ""
    action: ActionType = ActionType.CREATE

class ProvisioningBlueprintModel(BaseModel):
    reasoning: str
    sites: List[SPSiteModel] = []
    lists: List[SPListModel] = []
    pages: List[SPPageModel] = []
    custom_components: List[CustomWebPartCodeModel] = []
    document_libraries: List[DocumentLibraryModel] = []
    groups: List[SharePointGroupModel] = []
    term_sets: List[TermSetModel] = []
    content_types: List[ContentTypeModel] = []
    views: List[SPViewModel] = []
    workflows: List[WorkflowScaffoldModel] = []
