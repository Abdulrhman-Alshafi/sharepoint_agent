"""Tests for ContentTemplateManager service."""

import pytest
from src.infrastructure.services.content_template_manager import ContentTemplateManager
from src.domain.value_objects.page_purpose import PagePurpose


class TestContentTemplateManager:
    """Test suite for ContentTemplateManager."""

    @pytest.fixture
    def manager(self):
        """Create manager instance."""
        return ContentTemplateManager()

    def test_get_template_home(self, manager):
        """Test retrieving template for Home purpose."""
        template = manager.get_template(PagePurpose.HOME)
        
        assert template is not None
        assert template.purpose == PagePurpose.HOME
        assert len(template.webparts) == 3  # Hero + QuickLinks + Text
        assert template.webparts[0].type == "Hero"
        assert template.webparts[1].type == "QuickLinks"
        assert template.webparts[2].type == "Text"

    def test_get_template_team(self, manager):
        """Test retrieving template for Team purpose."""
        template = manager.get_template(PagePurpose.TEAM)
        
        assert template is not None
        assert template.purpose == PagePurpose.TEAM
        assert len(template.webparts) == 3

    def test_get_template_news(self, manager):
        """Test retrieving template for News purpose."""
        template = manager.get_template(PagePurpose.NEWS)
        
        assert template is not None
        assert template.purpose == PagePurpose.NEWS
        assert len(template.webparts) == 3

    def test_get_template_documentation(self, manager):
        """Test retrieving template for Documentation purpose."""
        template = manager.get_template(PagePurpose.DOCUMENTATION)
        
        assert template is not None
        assert template.purpose == PagePurpose.DOCUMENTATION
        assert len(template.webparts) == 3

    def test_get_template_faq(self, manager):
        """Test retrieving template for FAQ purpose."""
        template = manager.get_template(PagePurpose.FAQ)
        
        assert template is not None
        assert template.purpose == PagePurpose.FAQ
        assert len(template.webparts) == 3

    def test_get_template_project_status(self, manager):
        """Test retrieving template for ProjectStatus purpose."""
        template = manager.get_template(PagePurpose.PROJECT_STATUS)
        
        assert template is not None
        assert template.purpose == PagePurpose.PROJECT_STATUS
        assert len(template.webparts) == 3

    def test_get_template_resource_library(self, manager):
        """Test retrieving template for ResourceLibrary purpose."""
        template = manager.get_template(PagePurpose.RESOURCE_LIBRARY)
        
        assert template is not None
        assert template.purpose == PagePurpose.RESOURCE_LIBRARY
        assert len(template.webparts) == 3

    def test_get_template_announcement(self, manager):
        """Test retrieving template for Announcement purpose."""
        template = manager.get_template(PagePurpose.ANNOUNCEMENT)
        
        assert template is not None
        assert template.purpose == PagePurpose.ANNOUNCEMENT
        assert len(template.webparts) == 3

    def test_get_template_other(self, manager):
        """Test retrieving template for Other purpose."""
        template = manager.get_template(PagePurpose.OTHER)
        
        assert template is not None
        assert template.purpose == PagePurpose.OTHER
        assert len(template.webparts) == 3

    def test_template_caching(self, manager):
        """Test that templates are cached."""
        # First call
        template1 = manager.get_template(PagePurpose.HOME)
        
        # Second call should return cached version
        template2 = manager.get_template(PagePurpose.HOME)
        
        assert template1 is template2  # Same object

    def test_clear_cache(self, manager):
        """Test clearing template cache."""
        # Cache a template
        template1 = manager.get_template(PagePurpose.HOME)
        
        # Clear cache
        manager.clear_cache()
        
        # Get template again
        template2 = manager.get_template(PagePurpose.HOME)
        
        # Should be different objects after cache clear
        assert template1 is not template2

    def test_get_available_purposes(self, manager):
        """Test retrieving list of available purposes."""
        purposes = manager.get_available_purposes()
        
        assert len(purposes) == len(PagePurpose)
        assert PagePurpose.HOME in purposes
        assert PagePurpose.TEAM in purposes
        assert PagePurpose.FAQ in purposes

    def test_template_has_placeholders(self, manager):
        """Test that templates contain placeholder strings."""
        template = manager.get_template(PagePurpose.HOME)
        
        # Check for placeholders in webpart properties
        has_placeholders = False
        for wp in template.webparts:
            props_str = str(wp.properties)
            if "{" in props_str and "}" in props_str:
                has_placeholders = True
                break
        
        assert has_placeholders, "Template should have placeholders for substitution"

    def test_template_webparts_have_types(self, manager):
        """Test that all template webparts have proper types."""
        for purpose in PagePurpose:
            template = manager.get_template(purpose)
            
            for wp in template.webparts:
                assert wp.type is not None
                assert len(wp.type) > 0
                assert wp.webpart_type is not None
                assert len(wp.webpart_type) > 0
