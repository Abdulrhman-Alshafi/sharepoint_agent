"""Commands for application operations."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ProvisionResourcesCommand:
    """Command to provision SharePoint resources based on a blueprint."""
    prompt: str
    user_email: str = ""
    user_login_name: str = ""
    target_site_id: str = ""

@dataclass
class DataQueryCommand:
    """Command to execute a data intelligence query over SharePoint."""
    question: str
    # Optional list of SP site IDs to scope the discovery.
    # None means "use all accessible sites".
    site_ids: Optional[List[str]] = field(default=None)
    # Page / site context forwarded from the frontend
    page_id:         Optional[str] = None
    page_url:        Optional[str] = None
    page_title:      Optional[str] = None
    context_site_id: Optional[str] = None   # from frontend, highest priority
    user_login_name: str = ""
