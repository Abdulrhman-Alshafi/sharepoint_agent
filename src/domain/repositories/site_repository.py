"""Site repository interfaces — split by concern (ISP).

Four focused ABCs combined into the backwards-compatible ``ISiteRepository``::

    ISiteCRUDRepository        — create / read / search / update / delete sites.
    ISiteMemberRepository      — owners, members, add/remove users.
    ISiteCustomizationRepository — theme, navigation.
    ISiteAnalyticsRepository   — storage info, analytics, recycle bin.

    ISiteRepository            — union of all four (backwards compat).
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from src.domain.entities.core import SPSite


# ══════════════════════════════════════════════════════════════════════════════
# 1. Site CRUD
# ══════════════════════════════════════════════════════════════════════════════

class ISiteCRUDRepository(ABC):
    """Create, read, search, update, and delete SharePoint sites."""

    @abstractmethod
    async def create_site(self, sp_site: SPSite) -> Dict[str, Any]:
        """Create a site in SharePoint. Returns created site metadata."""

    @abstractmethod
    async def get_site(self, site_id: str) -> Dict[str, Any]:
        """Get a site by ID."""

    @abstractmethod
    async def get_site_by_url(self, site_url: str) -> Dict[str, Any]:
        """Get a site by its URL."""

    @abstractmethod
    async def get_all_sites(self) -> List[Dict[str, Any]]:
        """Return all SharePoint sites the caller has access to."""

    @abstractmethod
    async def search_sites(self, query: str) -> List[Dict[str, Any]]:
        """Search sites by name or description."""

    @abstractmethod
    async def update_site(
        self, site_id: str, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update site properties. Returns updated metadata."""

    @abstractmethod
    async def delete_site(self, site_id: str) -> bool:
        """Delete a site. Returns True on success."""


# ══════════════════════════════════════════════════════════════════════════════
# 2. Site membership
# ══════════════════════════════════════════════════════════════════════════════

class ISiteMemberRepository(ABC):
    """Manage site owners and members."""

    @abstractmethod
    async def get_site_owners(self, site_id: str) -> List[Dict[str, Any]]:
        """Return a list of site owner user profiles."""

    @abstractmethod
    async def get_site_members(self, site_id: str) -> List[Dict[str, Any]]:
        """Return a list of site member user profiles."""

    @abstractmethod
    async def add_site_owner(self, site_id: str, user_email: str) -> bool:
        """Add a user as site owner. Returns True on success."""

    @abstractmethod
    async def add_site_member(self, site_id: str, user_email: str) -> bool:
        """Add a user as site member. Returns True on success."""

    @abstractmethod
    async def remove_site_user(self, site_id: str, user_id: str) -> bool:
        """Remove a user from the site. Returns True on success."""


# ══════════════════════════════════════════════════════════════════════════════
# 3. Site customization
# ══════════════════════════════════════════════════════════════════════════════

class ISiteCustomizationRepository(ABC):
    """Theme and navigation customisation for sites."""

    @abstractmethod
    async def update_site_theme(
        self, site_id: str, theme_settings: Dict[str, Any]
    ) -> bool:
        """Update site theme / logo. Returns True on success."""

    @abstractmethod
    async def get_site_navigation(
        self, site_id: str, nav_type: str = "top"
    ) -> List[Dict[str, Any]]:
        """Return site navigation items (type: "top" or "left")."""

    @abstractmethod
    async def update_site_navigation(
        self,
        site_id: str,
        nav_type: str,
        nav_items: List[Dict[str, Any]],
    ) -> bool:
        """Update site navigation. Returns True on success."""


# ══════════════════════════════════════════════════════════════════════════════
# 4. Analytics, storage & recycle bin
# ══════════════════════════════════════════════════════════════════════════════

class ISiteAnalyticsRepository(ABC):
    """Storage info, usage analytics, and recycle-bin management."""

    @abstractmethod
    async def get_site_storage_info(self, site_id: str) -> Dict[str, Any]:
        """Return storage information (used, quota, etc.)."""

    @abstractmethod
    async def get_site_analytics(
        self, site_id: str, period: str = "last7days"
    ) -> Dict[str, Any]:
        """Return site analytics for the given time period."""

    @abstractmethod
    async def get_site_recycle_bin(self, site_id: str) -> List[Dict[str, Any]]:
        """Return items currently in the recycle bin."""

    @abstractmethod
    async def restore_from_recycle_bin(self, site_id: str, item_id: str) -> bool:
        """Restore an item from the recycle bin. Returns True on success."""

    @abstractmethod
    async def empty_recycle_bin(self, site_id: str) -> bool:
        """Empty the recycle bin. Returns True on success."""


# ══════════════════════════════════════════════════════════════════════════════
# Combined backwards-compatible interface
# ══════════════════════════════════════════════════════════════════════════════

class ISiteRepository(
    ISiteCRUDRepository,
    ISiteMemberRepository,
    ISiteCustomizationRepository,
    ISiteAnalyticsRepository,
):
    """Full site repository interface (backwards-compatible union).

    Prefer injecting the narrower sub-interfaces where possible:
      - ``ISiteCRUDRepository``           for provisioning / basic lookups.
      - ``ISiteMemberRepository``         for membership management.
      - ``ISiteCustomizationRepository``  for theme / nav updates.
      - ``ISiteAnalyticsRepository``      for reporting and recycle-bin work.
    """
