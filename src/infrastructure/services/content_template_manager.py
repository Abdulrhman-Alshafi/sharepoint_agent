"""Content template manager for retrieving purpose-based page templates."""

from typing import Optional
from src.domain.value_objects.page_purpose import PagePurpose
from src.domain.entities.page_content_templates import PageContentTemplates, ContentTemplate
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class ContentTemplateManager:
    """Manages content templates for different page purposes.
    
    Retrieves predefined templates based on page purpose and provides
    them for content population.
    """

    def __init__(self):
        """Initialize template manager."""
        self._template_cache = {}

    def get_template(self, purpose: PagePurpose) -> Optional[ContentTemplate]:
        """Get content template for a given page purpose.
        
        Args:
            purpose: PagePurpose enum value
            
        Returns:
            ContentTemplate with webpart structure for the purpose,
            or None if not found
        """
        try:
            # Check cache first
            if purpose in self._template_cache:
                return self._template_cache[purpose]
            
            # Get from factory
            template = PageContentTemplates.get_template(purpose)
            
            # Cache it
            self._template_cache[purpose] = template
            
            logger.debug(f"Retrieved template for purpose: {purpose.value}")
            return template
        except Exception as e:
            logger.error(f"Failed to get template for purpose {purpose}: {e}")
            return None

    def get_available_purposes(self) -> list:
        """Get list of all available page purposes.
        
        Returns:
            List of PagePurpose enum values
        """
        return [p for p in PagePurpose]

    def clear_cache(self) -> None:
        """Clear template cache."""
        self._template_cache.clear()
        logger.debug("Template cache cleared")
