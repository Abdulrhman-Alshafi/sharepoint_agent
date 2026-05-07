"""Enterprise architecture entities: content types, term sets, views, workflows."""

from dataclasses import dataclass, field
from typing import List
from src.domain.entities.core import ActionType


@dataclass
class TermSet:
    """Entity representing a SharePoint Term Set (Taxonomy)."""
    name: str
    terms: List[str]
    group_name: str = field(default="Default Site Collection Group")
    term_set_id: str = field(default="")
    action: ActionType = field(default=ActionType.CREATE)


@dataclass
class ContentType:
    """Entity representing a SharePoint Content Type."""
    name: str
    description: str
    parent_type: str = field(default="Item")
    columns: List[str] = field(default_factory=list)
    content_type_id: str = field(default="")
    action: ActionType = field(default=ActionType.CREATE)


@dataclass
class SPView:
    """Entity representing a SharePoint List View."""
    title: str
    target_list_title: str
    columns: List[str]
    row_limit: int = field(default=30)
    query: str = field(default="")
    view_id: str = field(default="")
    action: ActionType = field(default=ActionType.CREATE)


@dataclass
class WorkflowScaffold:
    """Entity representing Power Automate workflow scaffolding."""
    name: str
    trigger_type: str
    target_list_title: str
    actions: List[str] = field(default_factory=list)
    action: ActionType = field(default=ActionType.CREATE)
