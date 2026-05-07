"""Tests for PagePurposeDetector service."""

import pytest
from src.domain.services.page_purpose_detector import PagePurposeDetector
from src.domain.value_objects.page_purpose import PagePurpose


class TestPagePurposeDetector:
    """Test suite for PagePurposeDetector."""

    @pytest.fixture
    def detector(self):
        """Create detector instance."""
        return PagePurposeDetector()

    @pytest.mark.asyncio
    async def test_detect_home_page(self, detector):
        """Test detection of home/welcome page."""
        purpose, confidence = await detector.detect_purpose(
            "Welcome to Our Site",
            "Main landing page for the organization"
        )
        assert purpose == PagePurpose.HOME
        assert confidence > 0.3

    @pytest.mark.asyncio
    async def test_detect_team_page(self, detector):
        """Test detection of team page."""
        purpose, confidence = await detector.detect_purpose(
            "Engineering Team Members",
            "Meet our engineering team"
        )
        assert purpose == PagePurpose.TEAM
        assert confidence > 0.3

    @pytest.mark.asyncio
    async def test_detect_news_page(self, detector):
        """Test detection of news/announcement page."""
        purpose, confidence = await detector.detect_purpose(
            "Company Announcements",
            "Latest news and updates"
        )
        assert purpose == PagePurpose.NEWS
        assert confidence > 0.3

    @pytest.mark.asyncio
    async def test_detect_documentation_page(self, detector):
        """Test detection of documentation page."""
        purpose, confidence = await detector.detect_purpose(
            "How-To Guides",
            "Step-by-step documentation and tutorials"
        )
        assert purpose == PagePurpose.DOCUMENTATION
        assert confidence > 0.3

    @pytest.mark.asyncio
    async def test_detect_faq_page(self, detector):
        """Test detection of FAQ page."""
        purpose, confidence = await detector.detect_purpose(
            "Frequently Asked Questions",
            "Common Q&A for our organization"
        )
        assert purpose == PagePurpose.FAQ
        assert confidence > 0.3

    @pytest.mark.asyncio
    async def test_detect_project_status_page(self, detector):
        """Test detection of project status page."""
        purpose, confidence = await detector.detect_purpose(
            "Project Roadmap and Status",
            "Track progress on our key initiatives"
        )
        assert purpose == PagePurpose.PROJECT_STATUS
        assert confidence > 0.3

    @pytest.mark.asyncio
    async def test_map_to_purpose_exact_match(self):
        """Test mapping strings to PagePurpose."""
        assert PagePurposeDetector._map_to_purpose("HOME") == PagePurpose.HOME
        assert PagePurposeDetector._map_to_purpose("TEAM") == PagePurpose.TEAM
        assert PagePurposeDetector._map_to_purpose("NEWS") == PagePurpose.NEWS
        assert PagePurposeDetector._map_to_purpose("FAQ") == PagePurpose.FAQ

    @pytest.mark.asyncio
    async def test_map_to_purpose_invalid(self):
        """Test mapping with invalid purpose string."""
        result = PagePurposeDetector._map_to_purpose("INVALID_PURPOSE")
        assert result == PagePurpose.OTHER

    @pytest.mark.asyncio
    async def test_detect_with_empty_description(self, detector):
        """Test detection with empty description."""
        purpose, confidence = await detector.detect_purpose(
            "Home Page",
            ""
        )
        assert purpose in [p for p in PagePurpose]
        assert 0.0 <= confidence <= 1.0

    @pytest.mark.asyncio
    async def test_detect_returns_valid_confidence(self, detector):
        """Test that confidence is always between 0 and 1."""
        purpose, confidence = await detector.detect_purpose(
            "Some Random Page",
            "Some description"
        )
        assert 0.0 <= confidence <= 1.0
