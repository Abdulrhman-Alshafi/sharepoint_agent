"""Page purpose value object and enumeration."""

from enum import Enum


class PagePurpose(str, Enum):
    """Enumeration of SharePoint page purposes.
    
    Used to classify pages and determine appropriate content templates.
    """
    HOME = "Home"
    TEAM = "Team"
    NEWS = "News"
    DOCUMENTATION = "Documentation"
    PROJECT_STATUS = "ProjectStatus"
    RESOURCE_LIBRARY = "ResourceLibrary"
    FAQ = "FAQ"
    ANNOUNCEMENT = "Announcement"
    OTHER = "Other"
