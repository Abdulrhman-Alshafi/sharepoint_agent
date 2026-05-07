"""ResourceCandidate value object.

Represents a SharePoint list or document library discovered during
cross-site resource discovery.  It carries enough site information
so that every downstream component knows *which site* a resource belongs
to without having to do additional lookups.
"""

from dataclasses import dataclass, field
from typing import List, Literal


@dataclass
class ResourceCandidate:
    """A discovered SharePoint list or document library with its site context.

    Instances are built by ``SmartResourceDiscoveryService`` and passed through
    the entire query pipeline so the final answer can always include site
    attribution.

    Attributes:
        resource_id:      Graph API id of the list / library.
        resource_type:    "list" or "library".
        title:            Human-readable display name.
        site_id:          Graph API site id (used for subsequent API calls).
        site_name:        Human-readable site display name.
        site_url:         Root URL of the site (e.g. https://contoso.sharepoint.com/sites/hr).
        web_url:          Absolute URL directly to the list / library.
        column_names:     Column display names.  Populated lazily during Pass-2 scoring.
        relevance_score:  Normalised relevance score in the range 0.0–1.0.
    """

    resource_id: str
    resource_type: Literal["list", "library"]
    title: str
    site_id: str
    site_name: str
    site_url: str
    web_url: str
    column_names: List[str] = field(default_factory=list)
    relevance_score: float = 0.0
