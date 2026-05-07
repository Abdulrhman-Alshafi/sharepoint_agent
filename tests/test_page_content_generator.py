"""Tests for PageContentGenerator service."""

import pytest
from src.infrastructure.services.page_content_generator import PageContentGenerator
from src.domain.value_objects.page_purpose import PagePurpose


class TestPageContentGenerator:
    """Test suite for PageContentGenerator."""

    @pytest.fixture
    def generator(self):
        """Create generator instance."""
        return PageContentGenerator()

    @pytest.mark.asyncio
    async def test_generate_page_content_home(self, generator):
        """Test generating content for Home page."""
        content = await generator.generate_page_content(
            "Welcome Home",
            "Main landing page",
            PagePurpose.HOME
        )
        
        assert "hero_title" in content
        assert "hero_description" in content
        assert "hero_image_url" in content
        assert "page_content" in content
        assert "quick_links" in content
        
        # Check for non-empty values
        assert content["hero_title"]
        assert content["page_content"]
        assert len(content["quick_links"]) > 0

    @pytest.mark.asyncio
    async def test_generate_page_content_team(self, generator):
        """Test generating content for Team page."""
        content = await generator.generate_page_content(
            "Engineering Team",
            "Meet the engineering team",
            PagePurpose.TEAM
        )
        
        assert content["hero_title"]
        assert content["page_content"]
        assert len(content["quick_links"]) > 0

    @pytest.mark.asyncio
    async def test_generate_quick_links(self, generator):
        """Test generating quick links."""
        links = await generator.generate_quick_links(
            "Resources",
            PagePurpose.RESOURCE_LIBRARY
        )
        
        assert len(links) > 0
        for link in links:
            assert "title" in link
            assert "url" in link
            assert link["title"]

    @pytest.mark.asyncio
    async def test_generate_hero_content(self, generator):
        """Test generating hero content."""
        content = await generator.generate_hero_content(
            "Welcome",
            PagePurpose.HOME
        )
        
        assert "hero_title" in content
        assert "hero_description" in content
        assert "hero_image_url" in content
        assert content["hero_title"]
        assert "source.unsplash.com" in content["hero_image_url"]

    @pytest.mark.asyncio
    async def test_generate_description(self, generator):
        """Test generating page description."""
        description = await generator.generate_description(
            "Team Page",
            "About our team",
            PagePurpose.TEAM
        )
        
        assert description
        assert "<p>" in description  # Should be HTML formatted

    @pytest.mark.asyncio
    async def test_fallback_content_different_purposes(self, generator):
        """Test fallback content for different purposes."""
        purposes = [
            PagePurpose.HOME,
            PagePurpose.TEAM,
            PagePurpose.NEWS,
            PagePurpose.DOCUMENTATION,
            PagePurpose.FAQ,
        ]
        
        for purpose in purposes:
            content = await generator.generate_page_content(
                "Test",
                "",
                purpose
            )
            
            assert content["hero_title"] == "Test"
            assert content["page_content"]
            assert content["quick_links"]

    @pytest.mark.asyncio
    async def test_generate_unsplash_url(self):
        """Test Unsplash URL generation."""
        url = PageContentGenerator._generate_unsplash_url("teamwork")
        
        assert "source.unsplash.com" in url
        assert "teamwork" in url
        assert "professional" in url

    @pytest.mark.asyncio
    async def test_page_content_has_all_keys(self, generator):
        """Test that generated content has all required keys."""
        content = await generator.generate_page_content(
            "Test Page",
            "Test description",
            PagePurpose.HOME
        )
        
        required_keys = [
            "hero_title",
            "hero_description",
            "hero_image_url",
            "hero_image_theme",
            "page_content",
            "quick_links",
        ]
        
        for key in required_keys:
            assert key in content, f"Missing key: {key}"

    @pytest.mark.asyncio
    async def test_quick_links_are_lists(self, generator):
        """Test that quick links are always lists."""
        content = await generator.generate_page_content(
            "Test",
            "",
            PagePurpose.HOME
        )
        
        assert isinstance(content["quick_links"], list)
        assert len(content["quick_links"]) >= 0

    @pytest.mark.asyncio
    async def test_content_respects_purpose(self, generator):
        """Test that generated content respects the purpose type."""
        home_content = await generator.generate_page_content(
            "Page",
            "",
            PagePurpose.HOME
        )
        
        faq_content = await generator.generate_page_content(
            "Page",
            "",
            PagePurpose.FAQ
        )
        
        # Content should be different for different purposes
        assert home_content["page_content"] != faq_content["page_content"]
