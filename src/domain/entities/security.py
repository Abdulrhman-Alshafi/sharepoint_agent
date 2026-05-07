"""Security-related entities: groups and permissions."""

from dataclasses import dataclass, field
from enum import Enum
from src.domain.entities.core import ActionType


class PermissionLevel(str, Enum):
    """SharePoint permission levels."""
    READ = "Read"
    CONTRIBUTE = "Contribute"
    FULL_CONTROL = "Full Control"
    EDIT = "Edit"


@dataclass
class SharePointGroup:
    """Entity representing a SharePoint site group with a target permission assignment."""
    name: str
    description: str = ""
    permission_level: PermissionLevel = field(default=PermissionLevel.READ)
    # The title of the DocumentLibrary this group should be granted access to.
    # Empty string means site-wide permission.
    target_library_title: str = ""
    group_id: str = field(default="")
    action: ActionType = field(default=ActionType.CREATE)

    def __post_init__(self):
        if not self.name or len(self.name.strip()) == 0:
            raise ValueError("Group name cannot be empty")
