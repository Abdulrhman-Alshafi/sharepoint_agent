"""Site detection and resolution utilities for multi-site support."""

import re
from typing import List, Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


# Words that, when appearing immediately BEFORE a preposition, signal the following
# word is a list/library name — NOT a site name.
# e.g. "items in SalaryDocuments", "files in HR Policies", "data in Tasks"
_CONTENT_POINTER_WORDS = frozenset([
    "items", "item", "files", "file", "documents", "document", "docs", "doc",
    "data", "content", "entries", "entry", "records", "record", "rows", "row",
    "everything", "details", "info", "information", "results",
])


# Platform / reserved words that are never real site names
_RESERVED_SITE_NAMES = frozenset([
    "sharepoint", "microsoft", "365", "office", "teams", "azure",
    "m365", "o365", "online", "cloud",
])


class SiteResolver:
    """Resolves site names to site IDs from queries."""

    @staticmethod
    def _clean_extracted_name(name: str, site_keywords: list) -> Optional[str]:
        """Strip trailing punctuation, remove site keywords, reject reserved names."""
        # Strip trailing punctuation (e.g. '?', '!', '.', ',')
        name = name.strip().rstrip("?!.,;:")
        for kw in site_keywords:
            name = name.replace(kw, "").strip()
        if not name:
            return None
        if name.lower() in _RESERVED_SITE_NAMES:
            return None
        return name.title()

    @staticmethod
    def extract_site_mention(question: str) -> Optional[str]:
        """Extract site name mentioned in a question.
        
        Args:
            question: User question
            
        Returns:
            Site name if detected, None otherwise
        """
        question_lower = question.lower()
        
        # Keywords that indicate a site reference
        site_keywords = ["site", "portal", "hub", "workspace", "page"]
        
        # STRATEGY 1: Look for explicit "X site" patterns (most reliable)
        # Patterns like "in HR site", "from Marketing site", etc.
        explicit_patterns = [
            r" in ([a-zA-Z0-9\s]+)\s*(?:site|portal|hub|workspace|page)",
            r" from ([a-zA-Z0-9\s]+)\s*(?:site|portal|hub|workspace|page)",
            r" on ([a-zA-Z0-9\s]+)\s*(?:site|portal|hub|workspace|page)",
            r" at ([a-zA-Z0-9\s]+)\s*(?:site|portal|hub|workspace|page)",
        ]
        
        for pattern in explicit_patterns:
            match = re.search(pattern, question_lower)
            if match:
                site_name = match.group(1).strip()
                cleaned = SiteResolver._clean_extracted_name(site_name, site_keywords)
                if cleaned:
                    return cleaned
        
        # Strategy 1 is the only safe approach: only treat X as a site when the user
        # explicitly says "X site", "X portal", "X hub", or "X workspace".
        # Any other "in X" / "from X" pattern without that keyword is far more likely
        # to be a list or library name (e.g. "status of Y in Milestones").
        return None
    
    @staticmethod
    def resolve_site_name(
        site_name: str, 
        all_sites: List[Dict[str, Any]]
    ) -> Optional[Tuple[str, str, str]]:
        """Resolve a site name to its full ID and URL.
        
        Args:
            site_name: Site name to resolve (e.g., "HR", "Marketing")
            all_sites: List of all available sites
            
        Returns:
            Tuple of (site_id, display_name, web_url) if found, None otherwise
        """
        if not site_name or not all_sites:
            return None
        
        site_name_lower = site_name.lower()
        
        # Try exact match first
        for site in all_sites:
            display_name = (site.get("displayName") or site.get("name", "")).lower()
            if display_name == site_name_lower:
                return (
                    site.get("id"),
                    site.get("displayName") or site.get("name"),
                    site.get("webUrl", "")
                )
        
        # Try partial match
        matches = []
        for site in all_sites:
            display_name = (site.get("displayName") or site.get("name", "")).lower()
            # Check if site name is in display name or vice versa
            if site_name_lower in display_name or display_name in site_name_lower:
                matches.append((
                    site.get("id"),
                    site.get("displayName") or site.get("name"),
                    site.get("webUrl", ""),
                    display_name
                ))
        
        # If we have exactly one match, return it
        if len(matches) == 1:
            return matches[0][:3]  # Return without the display_name_lower
        
        # If multiple matches, prefer the longer name (more specific)
        if len(matches) > 1:
            # Sort by length of display name descending (longer = more specific)
            matches.sort(key=lambda x: len(x[3]), reverse=True)
            return matches[0][:3]
        
        return None
    
    @staticmethod
    def format_site_context(site_name: str, site_url: str) -> str:
        """Format site context for display in responses.
        
        Args:
            site_name: Name of the site
            site_url: URL of the site
            
        Returns:
            Formatted string
        """
        return f"**{site_name}** site ({site_url})"


class SiteContextManager:
    """Manages site context in conversations."""
    
    def __init__(self):
        """Initialize site context manager."""
        self.current_site_id = None
        self.current_site_name = None
        self.current_site_url = None
    
    def set_site_context(self, site_id: str, site_name: str, site_url: str):
        """Set the current site context.
        
        Args:
            site_id: Site ID
            site_name: Site display name
            site_url: Site URL
        """
        self.current_site_id = site_id
        self.current_site_name = site_name
        self.current_site_url = site_url
        logger.info(f"Site context set to: {site_name}")
    
    def clear_site_context(self):
        """Clear the current site context."""
        self.current_site_id = None
        self.current_site_name = None
        self.current_site_url = None
        logger.info("Site context cleared")
    
    def get_site_context(self) -> Optional[Tuple[str, str, str]]:
        """Get the current site context.
        
        Returns:
            Tuple of (site_id, site_name, site_url) if set, None otherwise
        """
        if self.current_site_id:
            return (self.current_site_id, self.current_site_name, self.current_site_url)
        return None
    
    def has_context(self) -> bool:
        """Check if site context is set.
        
        Returns:
            True if context is set
        """
        return self.current_site_id is not None
