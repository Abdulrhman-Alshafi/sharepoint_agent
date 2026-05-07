"""HTTP Request/Response schemas for API endpoints."""

from pydantic import BaseModel, Field
from typing import List, Dict, Any
from enum import Enum


class ActionType(str, Enum):
    """Supported lifecycle actions."""
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


class ColumnSchema(BaseModel):
    """Schema for SharePoint column."""
    name: str
    type: str
    required: bool


class WebPartSchema(BaseModel):
    """Schema for SharePoint web part."""
    type: str
    properties: Dict[str, Any]


class CustomWebPartCodeSchema(BaseModel):
    """Schema for custom SPFx React web part code."""
    component_name: str
    tsx_content: str
    scss_content: str


class ListSchema(BaseModel):
    """Schema for SharePoint list."""
    title: str
    description: str
    columns: List[ColumnSchema]
    action: ActionType = ActionType.CREATE


class PageSchema(BaseModel):
    """Schema for SharePoint page."""
    title: str
    webparts: List[WebPartSchema]
    action: ActionType = ActionType.CREATE


class BlueprintSchema(BaseModel):
    """Schema for provisioning blueprint."""
    reasoning: str
    lists: List[ListSchema]
    pages: List[PageSchema]
    custom_components: List[CustomWebPartCodeSchema] = Field(default_factory=list)


class ProvisionRequest(BaseModel):
    """Request schema for provision endpoint."""
    prompt: str = Field(..., min_length=1, max_length=2000, description="Natural language description of resources to provision")


class ProvisionResponse(BaseModel):
    """Response schema for provision endpoint."""
    blueprint: BlueprintSchema
    created_lists: List[Dict[str, Any]]
    created_pages: List[Dict[str, Any]]
    resource_links: List[str] = Field(default_factory=list)


class QueryRequest(BaseModel):
    """Request schema for data intelligence query."""
    question: str = Field(..., min_length=1, max_length=1000, description="The user's question about SharePoint data")
    site_ids: List[str] = Field(default_factory=list, description="Optional list of site IDs to scope cross-resource discovery")


class QueryResponse(BaseModel):
    """Response schema for data intelligence query."""
    answer: str
    data_summary: Dict[str, Any]
    source_list: str
    resource_link: str
    suggested_actions: List[str]
    # Site context fields
    source_site_name: str = ""
    source_site_url: str = ""
    source_resource_type: str = ""  # "list" | "library" | ""
