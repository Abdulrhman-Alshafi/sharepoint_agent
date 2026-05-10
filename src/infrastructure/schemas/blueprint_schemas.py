"""Schemas for blueprint generation from AI."""

import json

from pydantic import BaseModel, Field, field_validator, model_validator
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
            "term": "managed_metadata",
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
    properties: Dict[str, Any] = Field(default_factory=dict)
    id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_webpart_shape(cls, value: Any) -> Any:
        """Normalize webpart input from common AI variants.

        Handles cases where:
        - properties key is misspelled/aliased (property, props, config, ...)
        - properties is a JSON string instead of a dict
        """
        if not isinstance(value, dict):
            return value

        if "properties" not in value:
            for key in list(value.keys()):
                key_l = str(key).lower().strip()
                if key_l in {"property", "props", "config", "configuration"} or key_l.startswith("propert"):
                    value["properties"] = value[key]
                    break

        if "properties" not in value:
            known_top_level = {"type", "id", "order", "webpart_type", "webparttype"}
            inferred = {
                k: v for k, v in value.items()
                if str(k).lower().strip() not in known_top_level
            }
            value["properties"] = inferred if isinstance(inferred, dict) else {}

        props = value.get("properties")
        if props is None:
            value["properties"] = {}
            return value
        if isinstance(props, str):
            text = props.strip()
            if text:
                try:
                    parsed = json.loads(text)
                    value["properties"] = parsed if isinstance(parsed, dict) else {"content": text}
                except Exception:
                    value["properties"] = {"content": text}

        return value

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
    columns: List[SPColumnModel] = []
    content_types: List[str] = []
    seed_data: List[Dict[str, Any]] = []
    action: ActionType = ActionType.CREATE

    @field_validator("columns", mode="before")
    @classmethod
    def normalize_library_columns(cls, value: Any) -> Any:
        """Allow AI to provide library columns as strings or dict objects.

        Example accepted values:
        - ["Owner", "Review Date"]
        - ["Owner:personOrGroup", "Review Date:dateTime"]
        - [{"name": "Owner", "type": "personOrGroup"}]
        """
        if not isinstance(value, list):
            return value

        normalized: List[Dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                normalized.append(item)
                continue

            if isinstance(item, str):
                token = item.strip()
                if not token:
                    continue
                if ":" in token:
                    name, col_type = token.split(":", 1)
                    normalized.append({"name": name.strip(), "type": col_type.strip() or "text", "required": False})
                else:
                    normalized.append({"name": token, "type": "text", "required": False})

        return normalized

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

    @field_validator("columns", mode="before")
    @classmethod
    def normalize_columns(cls, value: Any) -> Any:
        """Allow column arrays from AI as either strings or dict objects.

        Example accepted inputs:
        - ["policy_owner", "review_date"]
        - [{"name": "policy_owner", "type": "personOrGroup"}, ...]
        """
        if not isinstance(value, list):
            return value

        normalized: List[str] = []
        for item in value:
            if isinstance(item, str):
                if item.strip():
                    normalized.append(item.strip())
                continue

            if isinstance(item, dict):
                name = item.get("name") or item.get("title") or item.get("column")
                if isinstance(name, str) and name.strip():
                    normalized.append(name.strip())

        return normalized

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
