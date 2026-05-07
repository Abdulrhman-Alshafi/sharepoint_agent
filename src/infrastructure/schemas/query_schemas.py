"""Schemas for RAG data query AI operations."""

from pydantic import BaseModel, field_validator
from typing import List, Optional, Dict, Any
from enum import Enum


class QueryIntent(str, Enum):
    """Types of query intents the system can handle."""
    METADATA_COUNT = "metadata_count"          # Count resources (how many pages, lists, etc.)
    METADATA_DESCRIBE = "metadata_describe"     # Describe structure/information 
    FILTERED_META = "filtered_meta"            # Filtered list of resources (e.g., "all libraries", "HR lists")
    FULL_META = "full_meta"                    # Show all resources (only when explicitly asked)
    SPECIFIC_DATA = "specific_data"            # Query data within a specific list
    SEARCH = "search"                          # Search across SharePoint content
    # New document library intents
    LIBRARY_CONTENT = "library_content"        # Query about files in a library (count, list files)
    DOCUMENT_SEARCH = "document_search"        # Search for specific documents
    DATA_EXTRACTION = "data_extraction"        # Extract and answer questions from document content
    LIBRARY_COMPARISON = "library_comparison"  # Compare two or more libraries
    CONTENT_SUMMARY = "content_summary"        # Summarize library content and themes
    PAGE_CONTENT = "page_content"              # Read/query actual content inside SharePoint pages (web parts)


class ResourceType(str, Enum):
    """Types of SharePoint resources."""
    LIST = "list"           # Custom lists
    LIBRARY = "library"     # Document libraries
    PAGE = "page"           # Site pages
    SITE = "site"           # Sites
    ALL = "all"             # All resource types


class RouterResponse(BaseModel):
    """Enhanced router response with intelligent intent classification."""
    intent: QueryIntent
    resource_type: ResourceType = ResourceType.ALL
    filter_keywords: Optional[List[str]] = None  # Keywords to filter by (e.g., ["hr", "employee"])
    list_id: Optional[str] = None  # For specific data queries when exact ID is known
    semantic_target: Optional[str] = None  # Topic/concept when no exact list ID exists (e.g., "milestones", "tasks")
    site_name: Optional[str] = None  # Site name mentioned in query (e.g., "HR", "Marketing")
    query_specifics: Optional[Dict[str, Any]] = None  # Additional query context

    # Document library specific fields
    library_names: Optional[List[str]] = None  # Library names mentioned for comparison/query
    search_query: Optional[str] = None  # Search query for document content
    data_query: Optional[str] = None  # Specific data extraction question

    # Legacy support - will be phased out
    is_meta_query: bool = False

    @field_validator('resource_type', mode='before')
    @classmethod
    def set_default_resource_type(cls, v):
        if v is None:
            return ResourceType.ALL
        return v

class DataQueryResponseModel(BaseModel):
    answer: str
    suggested_actions: List[str]
